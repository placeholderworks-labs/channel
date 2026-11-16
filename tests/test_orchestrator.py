import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from pw_channel.core import records
from pw_channel.core.target import CallTarget
from pw_channel.orchestrator import service, store
from pw_channel.orchestrator.template import load_templates
from pw_channel.orchestrator.worker import Worker
from pw_sdk.contracts.outcomes import TaskOutcome
from pw_channel.db.core import connection
from pw_sdk import EventKind, OutcomeEvent
from tests.fakes import FakeChannel, install_fakes, record

NOW = datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc)

JOURNEYS = {
    "cart_recovery": {
        "steps": [
            {"key": "whatsapp", "channel": "whatsapp", "action": "send_template", "params": {"template": "cart"},
             "delay": "5m", "response_window": "30m"},
            {"key": "call", "channel": "voice", "depends_on": ["whatsapp"], "when": ["no_response"], "retries": 1,
             "retry_after": "15m"},
            {"key": "email", "channel": "email", "depends_on": ["call"], "when": ["no_answer", "failed"], "delay": "2h",
             "response_window": "24h"},
        ],
        "on": {"whatsapp.replied": "cancel:call", "link.clicked": "pause:30m", "payment.failed": "start:payment_failed"},
        "expires_after": "72h",
    },
    "payment_failed": {"steps": [{"key": "retry_link", "channel": "whatsapp", "action": "send_link"}]},
    "fan_in": {
        "steps": [
            {"key": "a", "channel": "whatsapp", "action": "send_text", "params": {"text": "hi"}},
            {"key": "b", "channel": "email", "action": "send_template", "params": {"template": "t"}},
            {"key": "any", "channel": "voice", "depends_on": ["a", "b"], "join": "any", "when": ["sent"]},
            {"key": "all", "channel": "voice", "depends_on": ["a", "b"], "when": ["sent"]},
        ],
    },
}


@pytest.fixture
def journeys(db):
    service.use_templates(load_templates(JOURNEYS, {"voice", "whatsapp", "email"}))
    yield
    service.use_templates(None)


def start(reference="CART-1", template="cart_recovery", **kwargs):
    target = CallTarget(record=record(reference, **kwargs), intake="demo_cart", agent="callvoice")
    records.save(target)
    return service.start_journey(template, target, NOW)


def tasks(journey_id: int) -> dict[str, dict]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM journey_tasks WHERE journey_id = %s", (journey_id,)).fetchall()
    return {row["key"]: row for row in rows}


def journey(journey_id: int) -> dict:
    with connection() as conn:
        return conn.execute("SELECT * FROM journeys WHERE id = %s", (journey_id,)).fetchone()


def tick(at: datetime, worker: Worker | None = None) -> int:
    return asyncio.run((worker or Worker(poll_secs=0.01)).tick(at))


def test_full_recovery_path_whatsapp_then_call_then_email(journeys):
    fakes = install_fakes()
    started = start()
    assert not started.merged and started.first_run_at == NOW + timedelta(minutes=5)
    state = tasks(started.journey_id)
    assert state["whatsapp"]["status"] == "ready" and state["call"]["status"] == "blocked"

    assert tick(NOW) == 0
    assert tick(NOW + timedelta(minutes=5)) == 1
    assert tasks(started.journey_id)["whatsapp"]["status"] == "waiting"
    assert fakes["whatsapp"].calls[0].params == {"template": "cart"}

    tick(NOW + timedelta(minutes=36))
    state = tasks(started.journey_id)
    assert state["whatsapp"]["outcome"] == "no_response" and state["call"]["status"] in ("ready", "waiting")

    tick(NOW + timedelta(minutes=37))
    state = tasks(started.journey_id)
    assert state["call"]["status"] == "waiting" and len(fakes["voice"].calls) == 1

    assert service.complete_by_ref(state["call"]["provider_ref"], TaskOutcome.NO_ANSWER) == "retrying"
    state = tasks(started.journey_id)
    assert state["call"]["status"] == "ready" and state["email"]["status"] == "blocked"

    tick(NOW + timedelta(minutes=53))
    state = tasks(started.journey_id)
    assert len(fakes["voice"].calls) == 2 and state["call"]["attempts"] == 2
    assert service.complete_by_ref(state["call"]["provider_ref"], TaskOutcome.NO_ANSWER) == "done"

    state = tasks(started.journey_id)
    assert state["email"]["status"] == "ready"
    tick(NOW + timedelta(hours=3))
    assert len(fakes["email"].calls) == 1 and tasks(started.journey_id)["email"]["status"] == "waiting"


def test_booking_confirmed_converts_and_cancels(journeys):
    install_fakes()
    started = start()
    tick(NOW + timedelta(minutes=5))
    event = OutcomeEvent(event_id="evt-1", reference_id="CART-1", kind=EventKind.BOOKING_CONFIRMED, occurred_at=NOW)
    assert service.record_outcome(event, "demo_events", {"raw": True}) is True
    assert service.record_outcome(event, "demo_events", {"raw": True}) is False
    service.process_events(now=NOW + timedelta(minutes=6))
    assert journey(started.journey_id)["status"] == "converted"
    assert {row["status"] for row in tasks(started.journey_id).values()} == {"cancelled"}
    with connection() as conn:
        processed = conn.execute("SELECT result FROM journey_events").fetchone()["result"]
    assert "converted" in processed


