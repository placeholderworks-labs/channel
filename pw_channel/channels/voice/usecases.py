import os
import logging
import re
import time

import httpx

from pw_channel import config
from pw_sdk.utils.http import base_url

logger = logging.getLogger(__name__)

_TTL_SECS = 10.0
_cache: dict[str, tuple[float, dict | None]] = {}


def base_url() -> str:
    return base_url(config.PW_CHAT_API_URL)


def headers(actor: str = "") -> dict:
    out = {"X-Api-Token": config.PW_CHAT_API_TOKEN}
    if actor:
        out["X-Actor"] = actor
    return out


async def fetch(slug: str) -> dict | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    now = time.monotonic()
    cached = _cache.get(slug)
    if cached and now - cached[0] < _TTL_SECS:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            response = await client.get(f"{base_url()}/usecases/{slug}", headers=headers())
        usecase = response.json() if response.status_code == 200 else None
        if response.status_code not in (200, 404):
            raise httpx.HTTPStatusError("unexpected", request=response.request, response=response)
    except Exception as e:
        logger.warning(f"[usecases] could not load {slug!r} from the brain: {e}")
        return cached[1] if cached else None

    _cache[slug] = (now, usecase)
    return usecase


def peek(slug: str) -> dict | None:
    cached = _cache.get((slug or "").strip())
    return cached[1] if cached else None


def forget(slug: str = "") -> None:
    if slug:
        _cache.pop(slug, None)
    else:
        _cache.clear()


def is_phone(user_type: str) -> bool:
    usecase = peek(user_type)
    if usecase is not None:
        return bool((usecase.get("call") or {}).get("is_phone"))
    return user_type == config.PW_CHAT_USER_TYPE_PHONE


def usable_on(usecase: dict | None, channel: str) -> bool:
    return bool(
        usecase
        and usecase.get("status") != "archived"
        and channel in (usecase.get("channels") or [])
    )


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")


def spoken_value(value) -> str:
    text = str(value if value is not None else "").strip()
    match = _ISO_DATE.match(text)
    if match:
        year, month, day, hour, minute = match.groups()
        out = f"{int(day)} {_MONTHS[int(month) - 1]}"
        if hour is not None and (hour, minute) != ("00", "00"):
            h = int(hour)
            out += f", {h % 12 or 12}:{minute} {'AM' if h < 12 else 'PM'}"
        return out
    if re.fullmatch(r"[a-z]+(?:_[a-z]+)+", text):
        return text.replace("_", " ")
    return text


_SALUTATION = re.compile(
    r"^\s*(नमस्ते|नमस्कार|namaste|hello|hi|hey|good (?:morning|afternoon|evening))(?:\s+there)?(?=[\s,!।.]|$)[\s,!।.]*",
    re.IGNORECASE,
)


def with_name_slot(template: str, language: str) -> str:
    match = _SALUTATION.match(template)
    if match:
        return f"{match.group(1)} {{customer_name}}, {template[match.end():].lstrip()}"
    opener = "नमस्ते {customer_name}, " if language == "hindi" else "Hello {customer_name}, "
    return opener + template


def greeting(user_type: str, *, language: str, customer_name: str = "", facts=None, cart_summary: str = "",
             channel: str = "") -> str:
    usecase = peek(user_type)
    if not usecase:
        return ""
    greetings = usecase.get("greeting") or {}
    template = ""
    if channel == "website" and not customer_name.strip():
        template = (greetings.get(f"website_{language}") or "").strip()
    template = template or (greetings.get(language) or "").strip()
    if not template:
        return ""
    if "{customer_name}" in template and not customer_name.strip():
        return ""
    if "{customer_name}" not in template and customer_name.strip():
        template = with_name_slot(template, language)
    if language == "hindi":
        template = re.sub(r"\{customer_name\}(?!\s*जी)", "{customer_name} जी", template)
    for fact in facts or []:
        key = str(fact.get("key") or "")
        if key and key != "customer_name":
            template = template.replace("{" + key + "}", spoken_value(fact.get("value")))
    if cart_summary:
        template = template.replace("{cart_summary}", cart_summary)
    persona = usecase.get("persona") or {}
    agent = persona.get("agent_name") or ""
    for variable in [*(usecase.get("variables") or []), *(usecase.get("global_variables") or [])]:
        if isinstance(variable, dict) and variable.get("key"):
            template = template.replace("{" + variable["key"] + "}", variable.get("value") or "")
    return (
        template.replace("{customer_name}", customer_name.strip())
        .replace("{agent_name_hindi}", persona.get("agent_name_hindi") or agent)
        .replace("{agent_name}", agent)
        .replace("{company}", persona.get("company") or os.getenv("COMPANY_NAME", "PlaceholderWorks"))
    )


def transfer_number(user_type: str) -> str:
    return str(((peek(user_type) or {}).get("overrides") or {}).get("transfer_number") or "").strip()


def tts_overrides(user_type: str) -> dict:
    voice = (peek(user_type) or {}).get("voice") or {}
    return {
        k: v
        for k, v in {"provider": voice.get("tts_provider"), "voice": voice.get("voice_id")}.items()
        if v
    }


def banned_phrases(user_type: str) -> list[str]:
    usecase = peek(user_type) or {}
    phrases = list((usecase.get("guardrails") or {}).get("banned_phrases") or [])
    for entry in usecase.get("resolved_guardrails") or []:
        if entry.get("kind") == "banned_phrase" and entry.get("enabled", True):
            phrases += entry.get("phrases") or []
    return [p.strip() for p in phrases if p and p.strip()]


def default_language(user_type: str) -> str:
    language = ((peek(user_type) or {}).get("language") or {}).get("default") or ""
    return {"hindi": "hi", "english": "en"}.get(language, "")


def max_call_duration(user_type: str) -> int | None:
    value = ((peek(user_type) or {}).get("call") or {}).get("max_call_duration_secs")
    return int(value) if value else None
