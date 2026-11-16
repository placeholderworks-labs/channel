import logging

from pw_channel import config
from pw_channel.channels.voice.tts.base import TTSProvider
from pw_sdk.registry import ProviderRegistry

logger = logging.getLogger(__name__)

TTS: ProviderRegistry[TTSProvider] = ProviderRegistry("tts", group="pw.tts")
TTS.add("gemini", "pw_channel.channels.voice.tts.gemini:GeminiTTS")
TTS.add("sarvam", "pw_channel.channels.voice.tts.sarvam:SarvamTTS")
TTS.add("openai", "pw_channel.channels.voice.tts.openai:OpenAITTS")
TTS.add("murf", "pw_channel.channels.voice.tts.murf:MurfTTS")

_instances: dict[str, TTSProvider] = {}


def provider(name: str | None = None) -> TTSProvider:
    key = (name or config.TTS_PROVIDER).strip().lower()
    if key not in _instances:
        _instances[key] = TTS.create(key)
    return _instances[key]


def build_tts_service(overrides: dict | None = None):
    overrides = overrides or {}
    service = provider(overrides.get("provider") or None).build(overrides)
    service._pw_tts_provider = (overrides.get("provider") or config.TTS_PROVIDER).strip().lower()
    return service


async def warm_up_tts() -> None:
    await provider().warmup()


def apply_tts_locale(service, locale: str) -> bool:
    return provider(getattr(service, "_pw_tts_provider", None)).set_language(service, locale)
