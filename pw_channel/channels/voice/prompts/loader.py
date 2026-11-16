import logging
from pathlib import Path

import yaml

from pw_channel import config
from pw_channel.channels.voice import usecases

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent

_GREETINGS_FILE = "greetings.yml"
_GREETING_KEYS = {
    "callvoice": "callvoice_greeting",
    "webvoice": "webvoice_greeting",
}

_TTS_PROFILES = {
    "murf": {
        "provider": "murf",
        "reads_bracket_tags_literally": True,
        "reads_currency_symbol_literally": True,
        "spell_numbers_in_words": True,
    },
    "gemini": {
        "provider": "gemini",
        "reads_bracket_tags_literally": False,
        "reads_currency_symbol_literally": True,
        "spell_numbers_in_words": True,
    },
}

_greetings_cache: dict | None = None


def _greetings() -> dict:
    global _greetings_cache
    if _greetings_cache is None:
        with open(PROMPTS_DIR / _GREETINGS_FILE, "r", encoding="utf-8") as f:
            _greetings_cache = yaml.safe_load(f) or {}
    return _greetings_cache


def load_greeting_line(user_type: str, *, customer_name: str = "", language: str = "", facts=None, cart_summary: str = "",
                       channel: str = "") -> str:
    language = (language or config.BOT_LANGUAGE).strip().lower()
    from_usecase = usecases.greeting(
        user_type, language=language, customer_name=customer_name, facts=facts, cart_summary=cart_summary,
        channel=channel,
    )
    if from_usecase or usecases.peek(user_type) is not None:
        return from_usecase

    key = _GREETING_KEYS.get(user_type)
    if not key:
        return ""

    greetings = _greetings().get(key) or {}
    template = (greetings.get(language) or "").strip()
    if not template:
        return ""

    if "{customer_name}" in template and not customer_name.strip():
        return ""

    return template.format(customer_name=customer_name.strip())


def tts_profile(provider: str = "") -> dict:
    provider = (provider or config.TTS_PROVIDER or "").strip().lower()
    profile = _TTS_PROFILES.get(provider)
    if profile is None:
        profile = {
            "provider": provider or "unknown",
            "reads_bracket_tags_literally": True,
            "reads_currency_symbol_literally": True,
            "spell_numbers_in_words": True,
        }
    return dict(profile)
