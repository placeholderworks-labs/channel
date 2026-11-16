import logging

from fastapi import APIRouter

from pw_channel import config
from pw_channel.channels.voice.schema import (
    CallDisposition,
    HealthResponse,
)
from pw_channel.channels.voice.calls.logger import log_call_disposition

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    from pw_channel.channels.voice.telephony import registry as telephony

    active_routes = [provider.stream_path() for provider in telephony.all_providers() if provider.enabled()]

    return HealthResponse(
        status="ok",
        channel_routes=active_routes,
        stt_provider=config.STT_PROVIDER,
        llm_provider=f"pw-llm-layer({config.PW_CHAT_USER_TYPE_PHONE}/{config.PW_CHAT_USER_TYPE_WEBSITE})",
        tts_provider=config.TTS_PROVIDER,
    )


@router.post("/api/disposition")
async def receive_disposition(disposition: CallDisposition):
    await log_call_disposition(disposition)
    return {"success": True}
