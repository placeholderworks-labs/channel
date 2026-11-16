import asyncio
import logging

from pw_sdk.utils.auth import authorization_value

import httpx

from pw_channel import config
from pw_channel.db import call_sessions
from pw_channel.observability import log_event
from pw_channel.channels.voice.states import call_lifecycle as status
from pw_channel.channels.voice.telephony import lifecycle as call_lifecycle
from pw_sdk.utils.phone import last10

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_state: dict = {"running": False, "polls": 0, "closed": 0, "error": None}
_missing: dict[int, int] = {}

MISSES_BEFORE_CLOSING = 2
MIN_AGE_SECS = 60


def status_report() -> dict:
    return dict(_state)


async def fetch_live_calls() -> list[dict]:
    if not config.ACEFONE_AUTH_TOKEN:
        raise RuntimeError("ACEFONE_AUTH_TOKEN is not configured")

    token = config.ACEFONE_AUTH_TOKEN
    url = f"{config.ACEFONE_API_BASE.rstrip('/')}/live_calls"
    headers = {
        "Authorization": authorization_value(token),
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)

    response.raise_for_status()
    try:
        body = response.json()
    except ValueError:
        return []

    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    if isinstance(body, dict):
        for key in ("data", "live_calls", "calls", "result"):
            rows = body.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _digits(value) -> str:
    only = last10(str(value or ""))
    return only if len(only) == 10 else ""


NUMBER_KEYS = ("customer_number", "source", "destination", "broadcast_no", "multiple_destination_name")


def _identifiers(rows: list[dict]) -> set[str]:
    seen: set[str] = set()
    for row in rows:
        for key in ("ref_id", "call_id", "uuid", "callId", "refId"):
            value = row.get(key)
            if value:
                seen.add(str(value).strip())
        for key in NUMBER_KEYS:
            number = _digits(row.get(key))
            if number:
                seen.add(f"tel:{number}")
    return seen


def _reconcile(live_ids: set[str], sessions: list[dict]) -> int:
    closed = 0
    for session in sessions:
        session_id = session["id"]
        present = any(
            value and str(value) in live_ids
            for value in (
                session.get("ref_id"),
                session.get("current_call_id"),
                session.get("original_call_id"),
            )
        )
        if present:
            _missing.pop(session_id, None)
            continue

        age = float(session.get("age_secs") or 0)
        rank = int(session.get("status_rank") or 0)

        if rank >= status.HANDED_OVER_RANK:
            number = _digits(session.get("customer_number"))
            if number and f"tel:{number}" in live_ids:
                _missing.pop(session_id, None)
                continue
            handed = float(session.get("handed_secs") or age)
            if number and handed >= MIN_AGE_SECS:
                misses = _missing.get(session_id, 0) + 1
                _missing[session_id] = misses
                if misses >= MISSES_BEFORE_CLOSING:
                    call_lifecycle.ended(session_id, reason="no_longer_live_at_acefone")
                    logger.info(
                        f"[live_calls] session={session_id} ({session.get('status')}) — "
                        f"neither its call ids nor the customer's number are live at Acefone "
                        f"for {misses} polls, so the call is over — closed"
                    )
                    closed += 1
                    _missing.pop(session_id, None)
                continue
            if age > config.CALL_SESSION_STALE_SECS:
                call_lifecycle.ended(session_id, reason="stale_timeout")
                logger.warning(
                    f"[live_calls] session={session_id} has been "
                    f"{session.get('status')} for {age / 3600:.1f}h with no hangup "
                    f"webhook — closing it as stale. This is a guess, not an observation."
                )
                closed += 1
                _missing.pop(session_id, None)
            continue

        if age < MIN_AGE_SECS:
            continue

        misses = _missing.get(session_id, 0) + 1
        _missing[session_id] = misses
        if misses < MISSES_BEFORE_CLOSING:
            continue

        call_lifecycle.bot_leg_closed(session_id, reason="reconciled_missing")
        logger.info(
            f"[live_calls] session={session_id} absent from Acefone for "
            f"{misses} polls while still with the bot — closed"
        )
        closed += 1
        _missing.pop(session_id, None)

    known = {session["id"] for session in sessions}
    for stale in [key for key in _missing if key not in known]:
        _missing.pop(stale, None)

    return closed


async def poll_once() -> dict:
    rows = await fetch_live_calls()
    sessions = await asyncio.to_thread(call_sessions.live_ids)
    live_ids = _identifiers(rows)
    closed = await asyncio.to_thread(_reconcile, live_ids, sessions)

    _state["polls"] += 1
    _state["closed"] += closed
    _state["error"] = None

    logger.debug(
        f"[live_calls] acefone={len(rows)} tracked={len(sessions)} closed={closed}"
    )
    return {"live": len(rows), "tracked": len(sessions), "closed": closed}


async def _loop() -> None:
    while _state["running"]:
        try:
            await asyncio.sleep(config.ACEFONE_LIVE_CALLS_POLL_SECS)
            if not _state["running"]:
                return
            await poll_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _state["error"] = f"{e.__class__.__name__}: {e}"
            logger.warning(f"[live_calls] reconciliation poll failed: {_state['error']}")


async def start() -> None:
    global _task
    if not config.ACEFONE_LIVE_CALLS_ENABLED:
        logger.info("[live_calls] reconciliation off (ACEFONE_LIVE_CALLS_ENABLED=false)")
        return
    if not config.ACEFONE_AUTH_TOKEN:
        logger.warning("[live_calls] reconciliation needs ACEFONE_AUTH_TOKEN — not started")
        return
    if _task is not None:
        return
    _state["running"] = True
    _task = asyncio.create_task(_loop(), name="acefone-live-calls")
    log_event("live_calls.started", poll_secs=config.ACEFONE_LIVE_CALLS_POLL_SECS)
    logger.info(
        f"[live_calls] reconciling every {config.ACEFONE_LIVE_CALLS_POLL_SECS}s "
        f"(a handed-over call closes once the customer's number is gone from the live list)"
    )


async def stop() -> None:
    global _task
    _state["running"] = False
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None
    _missing.clear()
