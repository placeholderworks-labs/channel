from pw_channel.core.channel import Channel, ChannelError, ChannelResult, ChannelTask
from pw_sdk.contracts.outcomes import TaskOutcome


class WhatsAppChannel(Channel):
    name = "whatsapp"
    actions = ("send_template", "send_text", "send_link")

    async def execute(self, task: ChannelTask) -> ChannelResult:
        from pw_channel.channels.whatsapp import sending

        record = task.record
        if not record.customer.phone:
            raise ChannelError("no phone number for WhatsApp", retryable=False)
        params = task.params
        name = record.customer.name
        reference = record.ref.reference_id
        if task.action == "send_template":
            template = params.get("template")
            if not template:
                raise ChannelError("send_template needs params.template", retryable=False)
            values = [str(params.get(key, "")).format(name=name, reference_id=reference, summary=record.spoken_summary(),
                                                      resume_url=record.journey.resume_url or "")
                      for key in params.get("variables", [])]
            components = params.get("components") or (
                [{"type": "body", "parameters": [{"type": "text", "text": value} for value in values]}] if values else []
            )
            outcome = await sending.send_template(record.customer.phone, template, params.get("language", "en"), components,
                                                  dedupe=task.idempotency_key, task_id=task.task_id)
        elif task.action == "send_link":
            body, button = sending.resume_message(params.get("event", "resume_link"), name, reference)
            link = sending.resume_link(record.journey.resume_url or "", reference)
            if not link:
                raise ChannelError("the record has no resume_url", retryable=False)
            outcome = await sending.send_cta(record.customer.phone, body, button, link, dedupe=task.idempotency_key,
                                             task_id=task.task_id)
        else:
            text = str(params.get("text", "")).format(name=name, reference_id=reference, summary=record.spoken_summary())
            if not text:
                raise ChannelError("send_text needs params.text", retryable=False)
            outcome = await sending.send_text(record.customer.phone, text, dedupe=task.idempotency_key, task_id=task.task_id)
        if not outcome.ok:
            raise ChannelError(outcome.error or "WhatsApp send failed")
        return ChannelResult.waiting(outcome.message_id, outcome=TaskOutcome.SENT, provider=outcome.provider)

    def routes(self):
        from pw_channel.channels.whatsapp import outbound, webhooks
        from pw_channel.channels.whatsapp.campaigns import routes as campaigns

        return [webhooks.router, webhooks.legacy_router, outbound.router, outbound.legacy_router, campaigns.router]

    async def startup(self) -> None:
        from pw_channel.channels.whatsapp.campaigns.store import campaign_store
        from pw_channel.channels.whatsapp.providers.pool import pool
        from pw_channel.channels.whatsapp.sessions import session_manager

        pool()
        try:
            await session_manager.connect()
        except Exception:
            pass
        try:
            await campaign_store.connect()
        except Exception:
            pass

    async def shutdown(self) -> None:
        from pw_channel.channels.whatsapp.campaigns.store import campaign_store
        from pw_channel.channels.whatsapp.sessions import session_manager

        await session_manager.disconnect()
        await campaign_store.disconnect()
