import logging

from pw_channel import config
from pw_channel.channels.voice.stt.base import STTProvider
from pw_sdk.registry import ProviderRegistry

logger = logging.getLogger(__name__)

STT: ProviderRegistry[STTProvider] = ProviderRegistry("stt", group="pw.stt")
STT.add("deepgram", "pw_channel.channels.voice.stt.deepgram:DeepgramSTT")
STT.add("deepgram_flux", "pw_channel.channels.voice.stt.deepgram_flux:DeepgramFluxSTT")

_instances: dict[str, STTProvider] = {}


def provider(name: str) -> STTProvider:
    if name not in _instances:
        _instances[name] = STT.create(name)
    return _instances[name]


def resolve_stt_params(channel: str | None = None) -> dict:
    overrides = config.STT_CHANNEL_OVERRIDES.get(channel or "", {})
    name = (overrides.get("provider") or config.STT_PROVIDER).strip().lower()
    model = provider(name).model_for(overrides.get("model") or config.STT_MODEL)
    return {"provider": name, "model": model, "language": overrides.get("language") or config.STT_LANGUAGE}


def uses_external_turns(channel: str | None = None) -> bool:
    return provider(resolve_stt_params(channel)["provider"]).external_turns


def build_stt_service(channel: str | None = None):
    params = resolve_stt_params(channel)
    logger.info(f"[{channel or 'default'}] STT provider={params['provider']} model={params['model']} language={params['language']}")
    return provider(params["provider"]).build(params, channel)


async def warm_up_stt() -> None:
    for name in sorted(set(config.STT_PROVIDER_BY_CHANNEL.values())):
        await provider(name).warmup()
