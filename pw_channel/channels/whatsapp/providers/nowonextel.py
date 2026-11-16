import json
import logging
import re
import uuid
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx

from pw_channel.channels.whatsapp.settings import settings
from pw_channel.channels.whatsapp.models import WhatsAppIncomingMessage
from pw_channel.channels.whatsapp.providers.base import WhatsAppProvider

logger = logging.getLogger(__name__)

MEDIA_TYPE_MAP = {
    "image": "image",
    "video": "video",
    "document": "document",
    "sticker": "image",
}

MEDIA_URL_KEYS = ("mediaUrl", "media_url", "url", "link")


def normalize_number(number: Any) -> str:
    return re.sub(r"\D", "", str(number or ""))


def _media_url(section: dict) -> str:
    for key in MEDIA_URL_KEYS:
        value = section.get(key)
        if value:
            return str(value)
    return ""


def _flow_reply_text(nfm_reply: dict) -> str:
    raw = nfm_reply.get("response_json")
    fields: Any = raw
    if isinstance(raw, str):
        try:
            fields = json.loads(raw)
        except (ValueError, TypeError):
            fields = None

    if isinstance(fields, dict):
        lines = [
            f"{key}: {value}"
            for key, value in fields.items()
            if key != "flow_token" and value not in (None, "")
        ]
        if lines:
            return "\n".join(lines)

    return str(nfm_reply.get("body") or "")


def _location_text(location: dict) -> str:
    place = ", ".join(str(p) for p in (location.get("name"), location.get("address")) if p)
    lat, lng = location.get("latitude"), location.get("longitude")
    coords = f"{lat}, {lng}" if lat not in (None, "") and lng not in (None, "") else ""
    if place and coords:
        return f"My location: {place} ({coords})"
    return f"My location: {place or coords}" if (place or coords) else ""


def extract_routing(payload: dict) -> Dict[str, str]:
    try:
        value = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}) or {}
    except (AttributeError, IndexError, TypeError):
        value = {}
    metadata = value.get("metadata", {}) or {}
    messages = value.get("messages") or [{}]
    return {
        "from": normalize_number(messages[0].get("from", "")),
        "to": normalize_number(metadata.get("display_phone_number", "")),
    }


