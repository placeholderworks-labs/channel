from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar

from pydantic import BaseModel, Field

from pw_sdk.utils import phone


class TelephonyError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class DialRequest(BaseModel):
    phone_e164: str
    reference_id: str
    customer_name: str = ""
    task_id: int | None = None
    idempotency_key: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DialResult(BaseModel):
    provider_ref: str
    session_id: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CallRef(BaseModel):
    call_id: str = ""
    ref_id: str = ""
    call_uuid: str = ""


class TelephonyProvider(ABC):
    name: ClassVar[str]
    supports_outbound: ClassVar[bool] = True
    supports_transfer: ClassVar[bool] = False

    def enabled(self) -> bool:
        from pw_channel import config

        return bool(getattr(config, f"ENABLE_{self.name.upper()}", False))

    def stream_path(self) -> str:
        from pw_channel import config

        return getattr(config, f"{self.name.upper()}_WS_PATH", f"/ws/{self.name}")

    def dial_number(self, e164: str) -> str:
        country = phone.country_of(e164) or "IN"
        return phone.national(e164, country) if country == "IN" else phone.digits(e164)

    @abstractmethod
    def websocket_endpoint(self) -> Callable:
        pass

    async def place_call(self, request: DialRequest) -> DialResult:
        raise TelephonyError(f"{self.name} cannot place outbound calls", retryable=False)

    async def transfer(self, call: CallRef, destination: str) -> dict:
        raise TelephonyError(f"{self.name} cannot transfer calls", retryable=False)

    async def hangup(self, call: CallRef) -> None:
        return None

    async def live_calls(self) -> set[str] | None:
        return None

    def register_routes(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def status(self) -> dict:
        return {"name": self.name, "enabled": self.enabled(), "path": self.stream_path(),
                "outbound": self.supports_outbound, "transfer": self.supports_transfer}
