import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from pw_channel import config
from pw_channel.db import call_events
from pw_channel.db import call_sessions
from pw_channel.channels.voice.routes import dynamic
from pw_channel.channels.voice.states import call_lifecycle as lifecycle_status
from pw_channel.channels.voice.telephony.acefone import webhook as acefone_webhook
from pw_channel.channels.voice.telephony import lifecycle as call_lifecycle
from pw_sdk.utils.auth import bearer as parse_bearer

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_token(authorization: str | None, x_api_key: str | None) -> str:
    return parse_bearer(authorization) or (x_api_key or "").strip()


def _check_auth(token: str) -> None:
    if not config.ACEFONE_WEBHOOK_TOKEN:
        return
    if not token and not config.ACEFONE_WEBHOOK_REQUIRE_AUTH:
        logger.warning("[acefone.webhook] delivery carried no token — allowed, auth not required")
        return
    if not hmac.compare_digest(token, config.ACEFONE_WEBHOOK_TOKEN):
        logger.warning("[acefone.webhook] rejected a delivery with a bad token")
        raise HTTPException(status_code=401, detail="bad webhook token")


async def _read_body(request: Request) -> dict:
    raw = await request.body()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
        try:
            form = await request.form()
            if form:
                return dict(form)
        except Exception:
            pass
    return dict(request.query_params)


async def acefone_webhook_receiver(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    _check_auth(_extract_token(authorization, x_api_key))

    payload = await _read_body(request)
    if not payload:
        return {"success": True, "note": "empty delivery ignored"}

    event = acefone_webhook.parse(payload)
    kind = event["kind"]

    if kind == acefone_webhook.UNKNOWN:
        logger.warning(f"[acefone.webhook] unrecognised delivery, ignored: {event['body']}")
        return {"success": True, "note": "unrecognised event ignored"}

    logger.info(
        f"[acefone.webhook] {kind} ref_id={event['ref_id']!r} "
        f"call_id={event['call_id']!r} uuid={event['uuid']!r} body={event['body']}"
    )

    session = call_sessions.find(
        ref_id=event["ref_id"], call_id=event["call_id"], call_uuid=event["uuid"]
    )

    event_id = call_events.record_once(
        event_key=event["event_key"],
        kind=kind,
        ref_id=event["ref_id"],
        call_id=event["call_id"],
        call_uuid=event["uuid"],
        session_id=session["id"] if session else None,
        payload=event["body"],
    )
    if event_id is None:
        logger.info(f"[acefone.webhook] replay of {event['event_key']} — nothing to do")
        return {"success": True, "note": "already processed"}

    if session is None:
        session_id = call_sessions.begin(
            ref_id=event["ref_id"],
            call_id=event["call_id"],
            call_uuid=event["uuid"],
            status=_status_for(kind),
            direction=event["direction"],
            customer_number=event["customer_number"],
            agent_number=event["agent_number"],
        )
        logger.warning(
            f"[acefone.webhook] {kind} for a call we never saw "
            f"(ref_id={event['ref_id']!r} call_id={event['call_id']!r}) — "
            f"opened session {session_id} from the webhook"
        )
        if session_id:
            call_events.link(event_id, session_id)
    else:
        session_id = session["id"]
        call_sessions.attach_leg(
            session_id, call_id=event["call_id"], call_uuid=event["uuid"]
        )

    prior = session["status"] if session else ""
    _apply(session_id, kind, event, prior)
    return {"success": True, "session_id": session_id, "event": kind}


def _status_for(kind: str) -> str:
    if kind == acefone_webhook.HANGUP:
        return lifecycle_status.ENDED
    return lifecycle_status.ACTIVE


def _apply(session_id: int | None, kind: str, event: dict, prior: str) -> None:
    if not session_id:
        return

    if kind == acefone_webhook.AGENT_ANSWERED:
        if lifecycle_status.handed_over(prior):
            call_lifecycle.agent_answered(session_id, agent_number=event["agent_number"])
        else:
            call_lifecycle.customer_answered(
                session_id, customer_number=event["customer_number"]
            )
        return

    provider_reason = event["hangup_cause"] or event["call_status"] or "provider_hangup"

    if _agent_never_answered(prior):
        logger.warning(
            f"[acefone.webhook] session={session_id} was transferred to customer care "
            f"but hung up without the agent ever answering ({provider_reason}) — "
            "the customer was handed over and left"
        )
        call_lifecycle.ended(
            session_id,
            reason=f"agent_no_answer: {provider_reason}",
            duration_secs=event["duration_secs"],
            recording_url=event["recording_url"],
            agent_number=event["missed_agent"] or event["agent_number"],
        )
        return

    call_lifecycle.ended(
        session_id,
        reason=provider_reason,
        duration_secs=event["duration_secs"],
        recording_url=event["recording_url"],
        agent_number=event["agent_number"],
    )


def _agent_never_answered(prior: str) -> bool:
    return prior in (lifecycle_status.TRANSFER_INITIATED, lifecycle_status.TRANSFERRED)


async def acefone_webhook_status() -> dict:
    return {
        "webhook_path": config.ACEFONE_WEBHOOK_PATH,
        "auth_configured": bool(config.ACEFONE_WEBHOOK_TOKEN),
        "auth_required": config.ACEFONE_WEBHOOK_REQUIRE_AUTH,
        "live_calls_reconciliation": config.ACEFONE_LIVE_CALLS_ENABLED,
        "live_calls_poll_secs": config.ACEFONE_LIVE_CALLS_POLL_SECS,
        "stale_after_secs": config.CALL_SESSION_STALE_SECS,
        "transcripts": config.CALL_TRANSCRIPT_ENABLED,
    }


@dynamic.installer
def install_acefone_webhook_routes(app) -> list[str]:
    path = config.ACEFONE_WEBHOOK_PATH
    app.add_api_route(
        path,
        acefone_webhook_receiver,
        methods=["POST", "GET"],
        operation_id="acefone_webhook",
        name=dynamic.ROUTE_TAG,
    )
    app.add_api_route(
        path + "/status",
        acefone_webhook_status,
        methods=["GET"],
        name=dynamic.ROUTE_TAG,
    )
    logger.info(f"[acefone.webhook] listening at {path}")
    return [path, path + "/status"]