class NowonextelClient(WhatsAppProvider):
    name = "nowonextel"
    webhook_path = "/api/channel/whatsapp/webhook/nowonextel"

    def __init__(self, sender: str):
        self.sender = normalize_number(sender)
        self.api_url = settings.nowonextel_api_url
        self.headers = {
            "apikey": settings.nowonextel_api_key,
            "Content-Type": "application/json",
        }
        self.timeout = 60.0

    @property
    def media_download_headers(self) -> Optional[dict]:
        if settings.nowonextel_media_auth:
            return {"apikey": settings.nowonextel_api_key}
        return None

    def routing(self, payload: dict) -> tuple[str, str]:
        found = extract_routing(payload)
        return found["from"], found["to"]

    def authorized(self, request) -> bool:
        import hmac

        secret = settings.nowonextel_webhook_secret
        if not secret:
            return True
        supplied = request.headers.get("X-Webhook-Secret") or request.query_params.get("token") or ""
        return hmac.compare_digest(supplied.encode(), secret.encode())

    def verify(self, request) -> str | None:
        challenge = request.query_params.get("hub.challenge")
        accepted = {settings.webhook_verify_token, settings.nowonextel_webhook_secret} - {""}
        if challenge is not None and request.query_params.get("hub.verify_token") in accepted:
            return challenge
        return None


    def parse_webhook_message(self, payload: dict) -> Optional[WhatsAppIncomingMessage]:
        try:
            value = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}) or {}
            messages = value.get("messages") or []
            if not messages:
                return None

            msg = messages[0]
            message_type = str(msg.get("type", "") or "").lower()
            from_number = normalize_number(msg.get("from", ""))
            message_id = str(msg.get("id", "") or "")

            def text_message(text: str) -> WhatsAppIncomingMessage:
                return WhatsAppIncomingMessage(
                    from_number=from_number, message_text=text, message_id=message_id,
                )

            if message_type == "text":
                return text_message((msg.get("text") or {}).get("body", ""))

            if message_type in ("audio", "voice"):
                audio = msg.get(message_type) or {}
                audio_url = _media_url(audio)
                audio_id = str(audio.get("id", "") or "")
                if not audio_url and not audio_id:
                    logger.warning(f"[NOWONEXTEL] audio {message_id} has neither mediaUrl nor id — dropping")
                    return None
                return WhatsAppIncomingMessage(
                    from_number=from_number, message_text="", message_id=message_id,
                    audio_url=audio_url or None,
                    audio_media_id=None if audio_url else audio_id,
                )

            if message_type in MEDIA_TYPE_MAP:
                media = msg.get(message_type) or {}
                caption = media.get("caption", "") or ""
                media_url = _media_url(media)
                return WhatsAppIncomingMessage(
                    from_number=from_number,
                    message_text=caption,
                    message_id=message_id,
                    media_type=MEDIA_TYPE_MAP[message_type],
                    media_id=None if media_url else (str(media.get("id", "") or "") or None),
                    media_url=media_url,
                    media_caption=caption,
                    media_filename=media.get("filename", "") or "",
                    media_mime_type=media.get("mime_type", "") or "",
                )

            if message_type == "interactive":
                interactive = msg.get("interactive") or {}
                interactive_type = interactive.get("type", "")
                if interactive_type in ("button_reply", "list_reply"):
                    return text_message((interactive.get(interactive_type) or {}).get("id", ""))
                if interactive_type == "nfm_reply":
                    return text_message(_flow_reply_text(interactive.get("nfm_reply") or {}))

            if message_type == "button":
                button = msg.get("button") or {}
                return text_message(button.get("payload") or button.get("text") or "")

            if message_type == "location":
                text = _location_text(msg.get("location") or {})
                if text:
                    return text_message(text)

            logger.info(f"[NOWONEXTEL] Ignoring message type: {message_type}")
            return None

        except Exception as e:
            logger.error(f"[NOWONEXTEL] Error parsing webhook: {e}", exc_info=True)
            return None


    def _split_recipient(self, to: str) -> tuple:
        number = normalize_number(to)
        prefix = settings.nowonextel_country_prefix.strip()
        prefix_digits = normalize_number(prefix)
        if prefix_digits and number.startswith(prefix_digits) and len(number) - len(prefix_digits) >= 10:
            return number[len(prefix_digits):], prefix
        logger.warning(f"[NOWONEXTEL] {number} does not start with {prefix or 'a prefix'} — sending with empty prefix")
        return number, ""

    def _wrap(self, to: str, message_type: str, body: dict) -> dict:
        recipient, prefix = self._split_recipient(to)
        return {
            "wa": [{
                "messaging_product": "whatsapp",
                "recipient": recipient,
                "sender": self.sender,
                "recipient_type": "individual",
                "type": message_type,
                message_type: body,
            }],
            "prefix": prefix,
        }

    @staticmethod
    def _rejection(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        reason = str(data.get("message") or data.get("error") or data)
        if data.get("status") is False or data.get("success") is False:
            return reason
        if str(data.get("status", "")).lower() in ("error", "failed", "failure", "fail"):
            return reason
        if data.get("error"):
            return reason
        return ""

    @staticmethod
    def _message_id(data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        candidates = [data, data.get("data")]
        for list_key in ("wa", "messages", "data"):
            items = data.get(list_key)
            if isinstance(items, list) and items:
                candidates.append(items[0])
        for container in candidates:
            if isinstance(container, dict):
                for key in ("messageId", "message_id", "msgId", "id", "wamid"):
                    if container.get(key):
                        return str(container[key])
        return None

    async def _send(self, payload: dict) -> tuple:
        if not self.api_url or not settings.nowonextel_api_key:
            logger.error("[NOWONEXTEL] NOWONEXTEL_API_URL / NOWONEXTEL_API_KEY not set — message not sent")
            return False, None

        message = payload["wa"][0]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.api_url, headers=self.headers, json=payload)
            logger.info(
                f"[NOWONEXTEL] {message['type']} {self.sender} → {message['recipient']}: "
                f"HTTP {response.status_code} {response.text}"
            )
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                data = None
            reason = self._rejection(data)
            if reason:
                logger.warning(f"[NOWONEXTEL] {message['type']} rejected: {reason}")
                return False, None
            return True, self._message_id(data) or f"nowonextel-{uuid.uuid4().hex}"
        except Exception as e:
            logger.error(f"[NOWONEXTEL] {message['type']} send failed: {e}")
            return False, None

    async def _send_cta(self, to: str, body_text: str, button_text: str, button_url: str) -> tuple:
        return await self._send(self._wrap(to, "interactive", {
            "type": "cta_url",
            "body": {"text": body_text},
            "action": {
                "name": "cta_url",
                "parameters": {"display_text": button_text[:20], "url": button_url},
            },
        }))


    async def mark_as_read(self, message_id: str, to: str = "") -> bool:
        return False

    async def get_media_url(self, media_id: str) -> Optional[str]:
        media_api = settings.nowonextel_media_api_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{media_api}/media",
                    params={"mediaId": media_id, "phoneNumber": self.sender},
                    headers={"apikey": settings.nowonextel_api_key},
                )
            response.raise_for_status()
            meta_url = (response.json() or {}).get("url")
        except Exception as e:
            logger.error(f"[NOWONEXTEL] media lookup failed for {media_id}: {e}")
            return None

        if not meta_url:
            logger.error(f"[NOWONEXTEL] media lookup for {media_id} returned no url: {response.text}")
            return None

        query = urlencode({"mediaUrl": meta_url, "phoneNumber": self.sender})
        return f"{media_api}/download-media?{query}"

    async def download_media(self, media_id: str) -> Optional[Dict[str, Any]]:
        url = await self.get_media_url(media_id)
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers={"apikey": settings.nowonextel_api_key})
            response.raise_for_status()
            return {
                "content": response.content,
                "content_type": response.headers.get("content-type", "application/octet-stream"),
            }
        except Exception as e:
            logger.error(f"[NOWONEXTEL] media download failed for {media_id}: {e}")
            return None

    async def send_text_message(self, to: str, text: str) -> bool:
        accepted, _ = await self._send(self._wrap(to, "text", {"preview_url": True, "body": text}))
        return accepted

    async def send_image_with_caption(self, to: str, image_url: str, caption: str) -> bool:
        accepted, _ = await self._send(self._wrap(to, "image", {"link": image_url, "caption": caption}))
        return accepted

    async def send_document(self, to: str, file_url: str, caption: str = "", filename: str = "document") -> bool:
        accepted, _ = await self._send(self._wrap(to, "document", {
            "link": file_url, "caption": caption, "filename": filename,
        }))
        return accepted

    async def send_interactive_button(self, to: str, body_text: str, button_text: str, button_url: str) -> bool:
        return await self.send_interactive_cta_button_with_id(to, body_text, button_text, button_url) is not None

    async def send_interactive_cta_button_with_id(
        self, to: str, body_text: str, button_text: str, button_url: str,
    ) -> Optional[str]:
        accepted, msg_id = await self._send_cta(to, body_text, button_text, button_url)
        if accepted:
            return msg_id
        await self.send_text_message(to, f"{body_text}\n\n{button_text}: {button_url}")
        return None

    async def send_interactive_reply_button(self, to: str, body_text: str, buttons: List[Dict[str, str]]) -> bool:
        return await self.send_interactive_reply_button_with_id(to, body_text, buttons) is not None

    async def send_interactive_reply_button_with_id(
        self, to: str, body_text: str, buttons: List[Dict[str, str]],
    ) -> Optional[str]:
        accepted, msg_id = await self._send(self._wrap(to, "interactive", {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": b["id"][:256], "title": b["title"][:20]}}
                for b in buttons[:3]
            ]},
        }))
        if accepted:
            return msg_id
        opts = "\n".join(f"{i + 1}. {b['title']}" for i, b in enumerate(buttons[:3]))
        await self.send_text_message(to, f"{body_text}\n\n{opts}")
        return None

    async def send_list_message(self, to: str, header: str, body: str, footer: str, sections: list) -> bool:
        formatted_sections = [
            {
                "title": str(section.get("title", ""))[:24],
                "rows": [
                    {
                        "id": str(row.get("id", row.get("rowId", "")))[:256],
                        "title": str(row.get("title", ""))[:24],
                        "description": str(row.get("description", ""))[:72],
                    }
                    for row in section.get("rows", [])
                ],
            }
            for section in sections
        ]
        accepted, _ = await self._send(self._wrap(to, "interactive", {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "footer": {"text": footer},
            "action": {"button": "Select", "sections": formatted_sections},
        }))
        return accepted

    async def send_template_message(
        self, to: str, template_name: str, language_code: str, components: List[Dict[str, Any]],
    ) -> bool:
        accepted, _ = await self._send(self._wrap(to, "template", {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        }))
        return accepted
