from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from pw_sdk.contracts.outcomes import TaskOutcome
from pw_sdk import CustomerRecord


class ChannelTask(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    task_id: int
    journey_id: int
    key: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    record: CustomerRecord
    intake: str = ""
    agent: str = ""
    attempt: int = 1
    idempotency_key: str


class ChannelResult(BaseModel):
    state: Literal["done", "waiting"]
    outcome: TaskOutcome | None = None
    provider_ref: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def done(cls, outcome: TaskOutcome, provider_ref: str | None = None, **detail) -> "ChannelResult":
        return cls(state="done", outcome=outcome, provider_ref=provider_ref, detail=detail)

    @classmethod
    def waiting(cls, provider_ref: str | None = None, outcome: TaskOutcome | None = None, **detail) -> "ChannelResult":
        return cls(state="waiting", outcome=outcome, provider_ref=provider_ref, detail=detail)


class ChannelError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class Channel(ABC):
    name: ClassVar[str]
    actions: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    async def execute(self, task: ChannelTask) -> ChannelResult:
        pass

    def routes(self) -> list[APIRouter]:
        return []

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def supports(self, action: str) -> bool:
        return not self.actions or action in self.actions
