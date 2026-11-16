from pydantic import BaseModel


class CallDisposition(BaseModel):
    call_id: str
    channel: str
    reference_id: str | None = None
    phone_no: str | None = None
    status: str
    duration_secs: float | None = None
    transcript_turns: int = 0
    ended_reason: str | None = None


class HealthResponse(BaseModel):
    status: str
    channel_routes: list[str]
    stt_provider: str
    llm_provider: str
    tts_provider: str
