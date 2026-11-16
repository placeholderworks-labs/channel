import json
import logging
import os
from typing import Any, Callable

from pw_channel.bootstrap import prepare
from pw_sdk.utils.http import base_url

_log = logging.getLogger(__name__)

CLIENT = prepare()


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val not in (None, "") else default
    except ValueError:
        return default


USE_DB = _env_bool("USE_DB", False)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

DASHBOARD_ENABLED = _env_bool("DASHBOARD_ENABLED", True)
DASHBOARD_SESSION_SECRET = os.getenv("DASHBOARD_SESSION_SECRET", "").strip()
DASHBOARD_SESSION_HOURS = _env_int("DASHBOARD_SESSION_HOURS", 168)
DASHBOARD_ADMIN_EMAIL = os.getenv("DASHBOARD_ADMIN_EMAIL", "").strip().lower()
DASHBOARD_ADMIN_PASSWORD = os.getenv("DASHBOARD_ADMIN_PASSWORD", "")
DASHBOARD_ADMIN_NAME = os.getenv("DASHBOARD_ADMIN_NAME", "").strip()

INTERNAL_LOG_TOKEN = os.getenv("INTERNAL_LOG_TOKEN", "").strip()


_LANGUAGES = {
    "hindi": {
        "script": "Devanagari",
        "endonym": "Hindi",
        "sarvam": "hi-IN",
        "murf": "hi-IN",
        "openai_hint": "Hindi",
    },
    "english": {
        "script": "Latin",
        "endonym": "English",
        "sarvam": "en-IN",
        "murf": "en-IN",
        "openai_hint": "Indian English",
    },
}

VAD_CHANNELS = ("acefone", "website")

_STT_CHANNEL_DEFAULTS = {"website": {"language": "hi", "model": "nova-2"}}

_STT_PROVIDERS = ("deepgram", "deepgram_flux")
_FLUX_MODELS = ("flux-general-multi", "flux-general-en")

_source: dict[str, str] = {}
_origin: str = "env"


def _resolve() -> tuple[dict[str, str], str]:
    from pw_channel.settings.registry import SETTINGS

    values: dict[str, str] = {}
    for key, setting in SETTINGS.items():
        env_value = os.getenv(key) if (not USE_DB or setting.restart) else None
        values[key] = setting.default if env_value is None else env_value

    if not USE_DB:
        return values, "env"

    from pw_channel.settings.store import load_overlay

    overlay = load_overlay()
    if not overlay:
        return values, "env"

    values.update(overlay)
    return values, "database"


class _Reader:

    def __init__(self, raw: dict[str, str]):
        self.raw = raw

    def str(self, name: str, default: str = "") -> str:
        val = self.raw.get(name)
        return default if val is None else val

    def bool(self, name: str, default: bool) -> bool:
        val = self.raw.get(name)
        if val is None or val.strip() == "":
            return default
        return val.strip().lower() in ("1", "true", "yes", "on")

    def int(self, name: str, default: int) -> int:
        val = self.raw.get(name)
        if val in (None, ""):
            return default
        try:
            return int(float(val))
        except ValueError:
            raise ValueError(f"{name} must be a whole number (got {val!r})")

    def float(self, name: str, default: float) -> float:
        val = self.raw.get(name)
        if val in (None, ""):
            return default
        try:
            return float(val)
        except ValueError:
            raise ValueError(f"{name} must be a number (got {val!r})")

    def json_obj(self, name: str) -> dict | None:
        val = self.raw.get(name)
        if val in (None, ""):
            return None
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError as e:
            raise ValueError(f"{name} is not valid JSON: {e.msg}")
        if not isinstance(parsed, dict):
            raise ValueError(f"{name} must be a JSON object, got {type(parsed).__name__}")
        return parsed


