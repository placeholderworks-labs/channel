import logging

from pw_channel import config
from pw_channel.channels.voice.stt.base import STTProvider
from pw_channel.channels.voice.stt.flux_ttft import attach_ttft_metrics

logger = logging.getLogger(__name__)

MULTILINGUAL_MODEL = "flux-general-multi"


def language_hints(language: str, model: str) -> list | None:
    from pipecat.transcriptions.language import Language

    if model != MULTILINGUAL_MODEL:
        return None
    hints = {"multi": (Language.HI, Language.EN), "hi": (Language.HI, Language.EN), "en": (Language.EN,)}
    key = (language or "").strip().lower()
    if key in hints:
        return list(hints[key])
    try:
        return [Language(key)]
    except ValueError:
        logger.warning(f"STT_LANGUAGE={language!r} has no Flux hint; Flux will auto-detect")
        return None


class DeepgramFluxSTT(STTProvider):
    name = "deepgram_flux"
    external_turns = True

    def model_for(self, model: str) -> str:
        return model if model.startswith("flux-") else config.STT_FLUX_MODEL

    def build(self, params: dict, channel: str | None):
        from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService

        if not config.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is required for the deepgram_flux transcriber")
        settings: dict = {
            "model": params["model"],
            "eot_threshold": config.FLUX_EOT_THRESHOLD,
            "eot_timeout_ms": config.FLUX_EOT_TIMEOUT_MS,
        }
        hints = language_hints(params["language"], params["model"])
        if hints:
            settings["language_hints"] = hints
        service = DeepgramFluxSTTService(
            api_key=config.DEEPGRAM_API_KEY,
            should_interrupt=config.FLUX_SHOULD_INTERRUPT,
            settings=DeepgramFluxSTTService.Settings(**settings),
        )
        attach_ttft_metrics(service)
        return service

    async def warmup(self) -> None:
        try:
            from websockets.asyncio.client import connect

            url = f"wss://api.deepgram.com/v2/listen?model={config.STT_FLUX_MODEL}&sample_rate=16000&encoding=linear16"
            async with connect(url, additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"}):
                pass
            logger.info(f"STT warm-up complete (deepgram_flux {config.STT_FLUX_MODEL})")
        except Exception:
            logger.exception("STT warm-up failed (deepgram_flux); the first call may be slow")
