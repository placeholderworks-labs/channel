import asyncio
import logging
import os

from pw_channel.db.core import is_configured
from pw_sdk.utils import phone

logger = logging.getLogger(__name__)

DEFAULT_OPT_OUT = ("stop", "unsubscribe", "opt out", "optout", "stop messages")


def opt_out_words() -> tuple[str, ...]:
    raw = os.getenv("WHATSAPP_OPT_OUT_KEYWORDS", "")
    words = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return words or DEFAULT_OPT_OUT


def is_opt_out(text: str) -> bool:
    return (text or "").strip().lower() in opt_out_words()


def lead_key_for(number: str) -> str:
    e164 = phone.to_e164(number if number.startswith("+") else f"+{phone.digits(number)}")
    return f"phone:{e164}" if e164 else ""


async def emit(kind: str, number: str, payload: dict | None = None, dedupe_key: str | None = None) -> None:
    if not is_configured():
        return
    lead_key = lead_key_for(number)
    if not lead_key:
        return
    from pw_channel.orchestrator import service

    try:
        await asyncio.to_thread(service.signal, kind, lead_key=lead_key, source="whatsapp",
                                payload={"channel": "whatsapp", **(payload or {})}, dedupe_key=dedupe_key)
    except Exception:
        logger.exception(f"[whatsapp] could not record {kind} for {phone.mask(number)}")
