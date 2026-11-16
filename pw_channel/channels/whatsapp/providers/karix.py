import httpx
import logging
from typing import Optional, Dict, Any, List
from pw_channel.channels.whatsapp.settings import settings
from pw_channel.channels.whatsapp.models import WhatsAppIncomingMessage
from pw_channel.channels.whatsapp.providers.base import WhatsAppProvider

logger = logging.getLogger(__name__)

MEDIA_TYPE_MAP = {
    "image": "image",
    "video": "video",
    "document": "document",
    "file": "document",
    "sticker": "image",
}

MEDIA_SECTION_KEYS = ("attachment", "media")
MEDIA_URL_KEYS = ("fileLink", "url", "link", "fileUrl")


def _media_section(msg: dict, kind: str) -> dict:
    for key in (kind, *MEDIA_SECTION_KEYS):
        section = msg.get(key)
        if isinstance(section, dict) and section:
            return section
    return {}


def _media_url(section: dict) -> str:
    for key in MEDIA_URL_KEYS:
        value = section.get(key)
        if value:
            return str(value)
    return ""


class KarixClient(WhatsAppProvider):
    name = "karix"
    webhook_path = "/api/channel/whatsapp/webhook/karix"

    def __init__(self, sender: str):
        self.sender = sender.lstrip("+")
        self.username = settings.karix_username
        self.password = settings.karix_password
        self.scenario_key = settings.karix_scenario_key
        self.base_url = settings.karix_api_base_url.rstrip("/")
        self.timeout = 60.0

    def is_inbound(self, payload: dict) -> bool:
        event_type = payload.get("events", {}).get("eventType", "")
        return not event_type or event_type.upper() == "USER INITIATED"

    def routing(self, payload: dict) -> tuple[str, str]:
        content = payload.get("eventContent", {})
        message = content.get("message", {})
        to = (message.get("to") or content.get("wabaNumber") or content.get("to") or payload.get("wabaNumber")
              or payload.get("recipient", {}).get("to") or payload.get("to") or "")
        return str(message.get("from", "")).lstrip("+"), str(to).lstrip("+")


    def parse_webhook_message(self, payload: dict) -> Optional[WhatsAppIncomingMessage]:
        try:
            msg = payload.get("eventContent", {}).get("message", {})
            if not msg:
                return None

            from_number = msg.get("from", "")
            message_id = msg.get("id", "")
            message_type = str(msg.get("messageType", "") or "")
            attachment_type = str(msg.get("attachmentType", "") or "")

            if message_type == "text":
                text = msg.get("text", {}).get("body", "")
                return WhatsAppIncomingMessage(
                    from_number=from_number,
                    message_text=text,
                    message_id=message_id,
                )

            content_type = str(msg.get("contentType", "") or "")
            is_audio = (
                message_type.lower() in ("audio", "voice")
                or attachment_type.lower() in ("audio", "voice")
                or (content_type.upper() == "ATTACHMENT"
                    and attachment_type.lower() in ("audio", "voice"))
            )
            if is_audio:
                media_key = (
                    attachment_type.lower()
                    if attachment_type.lower() in ("audio", "voice")
                    else message_type.lower()
                )
                audio_section = (
                    (msg.get(media_key) if isinstance(msg.get(media_key), dict) else {})
                    or (msg.get("audio") if isinstance(msg.get("audio"), dict) else {})
                    or (msg.get("voice") if isinstance(msg.get("voice"), dict) else {})
                    or _media_section(msg, media_key)
                    or {}
                )
                audio_url = _media_url(audio_section)
                if not audio_url:
                    logger.warning(f"[KARIX] audio message {message_id} has no fileLink — dropping")
                    return None
                return WhatsAppIncomingMessage(
                    from_number=from_number,
                    message_text="",
                    message_id=message_id,
                    audio_url=audio_url,
                )

            media_kind = (
                MEDIA_TYPE_MAP.get(message_type.lower())
                or MEDIA_TYPE_MAP.get(attachment_type.lower())
            )
            if media_kind:
                raw_kind = message_type.lower() if message_type.lower() in MEDIA_TYPE_MAP else attachment_type.lower()
                section = _media_section(msg, raw_kind)
                media_url = _media_url(section)
                if not media_url:
                    logger.warning(f"[KARIX] {raw_kind} message {message_id} has no media URL — dropping")
                    return None

                caption = section.get("caption", "") or ""
                return WhatsAppIncomingMessage(
                    from_number=from_number,
                    message_text=caption,
                    message_id=message_id,
                    media_type=media_kind,
                    media_url=media_url,
                    media_caption=caption,
                    media_filename=section.get("fileName", "") or section.get("filename", "") or "",
                    media_mime_type=section.get("mimeType", "") or section.get("mime_type", "") or "",
                )

            if message_type == "interactive":
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    button_id = interactive.get("button_reply", {}).get("id", "")
                    return WhatsAppIncomingMessage(
                        from_number=from_number,
                        message_text=button_id,
                        message_id=message_id,
                    )

            if message_type == "button":
                button = msg.get("button", {})
                button_value = button.get("payload") or button.get("text") or ""
                return WhatsAppIncomingMessage(
                    from_number=from_number,
                    message_text=button_value,
                    message_id=message_id,
                )

            logger.info(f"[KARIX] Ignoring message type: {message_type} (attachmentType: {attachment_type or 'none'})")
            return None

        except Exception as e:
            logger.error(f"[KARIX] Error parsing webhook: {e}")
            return None


    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authentication": f"Bearer {self.scenario_key}",
        }

    @property
    def media_auth(self) -> tuple[str, str] | None:
        return (self.username, self.password) if self.username and self.password else None

    @property
    def media_download_headers(self) -> dict:
        return {"Authentication": f"Bearer {self.scenario_key}"}

    @property
    def _recipient(self, to: str) -> dict:
        return {
            "to": to.lstrip("+"),
            "recipient_type": "individual",
            "reference": {"cust_ref": "123", "messageTag1": "", "conversationId": ""},
        }

    def _wrap(self, to: str, content: dict) -> dict:
        return {
            "message": {
                "channel": "WABA",
                "content": content,
                "recipient": self._recipient(to),
                "sender": {"from": self.sender},
                "preferences": {"webHookDNId": ""},
            },
            "metaData": {"version": "v1.0.9"},
        }

    @staticmethod
    def _is_accepted(response) -> bool:
        try:
            data = response.json()
        except Exception:
            return True
        if not isinstance(data, dict):
            return True
        status_code = str(data.get("statusCode", "")).strip()
        if not status_code or status_code.startswith("2"):
            return True
        logger.warning(
            f"[KARIX] Send rejected: statusCode={status_code} "
            f"desc={data.get('statusDesc')}"
        )
        return False

    async def _post(self, payload: dict) -> bool:
        url = f"{self.base_url}/sendMessage"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                auth=(self.username, self.password),
            ) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                logger.info(f"[KARIX] API response {response.status_code}: {response.text}")
                response.raise_for_status()
                return self._is_accepted(response)
        except Exception as e:
            logger.error(f"[KARIX] API call failed: {e}")
            return False

    async def _post_with_id(self, payload: dict) -> Optional[str]:
        url = f"{self.base_url}/sendMessage"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                auth=(self.username, self.password),
            ) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
                msg_id = (
                    data.get("messageId")
                    or data.get("id")
                    or data.get("mid")
                    or (data.get("message") or {}).get("id")
                )
                return str(msg_id) if msg_id else None
        except Exception as e:
            logger.error(f"[KARIX] API call failed: {e}")
            return None


    async def mark_as_read(self, message_id: str, to: str = "") -> bool:
        return await self.mark_many_as_read([message_id])

    async def mark_many_as_read(self, message_ids: List[str]) -> bool:
        ids = [str(m) for m in message_ids if m]
        if not ids:
            return False

        url = f"{self.base_url}/markAsRead"
        payload = {"id": ids, "senderId": self.sender}

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                auth=(self.username, self.password),
            ) as client:
                response = await client.post(url, headers=self._headers(), json=payload)

            if response.status_code not in (200, 201):
                logger.warning(
                    f"[KARIX] markAsRead HTTP {response.status_code} for {ids}: {response.text}"
                )
                return False

            try:
                status_code = str((response.json() or {}).get("statusCode", "200"))
            except Exception:
                status_code = "200"

            if status_code not in ("200", "201"):
                logger.warning(f"[KARIX] markAsRead rejected for {ids}: {response.text}")
                return False

            logger.info(f"[KARIX] markAsRead accepted for {ids}: {response.text}")
            return True
        except Exception as e:
            logger.warning(f"[KARIX] markAsRead failed for {ids}: {e}")
            return False

    async def send_text_message(self, to: str, text: str) -> bool:
        payload = self._wrap(to, {
            "preview_url": False,
            "text": text,
            "type": "TEXT",
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] Text sent to {to}")
        return success

    async def send_image_with_caption(self, to: str, image_url: str, caption: str) -> bool:
        payload = self._wrap(to, {
            "type": "ATTACHMENT",
            "attachment": {
                "type": "image",
                "caption": caption,
                "fileName": caption,
                "url": image_url,
            },
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] Image sent to {to}")
            return True
        if not (caption or "").strip():
            logger.warning(f"[KARIX] Image failed and no caption to fall back to for {to}")
            return False
        logger.warning(f"[KARIX] Image failed, sending caption as text to {to}")
        return await self.send_text_message(to, caption)

    async def send_interactive_button(
        self,
        to: str,
        body_text: str,
        button_text: str,
        button_url: str,
    ) -> bool:
        payload = self._wrap(to, {
            "preview_url": False,
            "shorten_url": False,
            "type": "INTERACTIVE",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body_text},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": button_text[:20],
                        "url": button_url,
                    },
                },
            },
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] CTA button sent to {to}")
            return True
        return await self.send_text_message(to, f"{body_text}\n\n{button_text}: {button_url}")

    async def send_interactive_reply_button(
        self,
        to: str,
        body_text: str,
        buttons: List[Dict[str, str]],
    ) -> bool:
        formatted = [
            {"type": "reply", "reply": {"id": b["id"][:256], "title": b["title"][:20]}}
            for b in buttons[:3]
        ]
        payload = self._wrap(to, {
            "preview_url": False,
            "shorten_url": False,
            "type": "INTERACTIVE",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": formatted},
            },
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] Reply buttons sent to {to}")
            return True
        opts = "\n".join(f"{i+1}. {b['title']}" for i, b in enumerate(buttons[:3]))
        return await self.send_text_message(to, f"{body_text}\n\n{opts}")

    async def send_interactive_cta_button_with_id(
        self,
        to: str,
        body_text: str,
        button_text: str,
        button_url: str,
    ) -> Optional[str]:
        payload = self._wrap(to, {
            "preview_url": False,
            "shorten_url": False,
            "type": "INTERACTIVE",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body_text},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": button_text[:20],
                        "url": button_url,
                    },
                },
            },
        })
        msg_id = await self._post_with_id(payload)
        if msg_id:
            logger.info(f"[KARIX] CTA button sent to {to}, msg_id: {msg_id}")
            return msg_id
        await self.send_text_message(to, f"{body_text}\n\n{button_text}: {button_url}")
        return None

    async def send_document(
        self,
        to: str,
        file_url: str,
        caption: str = "",
        filename: str = "document",
    ) -> bool:
        payload = self._wrap(to, {
            "type": "ATTACHMENT",
            "attachment": {
                "type": "document",
                "caption": caption,
                "fileName": filename,
                "url": file_url,
            },
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] Document sent to {to}")
        return success

    async def send_list_message(
        self,
        to: str,
        header: str,
        body: str,
        footer: str,
        sections: list,
    ) -> bool:
        payload = self._wrap(to, {
            "preview_url": False,
            "shorten_url": False,
            "type": "INTERACTIVE",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header},
                "body": {"text": body},
                "footer": {"text": footer},
                "action": {"button": "list", "sections": sections},
            },
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] List message sent to {to}")
        return success

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str,
        components: List[Dict[str, Any]],
    ) -> bool:
        payload = self._wrap(to, {
            "type": "TEMPLATE",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        })
        success = await self._post(payload)
        if success:
            logger.info(f"[KARIX] Template sent to {to}")
        return success
