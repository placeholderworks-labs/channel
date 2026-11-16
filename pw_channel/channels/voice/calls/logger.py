import logging

import httpx

from pw_channel import config
from pw_channel.db import call_records
from pw_channel.observability import log_event
from pw_channel.channels.voice.schema import CallDisposition

logger = logging.getLogger(__name__)


async def log_call_disposition(disposition: CallDisposition) -> None:
    logger.info(f"[disposition] {disposition.model_dump()}")

    log_event(
        "call.ended",
        channel=disposition.channel,
        reference_id=disposition.reference_id or "",
        status=disposition.status,
        duration_secs=disposition.duration_secs,
        transcript_turns=disposition.transcript_turns,
        ended_reason=disposition.ended_reason or "",
    )

    if disposition.reference_id:
        call_records.record_disposition(
            reference_id=disposition.reference_id,
            status=disposition.status,
            duration_secs=disposition.duration_secs,
            transcript_turns=disposition.transcript_turns,
            ended_reason=disposition.ended_reason,
        )

    if not config.DISPOSITION_LOG_WEBHOOK:
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(config.DISPOSITION_LOG_WEBHOOK, json=disposition.model_dump())
    except Exception:
        logger.exception("[disposition] failed to forward to webhook")
