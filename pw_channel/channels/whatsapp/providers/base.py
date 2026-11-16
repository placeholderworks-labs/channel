from abc import ABC, abstractmethod
from typing import Any, ClassVar

from fastapi import Request

from pw_channel.channels.whatsapp.models import WhatsAppIncomingMessage


class WhatsAppProvider(ABC):
    name: ClassVar[str]
    webhook_path: ClassVar[str]
    sender: str = ""

    @property
    def media_download_headers(self) -> dict | None:
        return None

    @property
    def media_auth(self) -> tuple[str, str] | None:
        return None

    def media_proxy_path(self, media_id: str) -> str:
        return f"/api/channel/whatsapp/media/{self.name}/{self.sender}/{media_id}"

    def routing(self, payload: dict) -> tuple[str, str]:
        return "", ""

    def authorized(self, request: Request) -> bool:
        return True

    def verify(self, request: Request) -> str | None:
        return None

    def is_inbound(self, payload: dict) -> bool:
        return True

    @abstractmethod
    def parse_webhook_message(self, payload: dict) -> WhatsAppIncomingMessage | None:
        pass

    @abstractmethod
    async def mark_as_read(self, message_id: str, to: str = "") -> bool:
        pass

    @abstractmethod
    async def get_media_url(self, media_id: str) -> str | None:
        pass

    @abstractmethod
    async def download_media(self, media_id: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    async def send_text_message(self, to: str, text: str) -> bool:
        pass

    @abstractmethod
    async def send_image_with_caption(self, to: str, image_url: str, caption: str) -> bool:
        pass

    @abstractmethod
    async def send_document(self, to: str, file_url: str, caption: str = "", filename: str = "document") -> bool:
        pass

    @abstractmethod
    async def send_interactive_button(self, to: str, body_text: str, button_text: str, button_url: str) -> bool:
        pass

    @abstractmethod
    async def send_interactive_reply_button(self, to: str, body_text: str, buttons: list[dict[str, str]]) -> bool:
        pass

    @abstractmethod
    async def send_interactive_cta_button_with_id(self, to: str, body_text: str, button_text: str, button_url: str) -> str | None:
        pass

    @abstractmethod
    async def send_list_message(self, to: str, header: str, body: str, footer: str, sections: list) -> bool:
        pass

    @abstractmethod
    async def send_template_message(self, to: str, template_name: str, language_code: str, components: list[dict[str, Any]]) -> bool:
        pass