def test_whatsapp_reply_completes_step_and_cancels_call(journeys):
    install_fakes()
    started = start()
    tick(NOW + timedelta(minutes=5))
    service.signal("whatsapp.replied", lead_key="phone:+919812345678", payload={"channel": "whatsapp"}, dedupe_key="wa:1")
    service.signal("whatsapp.replied", lead_key="phone:+919812345678", payload={"channel": "whatsapp"}, dedupe_key="wa:1")
    service.process_events(now=NOW + timedelta(minutes=7))
    state = tasks(started.journey_id)
    assert state["whatsapp"]["outcome"] == "replied"
    assert state["call"]["status"] == "skipped" and state["email"]["status"] == "skipped"
    assert journey(started.journey_id)["status"] == "completed"


def test_same_customer_new_cart_merges(journeys):
    install_fakes()
    first = start("CART-1")
    second = start("CART-2")
    assert second.merged and second.journey_id == first.journey_id
    assert journey(first.journey_id)["reference_id"] == "CART-2"
    other = start("CART-3", phone="+919811111111")
    assert not other.merged and other.journey_id != first.journey_id


def test_link_click_pauses(journeys):
    install_fakes()
    started = start()
    service.signal("link.clicked", reference_id="CART-1", payload={})
    service.process_events(now=NOW)
    assert journey(started.journey_id)["paused_until"] == NOW + timedelta(minutes=30)
    assert tick(NOW + timedelta(minutes=10)) == 0
    assert tick(NOW + timedelta(minutes=31)) == 1


def test_callback_reschedules_call(journeys):
    install_fakes()
    started = start()
    callback = NOW + timedelta(hours=10)
    service.signal("call.callback", reference_id="CART-1", payload={"at": callback.isoformat()})
    service.process_events(now=NOW)
    state = tasks(started.journey_id)
    assert state["call"]["status"] == "ready" and state["call"]["run_at"] == callback


def test_not_interested_and_opt_out(journeys):
    install_fakes()
    started = start()
    service.signal("opt_out", lead_key="phone:+919812345678", payload={"channel": "whatsapp"})
    service.process_events(now=NOW)
    state = tasks(started.journey_id)
    assert state["whatsapp"]["status"] == "cancelled" and state["call"]["status"] == "skipped"
    assert store.blocked_channels("phone:+919812345678") == {"whatsapp"}

    second = start("CART-9", phone="+919822222222")
    service.signal("call.not_interested", reference_id="CART-9", payload={})
    service.process_events(now=NOW)
    assert journey(second.journey_id)["status"] == "stopped"


def test_payment_failed_starts_other_journey(journeys):
    install_fakes()
    started = start()
    service.record_outcome(OutcomeEvent(event_id="evt-pf", reference_id="CART-1", kind=EventKind.PAYMENT_FAILED,
                                        occurred_at=NOW), "demo_events", {})
    service.process_events(now=NOW)
    assert journey(started.journey_id)["status"] == "stopped"
    with connection() as conn:
        rows = conn.execute("SELECT template, status FROM journeys ORDER BY id").fetchall()
    assert [(r["template"], r["status"]) for r in rows] == [("cart_recovery", "stopped"), ("payment_failed", "active")]


def test_fan_in_any_and_all(journeys):
    fakes = install_fakes(email=FakeChannel("email", fail=True))
    started = start(template="fan_in")
    tick(NOW)
    state = tasks(started.journey_id)
    assert state["a"]["status"] == "done" and state["a"]["outcome"] == "sent"
    assert state["b"]["status"] == "done" and state["b"]["outcome"] == "failed"
    assert state["any"]["status"] == "ready"
    assert state["all"]["status"] == "skipped"
    assert len(fakes["email"].calls) == 1


def test_contact_hours_defer(journeys, monkeypatch):
    install_fakes()
    monkeypatch.setenv("MESSAGE_HOURS_START", "09:00")
    monkeypatch.setenv("MESSAGE_HOURS_END", "21:00")
    started = start()
    night = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)
    tick(night)
    state = tasks(started.journey_id)
    assert state["whatsapp"]["status"] == "ready" and state["whatsapp"]["attempts"] == 0
    assert state["whatsapp"]["run_at"] == datetime(2026, 11, 21, 3, 30, tzinfo=timezone.utc)


def test_no_double_claims_and_lease_recovery(journeys):
    install_fakes()
    for index in range(6):
        start(f"CART-{index}", phone=f"+91981234560{index}")
    at = NOW + timedelta(minutes=5)
    first = store.claim_ready("w1", 4, 60, at)
    second = store.claim_ready("w2", 4, 60, at)
    assert len(first) == 4 and len(second) == 2
    assert not {t.id for t in first} & {t.id for t in second}
    assert store.claim_ready("w3", 4, 60, at) == []
    assert store.requeue_expired_leases(at + timedelta(minutes=5)) == 6
    assert len(store.claim_ready("w4", 10, 60, at + timedelta(minutes=5))) == 6


def test_expiry_and_scheduled_start(journeys):
    install_fakes()
    later = NOW + timedelta(days=1)
    target = CallTarget(record=record("CART-S", schedule={"scheduled_at": later.isoformat()}), intake="demo_cart")
    records.save(target)
    started = service.start_journey("cart_recovery", target, NOW)
    assert started.first_run_at == later + timedelta(minutes=5)
    assert service.sweep(NOW + timedelta(hours=80))["journeys"] == 1
    assert journey(started.journey_id)["status"] == "expired"


def test_channel_failure_is_retried_then_fails(journeys):
    install_fakes(whatsapp=FakeChannel("whatsapp", fail=True))
    started = start()
    tick(NOW + timedelta(minutes=5))
    state = tasks(started.journey_id)
    assert state["whatsapp"]["status"] == "done" and state["whatsapp"]["outcome"] == "failed"
    assert state["call"]["status"] == "skipped"
