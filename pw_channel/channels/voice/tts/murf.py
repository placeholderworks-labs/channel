import json
import logging

from pw_channel import config
from pw_channel.channels.voice.tts.base import TTSProvider

logger = logging.getLogger(__name__)

LOCALE_KEY = "multi_native_locale"


class MurfTTS(TTSProvider):
    name = "murf"
    voice_setting = "MURF_TTS_VOICE"
    model_setting = "MURF_TTS_MODEL"
    key_setting = "MURF_API_KEY"
    style_setting = "MURF_TTS_STYLE"

    def build(self, overrides: dict):
        from pipecat_murf_tts import MurfTTSService

        if not config.MURF_API_KEY:
            raise ValueError("MURF_API_KEY is required for the murf voice")
        return MurfTTSService(
            api_key=config.MURF_API_KEY,
            url=config.MURF_TTS_URL,
            params=MurfTTSService.InputParams(
                voice_id=self.pick(overrides, "voice", config.MURF_TTS_VOICE),
                model=self.pick(overrides, "model", config.MURF_TTS_MODEL),
                style=self.pick(overrides, "style", config.MURF_TTS_STYLE),
                multi_native_locale=config.MURF_TTS_LANGUAGE or None,
                rate=config.MURF_TTS_RATE,
                pitch=config.MURF_TTS_PITCH,
                variation=config.MURF_TTS_VARIATION,
                pronunciation_dictionary=config.MURF_TTS_PRONUNCIATION_DICTIONARY,
                sample_rate=self.pick(overrides, "sample_rate", config.MURF_TTS_SAMPLE_RATE),
                channel_type=config.MURF_TTS_CHANNEL_TYPE,
                format=config.MURF_TTS_FORMAT,
                min_buffer_size=config.MURF_TTS_MIN_BUFFER_SIZE,
                max_buffer_delay_in_ms=config.MURF_TTS_MAX_BUFFER_DELAY_MS,
            ),
        )

    def set_language(self, service, locale: str) -> bool:
        settings = getattr(service, "_murf_settings", None)
        if not isinstance(settings, dict) or LOCALE_KEY not in settings:
            return super().set_language(service, locale)
        settings[LOCALE_KEY] = locale
        return True

    async def warmup(self) -> None:
        try:
            from websockets.asyncio.client import connect

            url = (f"{config.MURF_TTS_URL}?sample_rate={config.MURF_TTS_SAMPLE_RATE}&format={config.MURF_TTS_FORMAT}"
                   f"&channel_type={config.MURF_TTS_CHANNEL_TYPE}&model={config.MURF_TTS_MODEL}")
            voice = {"voice_id": config.MURF_TTS_VOICE, "style": config.MURF_TTS_STYLE,
                     "rate": config.MURF_TTS_RATE, "pitch": config.MURF_TTS_PITCH}
            if config.MURF_TTS_MODEL == "GEN2" and config.MURF_TTS_VARIATION is not None:
                voice["variation"] = config.MURF_TTS_VARIATION
            if config.MURF_TTS_PRONUNCIATION_DICTIONARY:
                voice["pronunciation_dictionary"] = config.MURF_TTS_PRONUNCIATION_DICTIONARY
            if config.MURF_TTS_LANGUAGE:
                voice[LOCALE_KEY] = config.MURF_TTS_LANGUAGE
            async with connect(url, additional_headers={"api-key": config.MURF_API_KEY}) as websocket:
                await websocket.send(json.dumps({"context_id": "warmup", "voice_config": voice, "text": "Warming up.", "end": True}))
                async for message in websocket:
                    if not isinstance(message, str):
                        continue
                    data = json.loads(message)
                    if "error" in data:
                        raise RuntimeError(f"Murf warm-up rejected: {data['error']}")
                    if data.get("final") is True:
                        break
            logger.info("TTS warm-up complete (murf)")
        except Exception:
            logger.exception("TTS warm-up failed (murf); the first call may be slow")
