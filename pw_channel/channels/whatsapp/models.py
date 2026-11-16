from pydantic import BaseModel, Field, AliasChoices
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_type: str = "whatsapp"
    phone_number: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response_text: str
    response_html: Optional[str] = None
    handoffToMainMenu: bool = False
    handoffToCustomerAgent: bool = False
    whatsapp_response: Optional[Dict[str, Any]] = None
    handoff_info: Optional[Dict[str, Any]] = None


class WhatsAppIncomingMessage(BaseModel):
    from_number: str
    message_text: str
    message_id: str
    audio_media_id: Optional[str] = None
    audio_url: Optional[str] = None

    media_type: Optional[str] = None
    media_id: Optional[str] = None
    media_url: Optional[str] = None
    media_caption: Optional[str] = None
    media_filename: Optional[str] = None
    media_mime_type: Optional[str] = None

    @property
    def media(self) -> Optional[Dict[str, Any]]:
        if not self.media_type:
            return None
        return {
            "type": self.media_type,
            "id": self.media_id or "",
            "url": self.media_url or "",
            "caption": self.media_caption or "",
            "filename": self.media_filename or "",
            "mime_type": self.media_mime_type or "",
        }


@dataclass
class WhatsAppOutgoingMessage:
    message_type: str  
    data: Dict[str, Any]


class Session(BaseModel):
    session_id: str
    phone_number: str
    is_processing: bool = False
    last_activity: float
    message_count: int = 0
