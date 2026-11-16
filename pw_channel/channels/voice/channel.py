import asyncio
import os
import logging

from pw_channel.core.channel import Channel, ChannelError, ChannelResult, ChannelTask
from pw_channel.db import call_records, call_sessions
from pw_channel.channels.voice.telephony import registry as telephony
from pw_channel.channels.voice.telephony.base import DialRequest, TelephonyError

logger = logging.getLogger(__name__)


class VoiceChannel(Channel):
    name = "voice"
    actions = ("call",)

    async def execute(self, task: ChannelTask) -> ChannelResult:
        record = task.record
        if not record.customer.phone:
            raise ChannelError("no phone number to dial", retryable=False)
        try:
            provider = telephony.outbound()
            result = await provider.place_call(DialRequest(
                phone_e164=record.customer.phone,
                reference_id=record.ref.reference_id,
                customer_name=record.customer.name,
                task_id=task.task_id,
                idempotency_key=task.idempotency_key,
            ))
        except TelephonyError as error:
            await asyncio.to_thread(
                call_records.record_request, channel=os.getenv("TELEPHONY_PROVIDER", "acefone"),
                phone_no=record.customer.phone, reference_id=record.ref.reference_id,
                customer_name=record.customer.name, status="failed", triggered_by=f"journey:{task.journey_id}",
                error=str(error),
            )
            raise ChannelError(str(error), retryable=error.retryable) from error
        record_id = await asyncio.to_thread(
            call_records.record_request, channel=provider.name, phone_no=record.customer.phone,
            reference_id=record.ref.reference_id, customer_name=record.customer.name, status="placed",
            triggered_by=f"journey:{task.journey_id}", provider_call_id=result.provider_ref,
            provider_response=result.raw, cart=record.model_dump(mode="json"),
        )
        if record_id and result.session_id:
            await asyncio.to_thread(call_sessions.update, result.session_id, call_record_id=record_id)
        logger.info(f"[voice] task {task.task_id} dialled {record.ref.reference_id} via {provider.name} ref={result.provider_ref}")
        return ChannelResult.waiting(result.provider_ref, call_record_id=record_id, provider=provider.name)

    async def startup(self) -> None:
        for provider in telephony.all_providers():
            await provider.start()

    async def shutdown(self) -> None:
        for provider in telephony.all_providers():
            await provider.stop()
