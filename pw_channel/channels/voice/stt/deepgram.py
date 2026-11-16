import logging

from pw_channel import config
from pw_channel.channels.voice.stt.base import STTProvider

logger = logging.getLogger(__name__)


class DeepgramSTT(STTProvider):
    name = "deepgram"

    def build(self, params: dict, channel: str | None):
        from pipecat.services.deepgram.stt import DeepgramSTTService

        if not config.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is required for the deepgram transcriber")
        return DeepgramSTTService(
            api_key=config.DEEPGRAM_API_KEY,
            settings=DeepgramSTTService.Settings(
                model=params["model"], language=params["language"], smart_format=True, punctuate=True, interim_results=True,
            ),
        )

    async def warmup(self) -> None:
        try:
            from deepgram import AsyncDeepgramClient

            client = AsyncDeepgramClient(api_key=config.DEEPGRAM_API_KEY)
            async with client.listen.v1.connect(model=config.STT_MODEL, encoding="linear16", sample_rate="16000", channels="1"):
                pass
            logger.info("STT warm-up complete (deepgram)")
        except Exception:
            logger.exception("STT warm-up failed (deepgram); the first call may be slow")
