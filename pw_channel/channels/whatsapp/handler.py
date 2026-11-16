import asyncio
import logging
import json
import re
import time
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from pw_channel.channels.whatsapp.settings import settings
from pw_channel.channels.whatsapp.models import ChatResponse
from pw_channel.channels.whatsapp.brain import chat_service
from pw_channel.channels.whatsapp import signals
from pw_channel.channels.whatsapp.providers.base import WhatsAppProvider
from pw_channel.channels.whatsapp.signals import is_opt_out
from pw_channel.channels.whatsapp.sessions import session_manager
from pw_channel.channels.whatsapp.campaigns.store import campaign_store
from pw_channel.channels.whatsapp import transcription as transcription_service

logger = logging.getLogger(__name__)


MEDIA_LABELS = {"image": "an image", "video": "a video", "document": "a document"}

def media_not_supported_reply() -> str:
    return (
        "I can't read images or documents yet. Please type your question and I'll be happy to help, "
        f"or ask to speak with the {settings.company_name} team."
    )


class MessageHandler:

    def __init__(self, wa_client: WhatsAppProvider):
        self.wa_client = wa_client

    async def _transcribe_audio(self, audio_media_id: str, audio_url: str) -> str:
        try:
            if audio_media_id:
                media_url = await self.wa_client.get_media_url(audio_media_id)
                if not media_url:
                    logger.error(f"[TRANSCRIPTION] Could not resolve media ID {audio_media_id}")
                    return ""
                text = await transcription_service.download_and_transcribe(media_url, headers=self.wa_client.media_download_headers)
            else:
                text = await transcription_service.download_and_transcribe(
                    audio_url,
                    headers=self.wa_client.media_download_headers,
                    auth=self.wa_client.media_auth,
                )

            if text:
                logger.info(f"[TRANSCRIPTION] Transcribed voice note: {text!r}")
            else:
                logger.warning("[TRANSCRIPTION] Whisper returned empty result")
            return text or ""
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Unexpected error: {e}")
            return ""

    async def _check_repeated_echo(self, phone_number: str, message: str) -> str:
        normalized = re.sub(r"\s+", " ", message.strip().lower())
        if not normalized:
            return "process"
        repeat_count = await session_manager.register_message_and_get_repeat_count(
            phone_number, normalized, settings.duplicate_message_ttl
        )
        if repeat_count == settings.duplicate_message_repeat_threshold:
            return "reply"
        if repeat_count > settings.duplicate_message_repeat_threshold:
            return "silent"
        return "process"

    async def process_incoming_message(
        self,
        phone_number: str,
        message: str,
        message_id: str,
        audio_media_id: str = "",
        audio_url: str = "",
        media: Optional[Dict[str, Any]] = None,
    ):
        try:

            await self.wa_client.mark_as_read(message_id, phone_number)

            if is_opt_out(message):
                await signals.emit("opt_out", phone_number, {"text": message}, dedupe_key=f"wa:{message_id}")
                await self.wa_client.send_text_message(phone_number, settings.opt_out_reply)
                return
            await signals.emit("whatsapp.replied", phone_number, {"message_id": message_id}, dedupe_key=f"wa:{message_id}")

            if media:
                if await self.handle_incoming_media(phone_number, message_id, media):
                    return
                message = (media.get("caption") or "").strip()

            if audio_media_id or audio_url:
                message = await self._transcribe_audio(audio_media_id, audio_url)
                if not message:
                    await self.wa_client.send_text_message(
                        phone_number,
                        "Sorry, I couldn't understand your voice note. Please type your message instead."
                    )
                    return

            session = await session_manager.get_or_create_session(phone_number)

            sender_number = self.wa_client.sender
            if sender_number:
                campaign = await campaign_store.match_trigger(sender_number, message)
                if campaign:
                    await self.send_campaign_reply(phone_number, campaign, sender_number)
                    return

            flow_mode = await session_manager.get_flow_mode(phone_number)
            if message.strip().lower() in settings.ai_flow_keywords:
                    logger.info(f"[FLOW] {phone_number} asked for the assistant — switching to the AI flow")
                    await session_manager.set_flow_mode(phone_number, "ai")
                    await self.redirect_to_ai_flow(phone_number, message, session.session_id)
                    return
            if flow_mode == "embracebot":
                logger.info(f"[FLOW] {phone_number} is on embracebot flow — forwarding")
                await session_manager.set_flow_mode(phone_number, "embracebot")
                await self.forward_to_embracebot(phone_number, message, message_id)
                return
            if await session_manager.is_processing(session.session_id):
                logger.warning(f"Session {session.session_id} is already processing")
                return

            echo_status = await self._check_repeated_echo(phone_number, message)
            if echo_status == "reply":
                await self.wa_client.send_text_message(phone_number, settings.duplicate_message_reply)
                return
            if echo_status == "silent":
                return

            await session_manager.set_processing(session.session_id, True)
            
            try:
               
                
                chat_response = await chat_service.send_message(
                    session.session_id,
                    message
                )
                
                if not chat_response:
                    await self.wa_client.send_text_message(
                        phone_number,
                        "Sorry, we’re taking longer than expected to fetch the details. Please try again in a moment."
                    )
                    return
                
                logger.info(f"Chat response: {chat_response}")
                print(f"[DEBUG] Full chat_response: {chat_response}")

                logger.info(
                    f"[FLOW] {phone_number} handoff flags — "
                    f"customerAgent={chat_response.handoffToCustomerAgent} "
                    f"mainMenu={chat_response.handoffToMainMenu}"
                )
                
                if chat_response.handoffToCustomerAgent:
                    logger.info(f"[FLOW] handoffToCustomerAgent=True for {phone_number} — switching to embracebot flow and transferring to live customer agent")
                    await session_manager.set_flow_mode(phone_number, "embracebot")
                    signal = settings.agent_handoff_signal
                    info = chat_response.handoff_info or {}
                    if info.get("booking_id") and info.get("email"):
                        signal = f"{signal}|{info['booking_id']}|{info['email']}"
                    await self.forward_to_embracebot(phone_number, signal, message_id)
                    return

                
                await self.handle_chat_response(phone_number, chat_response, session.session_id)
                
            finally:
                
                await session_manager.set_processing(session.session_id, False)
        
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.wa_client.send_text_message(
                phone_number,
                "Sorry, we’re taking longer than expected to fetch the details. Please try again in a moment."
            )
            
            
            session = await session_manager.get_or_create_session(phone_number)
            await session_manager.set_processing(session.session_id, False)
    
    CAMPAIGN_CAPTION_LIMIT = 1024

    async def send_campaign_reply(self, phone_number: str, campaign: Dict[str, str], sender_number: str):
        text = campaign.get("message") or ""
        image_url = (campaign.get("image_url") or "").strip()

        if not image_url:
            await self.wa_client.send_text_message(phone_number, text)
            logger.info(f"[CAMPAIGN] Trigger matched — sent campaign reply to {phone_number} on {sender_number}")
            return

        caption_fits = len(text) <= self.CAMPAIGN_CAPTION_LIMIT
        caption = text if caption_fits else ""

        sent = await self.wa_client.send_image_with_caption(phone_number, image_url, caption)

        if not sent:
            logger.warning(
                f"[CAMPAIGN] Image send failed for {phone_number} on {sender_number} "
                f"(url={image_url}) — falling back to text only"
            )
            await self.wa_client.send_text_message(phone_number, text)
            return

        if not caption_fits:
            await asyncio.sleep(0.5)
            await self.wa_client.send_text_message(phone_number, text)

        logger.info(
            f"[CAMPAIGN] Trigger matched — sent campaign reply with image to "
            f"{phone_number} on {sender_number} (caption={'yes' if caption_fits else 'no'})"
        )

    async def forward_to_embracebot(self, phone_number: str, message: str, message_id: str):
        clean_number = phone_number.lstrip("+")

        payload = {
            "channel": "WABA",
            "appDetails": {"type": "LIVE"},
            "recipient": {},
            "events": {
                "eventType": "User initiated",
                "timestamp": str(int(time.time())),
                "date": datetime.now().strftime("%Y-%B-%d"),
            },
            "eventContent": {
                "message": {
                    "from": clean_number,
                    "id": message_id,
                    "text": {"body": message},
                    "to": self.wa_client.sender or settings.whatsapp_bot_phone_number,
                    "contentType": "text",
                    "messageType": "text",
                    "profileName": "",
                }
            },
            "to": settings.embracebot_company_id,
        }

        url = f"{settings.embracebot_base_url}/karix_whatsapp_webhook/{settings.embracebot_company_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                logger.info(f"[FLOW] Forwarded to embracebot ({url}), status: {response.status_code}")
        except Exception as e:
            logger.error(f"[FLOW] Failed to forward to embracebot: {str(e)}")


    async def handle_incoming_media(self, phone_number: str, message_id: str, media: Dict[str, Any]) -> bool:
        media_type = media.get("type", "image")
        caption = (media.get("caption") or "").strip()
        label = MEDIA_LABELS.get(media_type, "a file")

        flow_mode = await session_manager.get_flow_mode(phone_number)

        if flow_mode == "embracebot":
            await session_manager.set_flow_mode(phone_number, "embracebot")

            file_link = await self.resolve_media_link(media)
            if file_link:
                await self.forward_media_to_embracebot(phone_number, message_id, media, file_link)
            else:
                logger.error(f"[MEDIA] Could not build a link for {media_type} from {phone_number}")
                await self.forward_to_embracebot(
                    phone_number,
                    caption or f"[Customer sent {label} that could not be attached — please ask them to resend it]",
                    message_id,
                )
            return True

        if caption:
            logger.info(f"[MEDIA] {media_type} with caption on AI flow — using caption as the message")
            return False

        logger.info(f"[MEDIA] {media_type} from {phone_number} on AI flow — media not supported by the assistant")
        await self.wa_client.send_text_message(phone_number, media_not_supported_reply())
        return True

    async def resolve_media_link(self, media: Dict[str, Any]) -> str:
        if media.get("url"):
            return media["url"]

        media_id = media.get("id")
        if not media_id:
            return ""

        if not settings.public_base_url:
            logger.error("[MEDIA] PUBLIC_BASE_URL is not set — cannot expose media to the agent dashboard")
            return ""

        path = self.wa_client.media_proxy_path(media_id)
        return f"{settings.public_base_url.rstrip('/')}{path}"

    async def forward_media_to_embracebot(
        self,
        phone_number: str,
        message_id: str,
        media: Dict[str, Any],
        file_link: str,
    ):
        clean_number = phone_number.lstrip("+")
        media_type = media.get("type", "image")
        caption = media.get("caption", "") or ""

        media_object = {
            "fileLink": file_link,
            "url": file_link,
            "caption": caption,
            "fileName": media.get("filename", "") or f"{media_type}",
            "mimeType": media.get("mime_type", "") or "",
        }

        message_payload = {
            "from": clean_number,
            "id": message_id,
            "to": self.wa_client.sender or settings.whatsapp_bot_phone_number,
            "contentType": "ATTACHMENT",
            "attachmentType": media_type,
            "messageType": media_type,
            "text": {"body": file_link},
            "profileName": "",
        }
        message_payload["document" if media_type == "document" else "image"] = media_object

        payload = {
            "channel": "WABA",
            "appDetails": {"type": "LIVE"},
            "recipient": {},
            "events": {
                "eventType": "User initiated",
                "timestamp": str(int(time.time())),
                "date": datetime.now().strftime("%Y-%B-%d"),
            },
            "eventContent": {"message": message_payload},
            "to": settings.embracebot_company_id,
        }

        url = f"{settings.embracebot_base_url}/karix_whatsapp_webhook/{settings.embracebot_company_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                logger.info(
                    f"[MEDIA] Forwarded {media_type} from {phone_number} to embracebot "
                    f"({url}), status: {response.status_code}, link: {file_link}"
                )
        except Exception as e:
            logger.error(f"[MEDIA] Failed to forward {media_type} to embracebot: {str(e)}")

    async def redirect_to_ai_flow(self, phone_number: str, message: str, session_id: str):
        try:
            chat_response = await chat_service.send_message(
                session_id,
                message,
            )
            if chat_response:
                await self.handle_chat_response(phone_number, chat_response, session_id)
        except Exception as e:
            logger.error(f"Error redirecting to AI flow: {str(e)}", exc_info=True)

    async def handle_chat_response(self, phone_number: str, chat_response: ChatResponse, session_id: str):
        try:
            payload = chat_response.whatsapp_response
            if not payload:
                await self._send_plain_response(phone_number, chat_response.response_text)
                return

            response_type = (payload.get("type") or "text").strip().lower()
            handler = self.RESPONSE_HANDLERS.get(response_type)
            if handler is None:
                logger.warning(f"Unknown whatsapp_response type {response_type!r} — sending text")
                await self._send_plain_response(phone_number, chat_response.response_text)
                return

            intro = payload.get("intro_text") or ""
            if intro:
                await self.wa_client.send_text_message(phone_number, intro)
                await asyncio.sleep(0.5)

            await getattr(self, handler)(phone_number, payload, chat_response)
        except Exception as e:
            logger.error(f"Error handling chat response: {str(e)}", exc_info=True)

    RESPONSE_HANDLERS = {
        "text": "_send_text_payload",
        "cta": "_send_cta_payload",
        "buttons": "_send_buttons_payload",
        "list": "_send_list_payload",
        "image": "_send_image_payload",
        "document": "_send_document_payload",
    }

    def _payload_text(self, payload: Dict[str, Any], chat_response: ChatResponse) -> str:
        text = payload.get("text") or payload.get("response_text") or ""
        if text:
            return text
        friendly = chat_service.extract_friendly_text(chat_response.response_text)
        return friendly or chat_service.clean_html_tags(chat_response.response_text)

    async def _send_plain_response(self, phone_number: str, raw: str):
        friendly_text = chat_service.extract_friendly_text(raw)
        link = chat_service.extract_link(raw)
        if link:
            btn_text, btn_url = link
            body = chat_service.clean_html_tags(friendly_text or raw)
            await self.wa_client.send_interactive_button(phone_number, body, btn_text, btn_url)
            return
        text_to_send = friendly_text or chat_service.clean_html_tags(raw)
        if text_to_send:
            await self.wa_client.send_text_message(phone_number, text_to_send)

    async def _send_text_payload(self, phone_number: str, payload: Dict[str, Any], chat_response: ChatResponse):
        text = self._payload_text(payload, chat_response)
        if text:
            await self.wa_client.send_text_message(phone_number, text)

    async def _send_cta_payload(self, phone_number: str, payload: Dict[str, Any], chat_response: ChatResponse):
        text = self._payload_text(payload, chat_response)
        url = payload.get("url") or ""
        if not url:
            await self.wa_client.send_text_message(phone_number, text)
            return
        await self.wa_client.send_interactive_button(phone_number, text, payload.get("button") or "Open", url)

    async def _send_buttons_payload(self, phone_number: str, payload: Dict[str, Any], chat_response: ChatResponse):
        text = self._payload_text(payload, chat_response)
        buttons = [b for b in payload.get("buttons") or [] if b.get("id") and b.get("title")][:3]
        if not buttons:
            await self.wa_client.send_text_message(phone_number, text)
            return
        await self.wa_client.send_interactive_reply_button(phone_number, text, buttons)

    async def _send_list_payload(self, phone_number: str, payload: Dict[str, Any], chat_response: ChatResponse):
        text = self._payload_text(payload, chat_response)
        sections = payload.get("sections") or []
        if not sections:
            await self.wa_client.send_text_message(phone_number, text)
            return
        await self.wa_client.send_list_message(
            phone_number, payload.get("header") or "", text, payload.get("footer") or "", sections
        )

    async def _send_image_payload(self, phone_number: str, payload: Dict[str, Any], chat_response: ChatResponse):
        text = self._payload_text(payload, chat_response)
        url = payload.get("url") or ""
        if not url or not await self.wa_client.send_image_with_caption(phone_number, url, text[:1024]):
            await self.wa_client.send_text_message(phone_number, text)

    async def _send_document_payload(self, phone_number: str, payload: Dict[str, Any], chat_response: ChatResponse):
        text = self._payload_text(payload, chat_response)
        url = payload.get("url") or ""
        if not url:
            await self.wa_client.send_text_message(phone_number, text)
            return
        await self.wa_client.send_document(phone_number, url, caption=text, filename=payload.get("filename") or "document.pdf")

