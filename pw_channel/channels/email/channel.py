import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from pw_channel.core import records
from pw_channel.core.channel import Channel, ChannelError, ChannelResult, ChannelTask
from pw_channel.channels.email import links, templates
from pw_channel.channels.email.providers.base import EmailMessageIn
from pw_channel.channels.email.providers.registry import provider
from pw_sdk.contracts.outcomes import TaskOutcome
from pw_channel.db.core import connection, is_configured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel/email", tags=["email"])


def _signal(kind: str, lead_key: str, payload: dict) -> None:
    if not is_configured():
        return
    from pw_channel.orchestrator import service

    service.signal(kind, lead_key=lead_key, source="email", payload={"channel": "email", **payload})


@router.get("/click/{token}")
async def click(token: str):
    data = links.read(token)
    if not data or not str(data.get("u", "")).startswith(("http://", "https://")):
        raise HTTPException(status_code=404, detail="link not found")
    await asyncio.to_thread(_signal, "email.clicked", data.get("l", ""), {"task_id": data.get("t")})
    await asyncio.to_thread(_signal, "link.clicked", data.get("l", ""), {"task_id": data.get("t")})
    return RedirectResponse(data["u"], status_code=302)


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str):
    data = links.read(token)
    if not data:
        raise HTTPException(status_code=404, detail="link not found")
    await asyncio.to_thread(_signal, "opt_out", data.get("l", ""), {})
    return "<p>You have been unsubscribed. You will not get more emails from us.</p>"


def _log(to: str, task_id: int, subject: str, message_id: str, ok: bool) -> None:
    if not is_configured():
        return
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO message_log (channel, provider, direction, address, provider_ref, task_id, body, status)
            VALUES ('email', %s, 'out', %s, %s, %s, %s, %s)
            """,
            (provider().name, to, message_id or None, task_id, json.dumps({"subject": subject}), "sent" if ok else "failed"),
        )


class EmailChannel(Channel):
    name = "email"
    actions = ("send_template",)

    async def execute(self, task: ChannelTask) -> ChannelResult:
        record = task.record
        if not record.customer.email:
            raise ChannelError("no email address", retryable=False)
        name = task.params.get("template")
        if not name:
            raise ChannelError("send_template needs params.template", retryable=False)
        lead_key = records.lead_key(record)
        resume = record.journey.resume_url or task.params.get("link") or ""
        values = {
            "name": record.customer.name or "there",
            "reference_id": record.ref.reference_id,
            "summary": record.spoken_summary() or "your booking",
            "link": links.tracked(resume, lead_key, task.task_id) if resume else "",
            "unsubscribe": links.unsubscribe(lead_key),
        }
        try:
            subject, text, body = templates.render(name, values)
        except KeyError:
            raise ChannelError(f"email template {name!r} is not configured", retryable=False) from None
        result = await asyncio.to_thread(provider().send, EmailMessageIn(
            to=record.customer.email, subject=subject, text=text, html=body,
            headers={"List-Unsubscribe": f"<{values['unsubscribe']}>"},
        ))
        await asyncio.to_thread(_log, record.customer.email, task.task_id, subject, result.message_id, result.ok)
        if not result.ok:
            raise ChannelError(result.error or "email send failed")
        return ChannelResult.waiting(result.message_id, outcome=TaskOutcome.SENT)

    def routes(self):
        return [router]
