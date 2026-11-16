import httpx
import logging
import re
from typing import Optional
from pw_channel.channels.whatsapp.settings import settings
from pw_channel.channels.whatsapp.models import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


class ChatServiceClient:
    
    def __init__(self):
        self.endpoint = settings.chat_service_endpoint
        self.timeout = 65.0
    
    async def send_message(self, session_id: str, message: str) -> Optional[ChatResponse]:
        phone_number = session_id[3:] if session_id.startswith("wa+") else None
        payload = ChatRequest(
            session_id=session_id,
            message=message,
            user_type="whatsapp",
            phone_number=phone_number
        )
        
        headers = {"Content-Type": "application/json", "User-Agent": "pw-channel-whatsapp"}
        if settings.brain_api_token:
            headers["X-Api-Token"] = settings.brain_api_token
        
        logger.info(f"Calling chat service for session: {session_id}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload.model_dump(),
                    headers=headers
                )
                response.raise_for_status()
                
                data = response.json()
                chat_response = ChatResponse(**data)
                
                logger.info(f"Chat service response received for: {session_id}")
                logger.debug(f"Response text: {chat_response.response_text[:100]}...")
                
                return chat_response
                
        except httpx.TimeoutException:
            logger.error(f"Timeout calling chat service for: {session_id}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from chat service: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error calling chat service: {str(e)}")
            return None
    
    @staticmethod
    def extract_link(response_text: str):
        if not response_text:
            return None
        match = re.search(r'<a\s+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', response_text, re.IGNORECASE)
        if match:
            return match.group(2).strip() or "Open Link", match.group(1).strip()
        return None

    @staticmethod
    def extract_friendly_text(response_text: str) -> str:
        if not response_text:
            return ""
        
        match = re.search(r'<FRIENDLY_TEXT>(.*?)</FRIENDLY_TEXT>', response_text, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        return ""
    
    @staticmethod
    def clean_html_tags(text: str) -> str:
        if not text:
            return ""
        
        text = re.sub(r'<a\s+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', r'\2 (\1)', text)
        
        text = re.sub(r'<(?!/?(?:FRIENDLY_TEXT|DESCRIPTIVE_TEXT)\b)[^>]+>', '', text)

        text = re.sub(r'</?(?:FRIENDLY_TEXT|DESCRIPTIVE_TEXT)\b[^>]*>', '', text, flags=re.IGNORECASE)

        text = re.sub(r'\s+', ' ', text).strip()
        
        return text


chat_service = ChatServiceClient()
