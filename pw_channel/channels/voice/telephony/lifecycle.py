import logging

from pw_channel.db import call_sessions
from pw_sdk.contracts.outcomes import TaskOutcome
from pw_channel.observability import log_event
from pw_channel.channels.voice.states import call_lifecycle as status

logger = logging.getLogger(__name__)


def opened(
    *,
    ref_id: str,
    phone_no: str,
    booking_reference_id: str = "",
    customer_name: str = "",
    channel: str = "acefone",
    call_record_id: int | None = None,
    task_id: int | None = None,
) -> int | None:
    session_id = call_sessions.begin(
        task_id=task_id,
        ref_id=ref_id,
        status=status.RINGING,
        channel=channel,
        direction="outbound",
        customer_number=phone_no,
        customer_name=customer_name,
        booking_reference_id=booking_reference_id,
        call_record_id=call_record_id,
    )
    _note(session_id, status.RINGING, ref_id=ref_id, phone=phone_no)
    return session_id


def answered(
    *,
    ref_id: str,
    call_id: str,
    customer_number: str,
    booking_reference_id: str = "",
    customer_name: str = "",
    direction: str = "",
    channel: str = "acefone",
    did: str = "",
) -> int | None:
    existing = call_sessions.find(ref_id=ref_id, call_id=call_id)

    if existing is None:
        session_id = call_sessions.begin(
            ref_id=ref_id,
            call_id=call_id,
            status=status.ACTIVE,
            channel=channel,
            direction=direction,
            customer_number=customer_number,
            customer_name=customer_name,
            booking_reference_id=booking_reference_id,
            did=did,
        )
        _note(session_id, status.ACTIVE, ref_id=ref_id, call_id=call_id, created=True)
        return session_id

    session_id = existing["id"]
    call_sessions.attach_leg(session_id, call_id=call_id)
    call_sessions.mark(
        session_id,
        status.ACTIVE,
        customer_number=customer_number,
        customer_name=customer_name,
        booking_reference_id=booking_reference_id,
        direction=direction,
        did=did,
    )
    _note(session_id, status.ACTIVE, ref_id=ref_id, call_id=call_id, did=did)
    return session_id


def transfer_started(session_id: int | None, *, destination: str) -> None:
    if not session_id:
        return
    call_sessions.mark(session_id, status.TRANSFER_INITIATED, did=destination)
    _note(session_id, status.TRANSFER_INITIATED, destination=destination)


def transfer_succeeded(session_id: int | None, *, destination: str) -> None:
    if not session_id:
        return
    call_sessions.mark(session_id, status.TRANSFERRED, did=destination)
    _note(session_id, status.TRANSFERRED, destination=destination)


def transfer_failed(session_id: int | None, *, error: str) -> None:
    if not session_id:
        return
    call_sessions.update(session_id, ended_reason=f"transfer_failed: {error}"[:300])
    log_event("call.lifecycle.transfer_failed", session_id=session_id, error=error)


def agent_answered(session_id: int | None, *, agent_number: str = "") -> None:
    if not session_id:
        return
    call_sessions.mark(session_id, status.ACTIVE_WITH_AGENT, agent_number=agent_number)
    _note(session_id, status.ACTIVE_WITH_AGENT, agent=agent_number)


def customer_answered(session_id: int | None, *, customer_number: str = "") -> None:
    if not session_id:
        return
    call_sessions.mark(session_id, status.ACTIVE, customer_number=customer_number)
    _note(session_id, status.ACTIVE, customer=customer_number)


def ended(
    session_id: int | None,
    *,
    reason: str = "",
    duration_secs: float | None = None,
    recording_url: str = "",
    agent_number: str = "",
) -> None:
    if not session_id:
        return
    prior = call_sessions.by_id(session_id)
    call_sessions.mark(
        session_id,
        status.ENDED,
        ended_reason=reason,
        duration_secs=duration_secs,
        recording_url=recording_url,
        agent_number=agent_number,
    )
    _note(session_id, status.ENDED, reason=reason)
    report_outcome(prior, reason)


def bot_leg_closed(session_id: int | None, *, reason: str = "bot_leg_closed") -> None:
    if not session_id:
        return
    prior = call_sessions.by_id(session_id)
    if call_sessions.end_bot_leg(session_id, reason=reason):
        _note(session_id, status.ENDED, reason=reason)
        report_outcome(prior, reason)
        return
    logger.info(
        f"[lifecycle] session={session_id} bot leg closed ({reason}) but the call is "
        f"no longer ours to end — waiting for the provider hangup webhook"
    )
    log_event("call.lifecycle.bot_leg_released", session_id=session_id, reason=reason)


def _note(session_id: int | None, state: str, **fields) -> None:
    if not session_id:
        return
    logger.info(f"[lifecycle] session={session_id} -> {state} {fields}")
    log_event(f"call.lifecycle.{state.lower()}", session_id=session_id, **fields)


def outcome_for(prior_status: str) -> TaskOutcome:
    if status.handed_over(prior_status):
        return TaskOutcome.TRANSFERRED
    if status.rank(prior_status) >= status.rank(status.ACTIVE):
        return TaskOutcome.ANSWERED
    return TaskOutcome.NO_ANSWER


def report_outcome(session: dict | None, reason: str) -> None:
    if not session or not session.get("taskId"):
        return
    outcome = outcome_for(session.get("status") or "")
    try:
        from pw_channel.orchestrator import service

        result = service.complete_task(int(session["taskId"]), outcome, {"call_session": session.get("id"), "ended": reason})
        logger.info(f"[lifecycle] session={session.get('id')} task={session['taskId']} -> {outcome.value} ({result})")
    except Exception:
        logger.exception(f"[lifecycle] could not report the outcome of session {session.get('id')}")
