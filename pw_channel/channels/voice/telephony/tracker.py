import asyncio
import logging
import time
from collections import deque

from pw_channel.channels.voice.states import PendingCall

logger = logging.getLogger(__name__)

_MAX_TRACKED = 20

_pending: deque[PendingCall] = deque(maxlen=_MAX_TRACKED)


def record_origination(
    *, ref_id: str, reference_id: str, phone_no: str, wait_secs: int
) -> None:
    call = PendingCall(ref_id, reference_id, phone_no)
    _pending.append(call)
    asyncio.create_task(_report_if_never_connected(call, wait_secs))


def note_websocket_connected() -> PendingCall | None:
    for call in reversed(_pending):
        if not call.connected:
            call.connected = True
            logger.info(
                f"[acefone] websocket matched to ref_id={call.ref_id} "
                f"({time.monotonic() - call.queued_at:.1f}s after origination)"
            )
            return call
    return None


async def _report_if_never_connected(call: PendingCall, wait_secs: int) -> None:
    await asyncio.sleep(wait_secs)
    if call.connected:
        return

    logger.warning(
        f"[acefone] NO websocket ever opened for ref_id={call.ref_id} "
        f"reference_id={call.reference_id} phone={call.phone_no} within {wait_secs}s. "
        f"Acefone accepted the origination but never streamed the call to us. "
        f"Most likely: the call was not answered, OR this API key's destination "
        f"is not routed to the bi-directional streaming endpoint. "
        f"Give this ref_id to Acefone support to trace the call."
    )
