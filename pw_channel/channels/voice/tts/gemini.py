import logging

from pw_channel import config
from pw_channel.channels.voice.tts.base import TTSProvider

logger = logging.getLogger(__name__)


class GeminiTTS(TTSProvider):
    name = "gemini"
    voice_setting = "TTS_VOICE"
    model_setting = "TTS_MODEL"
    key_setting = "GOOGLE_API_KEY"

    def build(self, overrides: dict):
        from pipecat.services.google.tts import GeminiTTSService

        if not config.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required for the gemini voice")
        return GeminiTTSService(
            api_key=config.GOOGLE_API_KEY,
            sample_rate=self.pick(overrides, "sample_rate", config.TTS_SAMPLE_RATE),
            settings=GeminiTTSService.Settings(
                model=self.pick(overrides, "model", config.TTS_MODEL),
                voice=self.pick(overrides, "voice", config.TTS_VOICE),
            ),
        )

    async def warmup(self) -> None:
        try:
            import google.genai as genai

            client = genai.Client(api_key=config.GOOGLE_API_KEY)
            speech = genai.types.SpeechConfig(voice_config=genai.types.VoiceConfig(
                prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(voice_name=config.TTS_VOICE)))
            response = await client.aio.models.generate_content_stream(
                model=config.TTS_MODEL, contents="Warming up.",
                config=genai.types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=speech),
            )
            async for _ in response:
                pass
            await client.aio.aclose()
            logger.info("TTS warm-up complete (gemini)")
        except Exception:
            logger.exception("TTS warm-up failed (gemini); the first call may be slow")
