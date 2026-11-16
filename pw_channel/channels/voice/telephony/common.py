import re
import uuid

from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

from pw_channel import config
from pw_channel.channels.voice.pipeline.builder import run_voice_pipeline
from pw_channel.channels.voice.states import CallContext

__all__ = [
    "CallContext",
    "build_websocket_params",
    "run_voice_pipeline",
    "voice_user_type",
    "mint_chat_session_id",
]

_NON_DIGIT_RULE = re.compile(r"\D")


def build_websocket_params(serializer, **overrides) -> FastAPIWebsocketParams:
    return FastAPIWebsocketParams(
        serializer=serializer,
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        **overrides,
    )


def voice_user_type(channel: str) -> str:
    override = (config.PW_CHAT_USER_TYPES_BY_CHANNEL.get(channel) or "").strip()
    if override:
        return override
    if channel == "website":
        return config.PW_CHAT_USER_TYPE_WEBSITE
    return config.PW_CHAT_USER_TYPE_PHONE


def mint_chat_session_id(user_type: str, *, phone_number: str = "") -> str:
    digits = _NON_DIGIT_RULE.sub("", phone_number or "")
    if digits:
        return f"voice-{digits}"
    return f"{user_type}-{uuid.uuid4()}"
