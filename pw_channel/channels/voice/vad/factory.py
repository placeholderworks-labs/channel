import logging
import os

from pw_channel import config
from pw_channel.channels.voice.vad.base import VADProvider
from pw_sdk.registry import ProviderRegistry

logger = logging.getLogger(__name__)

VAD: ProviderRegistry[VADProvider] = ProviderRegistry("vad", group="pw.vad")
VAD.add("silero", "pw_channel.channels.voice.vad.silero:SileroVAD")


def resolve_vad_params(channel: str | None = None) -> dict[str, float]:
    params = {
        "confidence": config.VAD_CONFIDENCE,
        "start_secs": config.VAD_START_SECS,
        "stop_secs": config.VAD_STOP_SECS,
        "min_volume": config.VAD_MIN_VOLUME,
    }
    params.update(config.VAD_CHANNEL_OVERRIDES.get(channel or "", {}))
    return params


def build_vad_analyzer(channel: str | None = None):
    params = resolve_vad_params(channel)
    name = os.getenv("VAD_PROVIDER", "silero")
    logger.info(f"[{channel or 'default'}] VAD {name} " + " ".join(f"{k}={v}" for k, v in params.items()))
    return VAD.create(name).build(params)
