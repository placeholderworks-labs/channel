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
    "sticker": "image",
}


class WhatsAppClient(WhatsAppProvider):
    name = "meta"
    webhook_path = "/api/channel/whatsapp/webhook"

    def __init__(self):
        self.base_url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}"
        self.headers = {
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json"
        }
        self.timeout = 60.0
        self.sender = settings.meta_number

    @property
    def media_download_headers(self) -> dict:
        return self.headers

    def routing(self, payload: dict) -> tuple[str, str]:
        try:
            value = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}) or {}
        except (AttributeError, IndexError, TypeError):
            return "", ""
        message = (value.get("messages") or [{}])[0]
        to = (value.get("metadata") or {}).get("display_phone_number", "")
        return str(message.get("from", "")).lstrip("+"), str(to).lstrip("+")

    def verify(self, request) -> str | None:
        params = request.query_params
        if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == settings.webhook_verify_token:
            return params.get("hub.challenge")
        return None
    
    def parse_webhook_message(self, payload: dict) -> Optional[WhatsAppIncomingMessage]:
        try:
            entry = payload.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            
            if not messages:
                return None
            
            message = messages[0]
            message_type = message.get("type", "")
            
           
            if message_type == "text":
                return WhatsAppIncomingMessage(
                    from_number=message.get("from", ""),
                    message_text=message.get("text", {}).get("body", ""),
                    message_id=message.get("id", "")
                )

            if message_type == "audio":
                media_id = message.get("audio", {}).get("id", "")
                return WhatsAppIncomingMessage(
                    from_number=message.get("from", ""),
                    message_text="",
                    message_id=message.get("id", ""),
                    audio_media_id=media_id,
                )

            if message_type == "interactive":
                interactive = message.get("interactive", {})
                interactive_type = interactive.get("type", "")
                
                if interactive_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = button_reply.get("id", "")
                    button_title = button_reply.get("title", "")
                    
                    return WhatsAppIncomingMessage(
                        from_number=message.get("from", ""),
                        message_text=button_id,
                        message_id=message.get("id", "")
                    )

            if message_type in MEDIA_TYPE_MAP:
                media = message.get(message_type, {}) or {}
                media_id = media.get("id", "")
                if not media_id:
                    logger.warning(f"{message_type} message {message.get('id', '')} has no media id — dropping")
                    return None

                caption = media.get("caption", "") or ""
                return WhatsAppIncomingMessage(
                    from_number=message.get("from", ""),
                    message_text=caption,
                    message_id=message.get("id", ""),
                    media_type=MEDIA_TYPE_MAP[message_type],
                    media_id=media_id,
                    media_caption=caption,
                    media_filename=media.get("filename", "") or "",
                    media_mime_type=media.get("mime_type", "") or "",
                )

            logger.info(f"Ignoring message type: {message_type}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing webhook: {str(e)}")
            return None
    
    async def mark_as_read(self, message_id: str, to: str = "") -> bool:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {
                "type": "text"
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Error marking message as read: {str(e)}")
            return False
    
    async def get_media_url(self, media_id: str) -> Optional[str]:
        url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{media_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json().get("url")
        except Exception as e:
            logger.error(f"Error resolving media URL for {media_id}: {e}")
            return None

    async def download_media(self, media_id: str) -> Optional[Dict[str, Any]]:
        media_url = await self.get_media_url(media_id)
        if not media_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    media_url,
                    headers={"Authorization": self.headers["Authorization"]}
                )
                response.raise_for_status()
                return {
                    "content": response.content,
                    "content_type": response.headers.get("content-type", "application/octet-stream"),
                }
        except Exception as e:
            logger.error(f"Error downloading media {media_id}: {e}")
            return None

    async def send_text_message(self, to: str, text: str) -> bool:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text}
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Text message sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending text message: {str(e)}")
            return False
        
      
    async def send_image_with_caption(self, to: str, image_url: str, caption: str) -> bool:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption
            }
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Image with caption sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending image with caption: {str(e)}")
            return False

    
    async def send_interactive_button(
        self,
        to: str,
        body_text: str,
        button_text: str,
        button_url: str
    ) -> bool:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body_text},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": button_text[:20],  
                        "url": button_url
                    }
                }
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Interactive CTA button sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending interactive button: {str(e)}")
            return False
    
    async def send_interactive_reply_button(
        self,
        to: str,
        body_text: str,
        buttons: List[Dict[str, str]]
    ) -> bool:
        url = f"{self.base_url}/messages"
        
        
        formatted_buttons = []
        for btn in buttons[:3]:  
            formatted_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"][:256],  
                    "title": btn["title"][:20]  
                }
            })
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": formatted_buttons
                }
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Interactive reply button sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending interactive reply button: {str(e)}")
            logger.error(f"Payload: {payload}")
            return False
        
    async def send_interactive_cta_button_with_id(
        self,
        to: str,
        body_text: str,
        button_text: str,
        button_url: str
    ) -> Optional[str]:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body_text},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": button_text[:20],
                        "url": button_url
                    }
                }
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                
                response_data = response.json()
                message_id = response_data.get("messages", [{}])[0].get("id")
                
                logger.info(f"Interactive CTA button sent to {to}, msg_id: {message_id}")
                return message_id
        except Exception as e:
            logger.error(f"Error sending interactive CTA button: {str(e)}")
            return None
    
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str,
        components: List[Dict[str, Any]]
    ) -> bool:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Template message sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending template message: {str(e)}")
            logger.error(f"Template: {template_name}, Components: {components}")
            return False

    async def send_document(self, to: str, file_url: str, caption: str = "", filename: str = "document") -> bool:
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {
                "link": file_url,
                "caption": caption,
                "filename": filename
            }
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Document sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending document: {str(e)}")
            return False

    async def send_list_message(
        self,
        to: str,
        header: str,
        body: str,
        footer: str,
        sections: list
    ) -> bool:
        url = f"{self.base_url}/messages"
        formatted_sections = []
        for section in sections:
            rows = []
            for row in section.get("rows", []):
                rows.append({
                    "id": str(row.get("id", row.get("rowId", "")))[:256],
                    "title": str(row.get("title", ""))[:24],
                    "description": str(row.get("description", ""))[:72]
                })
            formatted_sections.append({
                "title": str(section.get("title", ""))[:24],
                "rows": rows
            })
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": header},
                "body": {"text": body},
                "footer": {"text": footer},
                "action": {
                    "button": "Select",
                    "sections": formatted_sections
                }
            }
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"List message sent to {to}")
                return True
        except Exception as e:
            logger.error(f"Error sending list message: {str(e)}")
            return False


