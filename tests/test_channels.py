import asyncio
from datetime import datetime, timezone

import pytest

from pw_channel.core.channel import ChannelError, ChannelTask
from pw_channel.policy.rules import gate
from pw_channel.orchestrator.store import TaskRow
from pw_channel.channels.voice.telephony import lifecycle
from pw_channel.channels.voice.telephony import registry as telephony
from pw_channel.channels.voice.telephony.base import DialRequest, DialResult, TelephonyProvider
from pw_sdk.contracts.outcomes import TaskOutcome
from tests.fakes import record


def task_for(action: str, params: dict | None = None, **record_overrides) -> ChannelTask:
    return ChannelTask(task_id=7, journey_id=3, key="step", action=action, params=params or {},
                       record=record(**record_overrides), idempotency_key="key-7")


class FakeTelephony(TelephonyProvider):
    name = "fake"
    supports_outbound = True

    def __init__(self):
        self.dialled: list[DialRequest] = []

    def enabled(self) -> bool:
        return True

    def websocket_endpoint(self):
        return lambda websocket: None

    async def place_call(self, request: DialRequest) -> DialResult:
        self.dialled.append(request)
        return DialResult(provider_ref="call-123")


def test_voice_channel_dials_through_the_configured_provider(monkeypatch):
    from pw_channel.channels.voice.channel import VoiceChannel

    fake = FakeTelephony()
    monkeypatch.setitem(telephony._instances, "fake", fake)
    telephony.TELEPHONY.add("fake", FakeTelephony)
    monkeypatch.setenv("TELEPHONY_PROVIDER", "fake")
    result = asyncio.run(VoiceChannel().execute(task_for("call")))
    assert result.state == "waiting" and result.provider_ref == "call-123"
    assert fake.dialled[0].phone_e164 == "+919812345678" and fake.dialled[0].task_id == 7
    assert fake.dial_number("+919812345678") == "9812345678" and fake.dial_number("+14155550100") == "14155550100"
    with pytest.raises(ChannelError):
        asyncio.run(VoiceChannel().execute(task_for("call", phone=None)))


def test_call_outcomes_from_lifecycle_state():
    assert lifecycle.outcome_for("RINGING") is TaskOutcome.NO_ANSWER
    assert lifecycle.outcome_for("ACTIVE") is TaskOutcome.ANSWERED
    assert lifecycle.outcome_for("TRANSFERRED") is TaskOutcome.TRANSFERRED


class FakeWhatsApp:
    name = "fake"
    sender = "919999999999"

    def __init__(self):
        self.sent = []

    async def send_template_message(self, to, name, language, components):
        self.sent.append(("template", to, name, components))
        return True

    async def send_interactive_cta_button_with_id(self, to, body, button, url):
        self.sent.append(("cta", to, body, url))
        return "wamid.1"

    async def send_text_message(self, to, text):
        self.sent.append(("text", to, text))
        return True


def test_whatsapp_channel_actions(monkeypatch):
    from pw_channel.channels.whatsapp import sending
    from pw_channel.channels.whatsapp.channel import WhatsAppChannel

    fake = FakeWhatsApp()
    monkeypatch.setattr(sending, "_provider", lambda sender="": fake)

    async def no_dedupe(dedupe, send):
        return await send()

    monkeypatch.setattr(sending, "_guarded", no_dedupe)
    channel = WhatsAppChannel()
    result = asyncio.run(channel.execute(task_for("send_template", {"template": "cart_reminder", "variables": ["first"], "first": "{name}"})))
    assert result.state == "waiting" and result.outcome is TaskOutcome.SENT
    assert fake.sent[0] == ("template", "919812345678", "cart_reminder", [{"type": "body", "parameters": [{"type": "text", "text": "Asha"}]}])
    asyncio.run(channel.execute(task_for("send_link")))
    assert fake.sent[1][0] == "cta" and fake.sent[1][3] == "https://shop.example.com/r/CART-1"
    with pytest.raises(ChannelError):
        asyncio.run(channel.execute(task_for("send_template", {})))


def test_email_channel_renders_tracked_links(monkeypatch):
    from pw_channel.channels.email import channel as email_channel
    from pw_channel.channels.email.providers.base import EmailResult

    sent = []

    class FakeEmail:
        name = "fake"

        def send(self, message):
            sent.append(message)
            return EmailResult(ok=True, message_id="<m1>")

    monkeypatch.setattr(email_channel, "provider", lambda: FakeEmail())
    result = asyncio.run(email_channel.EmailChannel().execute(task_for("send_template", {"template": "cart_followup"})))
    assert result.provider_ref == "<m1>"
    message = sent[0]
    assert message.to == "asha@example.com" and "Delhi to Goa" in message.text
    assert "/api/channel/email/click/" in message.html and "List-Unsubscribe" in message.headers
    with pytest.raises(ChannelError):
        asyncio.run(email_channel.EmailChannel().execute(task_for("send_template", {"template": "cart_followup"}, email=None)))


def row(channel: str) -> TaskRow:
    return TaskRow(id=1, journey_id=1, key="k", channel=channel, action="a", params={}, status="running", outcome=None,
                   attempts=1, max_attempts=1, retry_delay_secs=0, response_window_secs=0, provider_ref=None,
                   reference_id="CART-1", lead_key="phone:+919812345678", intake="", template="t")


def test_policy_gate(monkeypatch):
    from pw_channel.policy import dnd, rules

    monkeypatch.setattr(rules.store, "blocked_channels", lambda lead: {"email"})
    monkeypatch.setattr(rules.intakes, "get", lambda intake: None)
    monkeypatch.setenv("DND_NUMBERS", "+919800000000")
    monkeypatch.setattr(rules, "checker", lambda: dnd.StaticDndList())
    now = datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc)
    assert asyncio.run(gate(row("email"), record(), now)).action == "skip"
    assert asyncio.run(gate(row("voice"), record(phone="+919800000000"), now)).reason == "number is on the DND list"
    no_consent = record(customer={"name": "A", "phone": "+919812345678", "consent": {"call": False}})
    assert asyncio.run(gate(row("voice"), no_consent, now)).reason == "no consent for voice"
    monkeypatch.setenv("CONTACT_HOURS_START", "10:00")
    monkeypatch.setenv("CONTACT_HOURS_END", "19:00")
    early = datetime(2026, 11, 20, 2, 0, tzinfo=timezone.utc)
    decision = asyncio.run(gate(row("voice"), record(), early))
    assert decision.action == "defer" and decision.run_at == datetime(2026, 11, 20, 4, 30, tzinfo=timezone.utc)
    assert asyncio.run(gate(row("voice"), record(), now)).action == "run"
    assert asyncio.run(gate(row("whatsapp"), record(), now)).action == "run"
