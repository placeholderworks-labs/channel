import asyncio
import logging
from datetime import datetime, timedelta, timezone

from pw_channel.core import records, registry
from pw_channel.core.channel import ChannelError, ChannelTask
from pw_channel.orchestrator import store
from pw_channel.policy import gate
from pw_sdk.contracts.outcomes import TaskOutcome
from pw_sdk.utils.ids import idempotency_key

logger = logging.getLogger(__name__)

CALL_WAIT_SECS = 2 * 3600
RETRY_ON = (TaskOutcome.NO_ANSWER, TaskOutcome.BUSY)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def dispatch(task: store.TaskRow, now: datetime | None = None) -> str:
    now = now or _now()

    async def _finish(task_id: int, outcome: TaskOutcome, **kwargs) -> str:
        return await asyncio.to_thread(store.finish, task_id, outcome, now=now, **kwargs)

    target = await asyncio.to_thread(records.get, task.reference_id)
    if target is None:
        await _finish(task.id, TaskOutcome.FAILED, detail={"error": "record not found"})
        return "failed: record not found"
    decision = await gate(task, target.record, now)
    if decision.action == "skip":
        await _finish(task.id, TaskOutcome.SKIPPED, detail={"skipped": decision.reason})
        return f"skipped: {decision.reason}"
    if decision.action == "defer":
        await asyncio.to_thread(store.defer, task.id, decision.run_at, decision.reason, now)
        return f"deferred: {decision.reason}"

    channel = registry.get(task.channel)
    if channel is None or not channel.supports(task.action):
        await _finish(task.id, TaskOutcome.FAILED, detail={"error": f"{task.channel}.{task.action} is not available"})
        return "failed: channel unavailable"

    work = ChannelTask(
        task_id=task.id,
        journey_id=task.journey_id,
        key=task.key,
        action=task.action,
        params=task.params or {},
        record=target.record,
        intake=task.intake,
        agent=target.agent,
        attempt=task.attempts,
        idempotency_key=idempotency_key(task.journey_id, task.key, task.attempts),
    )
    try:
        result = await channel.execute(work)
    except ChannelError as error:
        state = await _finish(task.id, TaskOutcome.FAILED, detail={"error": str(error)}, retry=error.retryable)
        return f"failed: {error} ({state})"
    except Exception as error:
        logger.exception(f"[dispatch] {task.channel}.{task.action} crashed for task {task.id}")
        state = await _finish(task.id, TaskOutcome.FAILED, detail={"error": f"{type(error).__name__}: {error}"}, retry=True)
        return f"failed: {error} ({state})"

    if result.state == "done":
        outcome = result.outcome or TaskOutcome.SENT
        state = await _finish(task.id, outcome, provider_ref=result.provider_ref, detail=result.detail,
                              retry=outcome in RETRY_ON)
        return f"{outcome.value} ({state})"

    is_call = task.channel == "voice"
    window = CALL_WAIT_SECS if is_call else max(task.response_window_secs, 1)
    on_timeout = TaskOutcome.FAILED if is_call else TaskOutcome.NO_RESPONSE
    if not is_call and not task.response_window_secs:
        state = await _finish(task.id, result.outcome or TaskOutcome.SENT, provider_ref=result.provider_ref, detail=result.detail)
        return f"sent ({state})"
    await asyncio.to_thread(
        store.wait, task.id, provider_ref=result.provider_ref, window_ends_at=now + timedelta(seconds=window),
        outcome=result.outcome, on_timeout=on_timeout, detail=result.detail, now=now,
    )
    return "waiting"
