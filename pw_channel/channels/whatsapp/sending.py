import asyncio
import json
import logging
from dataclasses import dataclass

from pw_channel.channels.whatsapp.providers.base import WhatsAppProvider
from pw_channel.channels.whatsapp.providers.pool import pool
from pw_channel.channels.whatsapp.sessions import session_manager
from pw_channel.channels.whatsapp.settings import settings
from pw_sdk import config as client_config
from pw_channel.db.core import connection, is_configured
from pw_sdk.utils import phone

logger = logging.getLogger(__name__)

DEFAULT_COPY = {
    "resume_link": {
        "with_name": "Hi {name}, thanks for your time just now. Here is the link to pick up where you left off.\n\n*Reference:* {reference_id}",
        "without_name": "Hi, thanks for your time just now. Here is the link to pick up where you left off.\n\n*Reference:* {reference_id}",
        "button": "Continue",
    },
}


@dataclass
class SendOutcome:
    ok: bool
    message_id: str = ""
    error: str = ""
    duplicate: bool = False
    sender: str = ""
    provider: str = ""


def copy_for(event: str) -> dict:
    custom = (client_config.current().get("whatsapp.messages") or {}).get(event)
    return {**DEFAULT_COPY.get(event, {}), **(custom or {})}


def recipient(number: str) -> str:
    return phone.msisdn(number, client_config.current().client.country)


def _log(provider: WhatsAppProvider | None, to: str, body: dict, outcome: SendOutcome, task_id: int | None) -> None:
    if not is_configured() or provider is None:
        return
    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO message_log (channel, provider, direction, address, provider_ref, task_id, body, status)
                VALUES ('whatsapp', %s, 'out', %s, %s, %s, %s, %s)
                """,
                (provider.name, to, outcome.message_id or None, task_id, json.dumps(body), "sent" if outcome.ok else "failed"),
            )
    except Exception:
        logger.exception("[whatsapp] could not write the message log")


async def _guarded(dedupe: str | None, send) -> SendOutcome:
    if dedupe:
        try:
            claimed, existing = await session_manager.claim(f"sent:{dedupe}", settings.voicebot_dedupe_ttl)
            if not claimed:
                return SendOutcome(ok=True, message_id=existing or "", duplicate=True)
        except Exception as error:
            logger.warning(f"[whatsapp] dedupe unavailable, sending anyway: {error}")
            dedupe = None
    outcome = await send()
    if dedupe:
        try:
            if outcome.ok:
                await session_manager.remember(f"sent:{dedupe}", outcome.message_id or "sent", settings.voicebot_dedupe_ttl)
            else:
                await session_manager.release(f"sent:{dedupe}")
        except Exception:
            pass
    return outcome


def _provider(sender: str = "") -> WhatsAppProvider | None:
    return (pool().for_sender(sender) if sender else None) or pool().default()


async def send_cta(to: str, body: str, button: str, url: str, *, dedupe: str | None = None, sender: str = "",
                   task_id: int | None = None) -> SendOutcome:
    provider = _provider(sender)
    number = recipient(to)

    async def send() -> SendOutcome:
        if provider is None:
            return SendOutcome(ok=False, error="no WhatsApp number is configured")
        message_id = await provider.send_interactive_cta_button_with_id(number, body, button[:20], url)
        if message_id:
            return SendOutcome(ok=True, message_id=message_id, sender=provider.sender, provider=provider.name)
        return SendOutcome(ok=False, error=f"{provider.name} rejected the message", provider=provider.name)

    outcome = await _guarded(dedupe, send)
    await asyncio.to_thread(_log, provider, number, {"type": "cta", "body": body, "url": url}, outcome, task_id)
    return outcome


async def send_text(to: str, text: str, *, dedupe: str | None = None, sender: str = "", task_id: int | None = None) -> SendOutcome:
    provider = _provider(sender)
    number = recipient(to)

    async def send() -> SendOutcome:
        if provider is None:
            return SendOutcome(ok=False, error="no WhatsApp number is configured")
        ok = await provider.send_text_message(number, text)
        return SendOutcome(ok=ok, message_id=f"{provider.name}:{number}" if ok else "", sender=provider.sender,
                           provider=provider.name, error="" if ok else f"{provider.name} rejected the message")

    outcome = await _guarded(dedupe, send)
    await asyncio.to_thread(_log, provider, number, {"type": "text", "text": text}, outcome, task_id)
    return outcome


async def send_template(to: str, name: str, language: str, components: list, *, dedupe: str | None = None,
                        sender: str = "", task_id: int | None = None) -> SendOutcome:
    provider = _provider(sender)
    number = recipient(to)

    async def send() -> SendOutcome:
        if provider is None:
            return SendOutcome(ok=False, error="no WhatsApp number is configured")
        ok = await provider.send_template_message(number, name, language, components)
        return SendOutcome(ok=ok, message_id=f"{provider.name}:{name}:{number}" if ok else "", sender=provider.sender,
                           provider=provider.name, error="" if ok else f"{provider.name} rejected template {name}")

    outcome = await _guarded(dedupe, send)
    await asyncio.to_thread(_log, provider, number, {"type": "template", "name": name, "components": components}, outcome, task_id)
    return outcome


def resume_message(event: str, customer_name: str, reference_id: str) -> tuple[str, str]:
    copy = copy_for(event)
    if not copy:
        raise KeyError(event)
    name = (customer_name or "").strip()
    body = (copy["with_name"] if name else copy["without_name"]).format(name=name, reference_id=reference_id,
                                                                      company=settings.company_name)
    return body, copy.get("button", "Continue")


def resume_link(resume_url: str, reference_id: str) -> str:
    if resume_url:
        return resume_url
    base = settings.voicebot_cart_link_base.strip()
    return f"{base}{reference_id}" if base else ""
