import logging

from pw_channel import config
from pw_channel.channels.voice.tts.base import TTSProvider

logger = logging.getLogger(__name__)


class OpenAITTS(TTSProvider):
    name = "openai"
    voice_setting = "OPENAI_TTS_VOICE"
    model_setting = "OPENAI_TTS_MODEL"
    key_setting = "OPENAI_TTS_API_KEY"

    def build(self, overrides: dict):
        from pipecat.services.openai.tts import OpenAITTSService

        if not config.OPENAI_TTS_API_KEY:
            raise ValueError("OPENAI_TTS_API_KEY is required for the openai voice")
        return OpenAITTSService(
            api_key=config.OPENAI_TTS_API_KEY,
            sample_rate=self.pick(overrides, "sample_rate", config.OPENAI_TTS_SAMPLE_RATE),
            settings=OpenAITTSService.Settings(
                model=self.pick(overrides, "model", config.OPENAI_TTS_MODEL),
                voice=self.pick(overrides, "voice", config.OPENAI_TTS_VOICE),
                instructions=config.OPENAI_TTS_INSTRUCTIONS or None,
                speed=config.OPENAI_TTS_SPEED,
            ),
        )

    async def warmup(self) -> None:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=config.OPENAI_TTS_API_KEY)
            async with client.audio.speech.with_streaming_response.create(
                input="Warming up.", model=config.OPENAI_TTS_MODEL, voice=config.OPENAI_TTS_VOICE, response_format="pcm",
            ) as response:
                async for _ in response.iter_bytes(4096):
                    pass
            await client.close()
            logger.info("TTS warm-up complete (openai)")
        except Exception:
            logger.exception("TTS warm-up failed (openai); the first call may be slow")