def _build(raw: dict[str, str]) -> dict[str, Any]:
    r = _Reader(raw)
    c: dict[str, Any] = {}

    c["HOST"] = r.str("HOST", "0.0.0.0")
    c["PORT"] = r.int("PORT", 8410)
    c["LOG_LEVEL"] = r.str("LOG_LEVEL", "INFO")
    c["PUBLIC_WSS_BASE"] = r.str("PUBLIC_WSS_BASE", "")
    c["SETTINGS_REFRESH_SECS"] = r.float("SETTINGS_REFRESH_SECS", 15.0)

    if 0 < c["SETTINGS_REFRESH_SECS"] < 2:
        raise ValueError(
            f"SETTINGS_REFRESH_SECS is {c['SETTINGS_REFRESH_SECS']:g}s — that polls the "
            "settings table faster than a change can usefully be made. Use 0 to switch "
            "the watcher off, or 2 or more."
        )

    bot_language = r.str("BOT_LANGUAGE", "hindi").strip().lower()
    if bot_language not in _LANGUAGES:
        raise ValueError(
            f"Unsupported BOT_LANGUAGE '{bot_language}'. Allowed: "
            f"{', '.join(sorted(_LANGUAGES))}."
        )
    language = _LANGUAGES[bot_language]
    c["BOT_LANGUAGE"] = bot_language
    c["LANGUAGES"] = _LANGUAGES
    c["LANGUAGE"] = language
    c["LANGUAGE_SCRIPT"] = language["script"]
    c["LANGUAGE_NAME"] = language["endonym"]
    c["DEFAULT_LANGUAGE"] = "hi" if bot_language == "hindi" else "en"

    c["STT_PROVIDER"] = r.str("STT_PROVIDER", "deepgram")
    c["STT_MODEL"] = r.str("STT_MODEL", "nova-3")
    c["STT_FLUX_MODEL"] = r.str("STT_FLUX_MODEL", "flux-general-multi")
    c["STT_LANGUAGE"] = r.str("STT_LANGUAGE", "multi")
    c["DEEPGRAM_API_KEY"] = r.str("DEEPGRAM_API_KEY", "")

    stt_overrides: dict[str, dict[str, str]] = {}
    for channel in VAD_CHANNELS:
        per_channel: dict[str, str] = {}
        for param in ("provider", "language", "model"):
            name = f"STT_{param.upper()}_{channel.upper()}"
            value = r.str(name, _STT_CHANNEL_DEFAULTS.get(channel, {}).get(param, "")).strip()
            if value:
                per_channel[param] = value
        if per_channel:
            stt_overrides[channel] = per_channel
    c["STT_CHANNEL_OVERRIDES"] = stt_overrides

    c["STT_PROVIDER_BY_CHANNEL"] = {
        channel: (
            stt_overrides.get(channel, {}).get("provider") or c["STT_PROVIDER"]
        ).strip().lower()
        for channel in VAD_CHANNELS
    }

    for name, value in (
        ("STT_PROVIDER", c["STT_PROVIDER"]),
        *(
            (f"STT_PROVIDER_{channel.upper()}", params["provider"])
            for channel, params in stt_overrides.items()
            if "provider" in params
        ),
    ):
        if value.strip().lower() not in _STT_PROVIDERS:
            raise ValueError(
                f"{name} must be one of {', '.join(_STT_PROVIDERS)} (got {value!r})."
            )

    if c["STT_FLUX_MODEL"] not in _FLUX_MODELS:
        raise ValueError(
            f"STT_FLUX_MODEL must be one of {', '.join(_FLUX_MODELS)} "
            f"(got {c['STT_FLUX_MODEL']!r})."
        )

    c["TTS_PROVIDER"] = r.str("TTS_PROVIDER", "murf")
    c["TTS_MODEL"] = r.str("TTS_MODEL", "gemini-3.1-flash-tts-preview")
    c["TTS_VOICE"] = r.str("TTS_VOICE", "Kore")
    c["TTS_SAMPLE_RATE"] = r.int("TTS_SAMPLE_RATE", 24000)
    c["GOOGLE_API_KEY"] = r.str("GOOGLE_API_KEY", "")

    c["SARVAM_API_KEY"] = r.str("SARVAM_API_KEY", "")
    c["SARVAM_TTS_MODEL"] = r.str("SARVAM_TTS_MODEL", "bulbul:v2")
    c["SARVAM_TTS_VOICE"] = r.str("SARVAM_TTS_VOICE", "anushka")
    c["SARVAM_TTS_LANGUAGE"] = r.str("SARVAM_TTS_LANGUAGE", "") or language["sarvam"]
    c["SARVAM_TTS_PACE"] = r.float("SARVAM_TTS_PACE", 1.0)
    c["SARVAM_TTS_SAMPLE_RATE"] = r.int("SARVAM_TTS_SAMPLE_RATE", 22050)

    c["OPENAI_TTS_API_KEY"] = r.str("OPENAI_TTS_API_KEY", "")
    c["OPENAI_TTS_MODEL"] = r.str("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    c["OPENAI_TTS_VOICE"] = r.str("OPENAI_TTS_VOICE", "alloy")
    c["OPENAI_TTS_INSTRUCTIONS"] = r.str("OPENAI_TTS_INSTRUCTIONS", "") or (
        f"Speak warmly and naturally in {language['openai_hint']}, like a helpful "
        "customer care agent on a phone call — not stiff or robotic."
    )
    c["OPENAI_TTS_SPEED"] = r.float("OPENAI_TTS_SPEED", 1.0)
    c["OPENAI_TTS_SAMPLE_RATE"] = r.int("OPENAI_TTS_SAMPLE_RATE", 24000)

    c["MURF_API_KEY"] = r.str("MURF_API_KEY", "")
    c["MURF_TTS_URL"] = r.str("MURF_TTS_URL", "wss://global.api.murf.ai/v1/speech/stream-input")
    c["MURF_TTS_MODEL"] = r.str("MURF_TTS_MODEL", "falcon-2")
    c["MURF_TTS_VOICE"] = r.str("MURF_TTS_VOICE", "Anisha")
    c["MURF_TTS_LANGUAGE"] = r.str("MURF_TTS_LANGUAGE", "") or language["murf"]
    c["MURF_TTS_STYLE"] = r.str("MURF_TTS_STYLE", "Conversational")
    c["MURF_TTS_RATE"] = r.int("MURF_TTS_RATE", 0)
    c["MURF_TTS_PITCH"] = r.int("MURF_TTS_PITCH", 0)
    c["MURF_TTS_VARIATION"] = r.int("MURF_TTS_VARIATION", 1)
    c["MURF_TTS_PRONUNCIATION_DICTIONARY"] = r.json_obj("MURF_TTS_PRONUNCIATION_DICTIONARY")
    c["MURF_TTS_SAMPLE_RATE"] = r.int("MURF_TTS_SAMPLE_RATE", 24000)
    c["MURF_TTS_CHANNEL_TYPE"] = r.str("MURF_TTS_CHANNEL_TYPE", "MONO")
    c["MURF_TTS_FORMAT"] = r.str("MURF_TTS_FORMAT", "PCM")
    c["MURF_TTS_MIN_BUFFER_SIZE"] = r.int("MURF_TTS_MIN_BUFFER_SIZE", 40)
    c["MURF_TTS_MAX_BUFFER_DELAY_MS"] = r.int("MURF_TTS_MAX_BUFFER_DELAY_MS", 300)

    c["BOT_OUTPUT_GAIN_DB"] = r.float("BOT_OUTPUT_GAIN_DB", 0.0)
    if not -24.0 <= c["BOT_OUTPUT_GAIN_DB"] <= 24.0:
        raise ValueError(
            f"BOT_OUTPUT_GAIN_DB must be between -24 and 24 dB (got "
            f"{c['BOT_OUTPUT_GAIN_DB']}). Beyond that the limiter is doing all the "
            "work and the voice will sound squashed rather than louder — fix the "
            "source level instead."
        )

    c["ENABLE_BACKGROUND_AMBIENCE"] = r.bool("ENABLE_BACKGROUND_AMBIENCE", False)
    c["BACKGROUND_AMBIENCE_LEVEL_DB"] = r.float("BACKGROUND_AMBIENCE_LEVEL_DB", -28.0)

    c["VAD_CONFIDENCE"] = r.float("VAD_CONFIDENCE", 0.7)
    c["VAD_START_SECS"] = r.float("VAD_START_SECS", 0.2)
    c["VAD_STOP_SECS"] = r.float("VAD_STOP_SECS", 0.5)
    c["VAD_MIN_VOLUME"] = r.float("VAD_MIN_VOLUME", 0.6)
    c["VAD_CHANNELS"] = VAD_CHANNELS

    overrides: dict[str, dict[str, float]] = {}
    for channel in VAD_CHANNELS:
        params: dict[str, float] = {}
        for param in ("confidence", "start_secs", "stop_secs", "min_volume"):
            name = f"VAD_{param.upper()}_{channel.upper()}"
            if r.str(name, "").strip():
                params[param] = r.float(name, 0.0)
        if params:
            overrides[channel] = params
    c["VAD_CHANNEL_OVERRIDES"] = overrides

    c["ENABLE_LANGUAGE_SWITCH"] = r.bool("ENABLE_LANGUAGE_SWITCH", True)

    c["SMART_TURN_STOP_SECS"] = r.float("SMART_TURN_STOP_SECS", 2.5)
    c["SMART_TURN_PRE_SPEECH_MS"] = r.float("SMART_TURN_PRE_SPEECH_MS", 800.0)
    c["SMART_TURN_MAX_DURATION_SECS"] = r.float("SMART_TURN_MAX_DURATION_SECS", 12.0)

    c["FLUX_EOT_THRESHOLD"] = r.float("FLUX_EOT_THRESHOLD", 0.7)
    c["FLUX_EOT_TIMEOUT_MS"] = r.int("FLUX_EOT_TIMEOUT_MS", 5000)
    c["FLUX_SHOULD_INTERRUPT"] = r.bool("FLUX_SHOULD_INTERRUPT", True)
    c["FLUX_INPUT_CHUNK_MS"] = r.int("FLUX_INPUT_CHUNK_MS", 0)
    c["FLUX_TURN_AGGREGATION_MS"] = r.int("FLUX_TURN_AGGREGATION_MS", 50)

    if not 0.5 <= c["FLUX_EOT_THRESHOLD"] <= 1.0:
        raise ValueError(
            f"FLUX_EOT_THRESHOLD must be between 0.5 and 1.0 (got "
            f"{c['FLUX_EOT_THRESHOLD']}). Deepgram rejects anything outside that range."
        )

    if not 500 <= c["FLUX_EOT_TIMEOUT_MS"] <= 60000:
        raise ValueError(
            f"FLUX_EOT_TIMEOUT_MS must be between 500 and 60000 (got "
            f"{c['FLUX_EOT_TIMEOUT_MS']})."
        )

    if not 10 <= c["FLUX_TURN_AGGREGATION_MS"] <= 500:
        raise ValueError(
            f"FLUX_TURN_AGGREGATION_MS must be between 10 and 500 (got "
            f"{c['FLUX_TURN_AGGREGATION_MS']}). It only has to outlast the queue hop "
            "between Flux's stop signal and its transcript; every extra millisecond "
            "is dead air before the brain is asked."
        )

    if not 0 <= c["FLUX_INPUT_CHUNK_MS"] <= 200:
        raise ValueError(
            f"FLUX_INPUT_CHUNK_MS must be between 0 and 200 (got "
            f"{c['FLUX_INPUT_CHUNK_MS']}); 0 disables re-chunking."
        )

    c["MIN_WORDS_TO_INTERRUPT"] = r.int("MIN_WORDS_TO_INTERRUPT", 2)
    c["USER_TURN_STOP_TIMEOUT_SECS"] = r.float("USER_TURN_STOP_TIMEOUT_SECS", 3.5)

    c["USER_IDLE_TIMEOUT_SECS"] = r.float("USER_IDLE_TIMEOUT_SECS", 7.0)
    c["MAX_CONSECUTIVE_REPROMPTS"] = r.int("MAX_CONSECUTIVE_REPROMPTS", 3)

    if c["USER_IDLE_TIMEOUT_SECS"] and (
        c["USER_IDLE_TIMEOUT_SECS"] <= c["USER_TURN_STOP_TIMEOUT_SECS"]
    ):
        raise ValueError(
            f"USER_IDLE_TIMEOUT_SECS ({c['USER_IDLE_TIMEOUT_SECS']}) must be greater "
            f"than USER_TURN_STOP_TIMEOUT_SECS ({c['USER_TURN_STOP_TIMEOUT_SECS']}), "
            "or 0 to disable. The idle timer starts when the bot stops speaking, so a "
            "shorter value pre-empts the turn watchdog and nudges a customer who is "
            "still speaking."
        )

    if c["MAX_CONSECUTIVE_REPROMPTS"] < 0:
        raise ValueError(
            f"MAX_CONSECUTIVE_REPROMPTS must be 0 or more (got "
            f"{c['MAX_CONSECUTIVE_REPROMPTS']})."
        )

    if c["MIN_WORDS_TO_INTERRUPT"] < 1:
        raise ValueError(
            f"MIN_WORDS_TO_INTERRUPT must be at least 1 (got "
            f"{c['MIN_WORDS_TO_INTERRUPT']}); 0 would mean a turn opens before any "
            "word is transcribed."
        )


    if any(p != "deepgram_flux" for p in c["STT_PROVIDER_BY_CHANNEL"].values()) and (
        c["USER_TURN_STOP_TIMEOUT_SECS"] <= c["SMART_TURN_STOP_SECS"]
    ):
        raise ValueError(
            f"USER_TURN_STOP_TIMEOUT_SECS ({c['USER_TURN_STOP_TIMEOUT_SECS']}) must be "
            f"greater than SMART_TURN_STOP_SECS ({c['SMART_TURN_STOP_SECS']}). Both "
            "timers start at the same VAD stop, so an equal or lower value makes the "
            "fallback watchdog race the turn analyzer and end turns the analyzer would "
            "have kept open. This is only relaxed once every channel runs "
            "STT_PROVIDER=deepgram_flux, which has no local turn analyzer."
        )

    c["MAX_CALL_DURATION_SECS"] = r.int("MAX_CALL_DURATION_SECS", 300)
    c["CALL_WRAP_UP_WARNING_SECS"] = r.int("CALL_WRAP_UP_WARNING_SECS", 30)
    c["CALL_END_WATCHDOG_SECS"] = r.int("CALL_END_WATCHDOG_SECS", 20)

    c["ENABLE_WEBSITE"] = r.bool("ENABLE_WEBSITE", False)
    c["ENABLE_ACEFONE"] = r.bool("ENABLE_ACEFONE", False)

    c["ACEFONE_WS_PATH"] = r.str("ACEFONE_WS_PATH", "/ws/acefone")
    c["ACEFONE_MEDIA_FORMAT"] = r.str("ACEFONE_MEDIA_FORMAT", "ulaw").strip().lower()
    c["ACEFONE_SAMPLE_RATE"] = r.int("ACEFONE_SAMPLE_RATE", 8000)
    c["ACEFONE_AUTO_HANG_UP"] = r.bool("ACEFONE_AUTO_HANG_UP", True)
    c["ACEFONE_OUT_10MS_CHUNKS"] = r.int("ACEFONE_OUT_10MS_CHUNKS", 2)
    c["ACEFONE_API_KEY"] = r.str("ACEFONE_API_KEY", "")
    c["ACEFONE_API_BASE"] = r.str("ACEFONE_API_BASE", "https://api.acefone.in/v1")
    c["ACEFONE_AUTH_TOKEN"] = r.str("ACEFONE_AUTH_TOKEN", "")
    c["ACEFONE_CALLER_ID"] = r.str("ACEFONE_CALLER_ID", "")
    c["ACEFONE_RING_TIMEOUT"] = r.int("ACEFONE_RING_TIMEOUT", 30)
    c["ACEFONE_CALL_TIMEOUT"] = r.int("ACEFONE_CALL_TIMEOUT", 0)

    c["ACEFONE_WEBHOOK_PATH"] = r.str("ACEFONE_WEBHOOK_PATH", "/webhooks/acefone")
    c["ACEFONE_WEBHOOK_TOKEN"] = r.str("ACEFONE_WEBHOOK_TOKEN", "")
    c["ACEFONE_WEBHOOK_REQUIRE_AUTH"] = r.bool("ACEFONE_WEBHOOK_REQUIRE_AUTH", False)
    c["ACEFONE_LIVE_CALLS_ENABLED"] = r.bool("ACEFONE_LIVE_CALLS_ENABLED", False)
    c["ACEFONE_LIVE_CALLS_POLL_SECS"] = r.int("ACEFONE_LIVE_CALLS_POLL_SECS", 30)
    c["CALL_SESSION_STALE_SECS"] = r.int("CALL_SESSION_STALE_SECS", 14400)
    c["CALL_TRANSCRIPT_ENABLED"] = r.bool("CALL_TRANSCRIPT_ENABLED", True)

    c["ENABLE_CALL_TRANSFER"] = r.bool("ENABLE_CALL_TRANSFER", True)
    c["CALL_TRANSFER_NUMBER"] = r.str("CALL_TRANSFER_NUMBER", "01143131313")
    c["CALL_TRANSFER_HOLD_SECS"] = r.float("CALL_TRANSFER_HOLD_SECS", 4.0)

    if not 0 <= c["CALL_TRANSFER_HOLD_SECS"] <= 15:
        raise ValueError(
            f"CALL_TRANSFER_HOLD_SECS must be between 0 and 15 seconds (got "
            f"{c['CALL_TRANSFER_HOLD_SECS']}); it only buys time for the handoff "
            "line to finish playing before the call leaves us."
        )

    if c["ACEFONE_LIVE_CALLS_POLL_SECS"] and c["ACEFONE_LIVE_CALLS_POLL_SECS"] < 10:
        raise ValueError(
            f"ACEFONE_LIVE_CALLS_POLL_SECS must be at least 10 seconds (got "
            f"{c['ACEFONE_LIVE_CALLS_POLL_SECS']}); this is a reconciliation "
            "check, not the source of truth for call state."
        )

    if c["ACEFONE_RING_TIMEOUT"] and not 10 <= c["ACEFONE_RING_TIMEOUT"] <= 30:
        raise ValueError(
            f"ACEFONE_RING_TIMEOUT must be between 10 and 30 seconds (got "
            f"{c['ACEFONE_RING_TIMEOUT']})."
        )

    if c["ACEFONE_MEDIA_FORMAT"] not in ("ulaw", "pcm"):
        raise ValueError(
            f"Unsupported ACEFONE_MEDIA_FORMAT '{c['ACEFONE_MEDIA_FORMAT']}'. "
            "Allowed: ulaw, pcm."
        )

    if c["ACEFONE_MEDIA_FORMAT"] == "ulaw" and c["ACEFONE_OUT_10MS_CHUNKS"] % 2 != 0:
        raise ValueError(
            f"ACEFONE_OUT_10MS_CHUNKS must be even when ACEFONE_MEDIA_FORMAT=ulaw "
            f"(got {c['ACEFONE_OUT_10MS_CHUNKS']}); mu-law payloads must be a "
            "multiple of 160 bytes."
        )

    if not 2 <= c["ACEFONE_OUT_10MS_CHUNKS"] <= 10:
        raise ValueError(
            f"ACEFONE_OUT_10MS_CHUNKS must be between 2 and 10 (got "
            f"{c['ACEFONE_OUT_10MS_CHUNKS']} = "
            f"{c['ACEFONE_OUT_10MS_CHUNKS'] * 10}ms per media message); 2 (20ms) is "
            "recommended."
        )

    c["WEBSITE_WS_PATH"] = r.str("WEBSITE_WS_PATH", "/ws/website")
    c["WEBSITE_SAMPLE_RATE"] = r.int("WEBSITE_SAMPLE_RATE", 24000)
    c["WEBSITE_PIPELINE_SAMPLE_RATE"] = r.int("WEBSITE_PIPELINE_SAMPLE_RATE", 16000)

    if c["WEBSITE_PIPELINE_SAMPLE_RATE"] not in (8000, 16000):
        raise ValueError(
            f"WEBSITE_PIPELINE_SAMPLE_RATE must be 8000 or 16000 (got "
            f"{c['WEBSITE_PIPELINE_SAMPLE_RATE']}); Silero VAD accepts no other rate, "
            "and both are rates Deepgram Flux accepts. The browser can still "
            "send/receive at WEBSITE_SAMPLE_RATE — the serializer resamples."
        )

    c["PW_CHAT_ENABLED"] = r.bool("PW_CHAT_ENABLED", True)
    c["PW_CHAT_API_URL"] = r.str(
        "PW_CHAT_API_URL",
        "http://localhost:8010/api/pw-ai-service/chat",
    )
    c["PW_CHAT_API_TOKEN"] = r.str("PW_CHAT_API_TOKEN", "")

    c["PW_CHAT_SETTINGS_URL"] = base_url(c["PW_CHAT_API_URL"]) + "/settings"
    c["PW_CHAT_USER_TYPE_WEBSITE"] = r.str("PW_CHAT_USER_TYPE_WEBSITE", "webvoice")
    c["PW_CHAT_USER_TYPE_PHONE"] = r.str("PW_CHAT_USER_TYPE_PHONE", "callvoice")
    c["PW_CHAT_USER_TYPES_BY_CHANNEL"] = {
        channel: r.str(f"PW_CHAT_BRAIN_{channel.upper()}", "")
        for channel in VAD_CHANNELS
    }
    c["PW_CHAT_ACTIONS_ENABLED"] = r.bool("PW_CHAT_ACTIONS_ENABLED", True)
    c["POST_CALL_MOM_ENABLED"] = r.bool("POST_CALL_MOM_ENABLED", True)
    c["PW_CHAT_CONNECT_TIMEOUT_SECS"] = r.float("PW_CHAT_CONNECT_TIMEOUT_SECS", 5.0)
    c["PW_CHAT_READ_TIMEOUT_SECS"] = r.float("PW_CHAT_READ_TIMEOUT_SECS", 30.0)
    c["PW_CHAT_PHONE_READ_TIMEOUT_SECS"] = r.float("PW_CHAT_PHONE_READ_TIMEOUT_SECS", 8.0)
    c["PW_CHAT_MAX_ATTEMPTS"] = r.int("PW_CHAT_MAX_ATTEMPTS", 2)
    c["PW_CHAT_MAX_CONSECUTIVE_FAILURES"] = r.int("PW_CHAT_MAX_CONSECUTIVE_FAILURES", 3)
    c["PW_CHAT_MAX_HTML_BYTES"] = r.int("PW_CHAT_MAX_HTML_BYTES", 262144)
    c["PW_CHAT_HTML_CHUNK_BYTES"] = r.int("PW_CHAT_HTML_CHUNK_BYTES", 8192)
    c["PW_CHAT_HOLD_DELAY_SECS"] = r.float("PW_CHAT_HOLD_DELAY_SECS", 1.8)
    c["PW_CHAT_HOLD_BUDGET_SECS"] = r.float("PW_CHAT_HOLD_BUDGET_SECS", 3.0)
    c["PW_CHAT_HOLD_GRACE_SECS"] = r.float("PW_CHAT_HOLD_GRACE_SECS", 0.2)
    c["PW_CHAT_SECOND_HOLD_SECS"] = r.float("PW_CHAT_SECOND_HOLD_SECS", 8.0)
    c["PW_CHAT_PHONE_HOLD_DELAY_SECS"] = r.float("PW_CHAT_PHONE_HOLD_DELAY_SECS", 1.4)
    c["PW_CHAT_PHONE_SECOND_HOLD_SECS"] = r.float("PW_CHAT_PHONE_SECOND_HOLD_SECS", 4.5)
    c["VOICE_REPLY_WARN_CHARS"] = r.int("VOICE_REPLY_WARN_CHARS", 400)

    if not c["PW_CHAT_API_URL"].startswith(("http://", "https://")):
        raise ValueError(
            f"PW_CHAT_API_URL must be an http(s) URL (got "
            f"{c['PW_CHAT_API_URL']!r})."
        )

    if c["PW_CHAT_MAX_ATTEMPTS"] < 1:
        raise ValueError(
            f"PW_CHAT_MAX_ATTEMPTS must be at least 1 (got "
            f"{c['PW_CHAT_MAX_ATTEMPTS']})."
        )

    if not 0 <= c["PW_CHAT_HOLD_GRACE_SECS"] <= 3:
        raise ValueError(
            f"PW_CHAT_HOLD_GRACE_SECS must be between 0 and 3 seconds (got "
            f"{c['PW_CHAT_HOLD_GRACE_SECS']}); it is the last look at whether the "
            "answer has already landed, not a second hold delay."
        )

    if c["PW_CHAT_HOLD_DELAY_SECS"] >= c["PW_CHAT_READ_TIMEOUT_SECS"]:
        raise ValueError(
            f"PW_CHAT_HOLD_DELAY_SECS ({c['PW_CHAT_HOLD_DELAY_SECS']}s) must be well "
            f"below PW_CHAT_READ_TIMEOUT_SECS ({c['PW_CHAT_READ_TIMEOUT_SECS']}s), or "
            "the customer waits out the whole search in silence."
        )

    if c["PW_CHAT_PHONE_HOLD_DELAY_SECS"] >= c["PW_CHAT_PHONE_READ_TIMEOUT_SECS"]:
        raise ValueError(
            f"PW_CHAT_PHONE_HOLD_DELAY_SECS "
            f"({c['PW_CHAT_PHONE_HOLD_DELAY_SECS']}s) must be well below "
            f"PW_CHAT_PHONE_READ_TIMEOUT_SECS "
            f"({c['PW_CHAT_PHONE_READ_TIMEOUT_SECS']}s), or the caller hears nothing "
            "at all while the brain thinks."
        )

    if c["PW_CHAT_MAX_CONSECUTIVE_FAILURES"] < 1:
        raise ValueError(
            f"PW_CHAT_MAX_CONSECUTIVE_FAILURES must be at least 1 (got "
            f"{c['PW_CHAT_MAX_CONSECUTIVE_FAILURES']})."
        )

    if c["PW_CHAT_HTML_CHUNK_BYTES"] < 1024:
        raise ValueError(
            f"PW_CHAT_HTML_CHUNK_BYTES must be at least 1024 (got "
            f"{c['PW_CHAT_HTML_CHUNK_BYTES']}); smaller chunks are pure overhead."
        )

    c["QMS_PUBLIC_BASE_URL"] = r.str("QMS_PUBLIC_BASE_URL", "").strip().rstrip("/")
    c["INGESTION_ENABLED"] = r.bool("INGESTION_ENABLED", True)
    c["INGESTION_API_TOKEN"] = r.str("INGESTION_API_TOKEN", "")
    c["INGESTION_CALL_CHANNEL"] = r.str("INGESTION_CALL_CHANNEL", "acefone").strip().lower()
    c["INGESTION_CALL_DELAY_SECS"] = r.float("INGESTION_CALL_DELAY_SECS", 120.0)
    c["INGESTION_DEDUPE_WINDOW_SECS"] = r.float("INGESTION_DEDUPE_WINDOW_SECS", 3600.0)
    c["INGESTION_CART_TTL_SECS"] = r.float("INGESTION_CART_TTL_SECS", 7200.0)
    c["INGESTION_MAX_BATCH"] = r.int("INGESTION_MAX_BATCH", 200)
    c["INGESTION_AGENT"] = (r.str("INGESTION_AGENT", "callvoice").strip().lower() or "callvoice")

    if c["INGESTION_CALL_DELAY_SECS"] < 0:
        raise ValueError(
            f"INGESTION_CALL_DELAY_SECS cannot be negative (got "
            f"{c['INGESTION_CALL_DELAY_SECS']})."
        )

    if c["INGESTION_CART_TTL_SECS"] <= c["INGESTION_CALL_DELAY_SECS"]:
        raise ValueError(
            f"INGESTION_CART_TTL_SECS ({c['INGESTION_CART_TTL_SECS']}) must be greater "
            f"than INGESTION_CALL_DELAY_SECS ({c['INGESTION_CALL_DELAY_SECS']}); the "
            "cart has to outlive the wait or the call rings with no cart data behind it."
        )

    c["DISPOSITION_LOG_WEBHOOK"] = r.str("DISPOSITION_LOG_WEBHOOK", "")

    c["CHANNEL_SAMPLE_RATES"] = {
        "acefone": c["ACEFONE_SAMPLE_RATE"],
        "website": c["WEBSITE_SAMPLE_RATE"],
    }

    return c


def _restart_required_keys() -> frozenset[str]:
    from pw_channel.settings.registry import SETTINGS

    return frozenset(key for key, setting in SETTINGS.items() if setting.restart)


RESTART_REQUIRED_KEYS = _restart_required_keys()


def source() -> str:
    return _origin


def raw_values() -> dict[str, str]:
    return dict(_source)


def validate(updates: dict[str, str]) -> None:
    candidate = dict(_source)
    candidate.update(updates)
    _build(candidate)


_reload_hooks: list[Callable[[dict[str, tuple[Any, Any]]], None]] = []


def on_reload(callback: Callable[[dict[str, tuple[Any, Any]]], None]):
    if callback not in _reload_hooks:
        _reload_hooks.append(callback)
    return callback


def _notify_reload(changes: dict[str, tuple[Any, Any]]) -> None:
    for hook in list(_reload_hooks):
        try:
            hook(changes)
        except Exception:
            _log.exception(f"[config] reload hook {getattr(hook, '__name__', hook)!r} failed")


def reload() -> dict[str, tuple[Any, Any]]:
    global _source, _origin

    raw, origin = _resolve()
    built = _build(raw)

    current = globals()
    changes: dict[str, tuple[Any, Any]] = {}
    for name, value in built.items():
        before = current.get(name)
        if before != value:
            changes[name] = (before, value)

    current.update(built)
    _source = raw
    _origin = origin

    if changes:
        _notify_reload(changes)
    return changes


def _initial_load() -> None:
    global _source, _origin

    raw, origin = _resolve()
    try:
        built = _build(raw)
    except ValueError as e:
        if origin != "database":
            raise
        _log.error(
            f"[config] the stored settings are invalid ({e}); starting on .env values "
            "instead. Fix the setting in the dashboard and apply again."
        )
        from pw_channel.settings.registry import SETTINGS

        raw = {
            key: (setting.default if os.getenv(key) is None else os.getenv(key))
            for key, setting in SETTINGS.items()
        }
        origin = "env"
        built = _build(raw)

    globals().update(built)
    _source = raw
    _origin = origin
    _log.info(f"[config] loaded {len(built)} settings from {origin}")


_initial_load()
