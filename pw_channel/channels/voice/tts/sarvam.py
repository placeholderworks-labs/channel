import logging

from pw_channel import config
from pw_channel.channels.voice.tts.base import TTSProvider
from pw_sdk.utils import http

logger = logging.getLogger(__name__)


class SarvamTTS(TTSProvider):
    name = "sarvam"
    voice_setting = "SARVAM_TTS_VOICE"
    model_setting = "SARVAM_TTS_MODEL"
    key_setting = "SARVAM_API_KEY"

    def build(self, overrides: dict):
        from pipecat.services.sarvam.tts import SarvamTTSService

        if not config.SARVAM_API_KEY:
            raise ValueError("SARVAM_API_KEY is required for the sarvam voice")
        return SarvamTTSService(
            api_key=config.SARVAM_API_KEY,
            sample_rate=self.pick(overrides, "sample_rate", config.SARVAM_TTS_SAMPLE_RATE),
            settings=SarvamTTSService.Settings(
                model=self.pick(overrides, "model", config.SARVAM_TTS_MODEL),
                voice=self.pick(overrides, "voice", config.SARVAM_TTS_VOICE),
                language=config.SARVAM_TTS_LANGUAGE,
                pace=config.SARVAM_TTS_PACE,
            ),
        )

    async def warmup(self) -> None:
        try:
            await http.request("POST", "https://api.sarvam.ai/text-to-speech", retries=0, timeout=20.0, json={
                "text": "Warming up.", "target_language_code": config.SARVAM_TTS_LANGUAGE,
                "speaker": config.SARVAM_TTS_VOICE, "sample_rate": config.SARVAM_TTS_SAMPLE_RATE,
                "enable_preprocessing": False, "model": config.SARVAM_TTS_MODEL, "pace": config.SARVAM_TTS_PACE,
            }, headers={"api-subscription-key": config.SARVAM_API_KEY})
            logger.info("TTS warm-up complete (sarvam)")
        except Exception:
            logger.exception("TTS warm-up failed (sarvam); the first call may be slow")
