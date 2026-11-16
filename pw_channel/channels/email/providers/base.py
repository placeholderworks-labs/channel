from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field


class EmailMessageIn(BaseModel):
    to: str
    subject: str
    text: str
    html: str = ""
    sender_name: str = ""
    inline_images: dict[str, bytes] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)


class EmailResult(BaseModel):
    ok: bool
    message_id: str = ""
    error: str = ""


class EmailProvider(ABC):
    name: ClassVar[str]

    @abstractmethod
    def configured(self) -> bool:
        pass

    @abstractmethod
    def send(self, message: EmailMessageIn) -> EmailResult:
        pass
