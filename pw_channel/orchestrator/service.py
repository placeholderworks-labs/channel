import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pw_channel.core import records
from pw_channel.core.target import CallTarget
from pw_channel.orchestrator import store
from pw_channel.orchestrator.template import JourneyTemplate, TemplateError, load_templates
from pw_sdk import config as client_config
from pw_sdk.contracts.outcomes import TaskOutcome
from pw_channel.db.core import connection, is_configured
from pw_sdk.utils.time import parse_duration
from pw_sdk import OutcomeEvent

logger = logging.getLogger(__name__)


class JourneyError(Exception):
    pass


@dataclass
class Started:
    journey_id: int
    merged: bool
    first_run_at: datetime | None


_templates: dict[str, JourneyTemplate] | None = None


def templates() -> dict[str, JourneyTemplate]:
    global _templates
    if _templates is None:
        from pw_channel.core.registry import enabled_names

        _templates = load_templates(client_config.current().journeys, set(enabled_names()))
    return _templates


def use_templates(found: dict[str, JourneyTemplate] | None) -> None:
    global _templates
    _templates = found


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_db() -> None:
    if not is_configured():
        raise JourneyError("journeys need Postgres; set DATABASE_URL")


def start_journey(template_name: str, target: CallTarget, now: datetime | None = None) -> Started:
    _require_db()
    now = now or _now()
    template = templates().get(template_name)
    if template is None:
        raise JourneyError(f"journey template {template_name!r} is not configured")
    lead_key = records.lead_key(target.record)
    scheduled = target.record.schedule.scheduled_at
    start_at = scheduled if scheduled and scheduled > now else now
    with connection() as conn:
        existing = store.active_journey(conn, lead_key, template.name)
        if existing and template.on_new_record == "merge":
            conn.execute(
                "UPDATE journeys SET reference_id = %s, updated_at = %s WHERE id = %s",
                (target.reference_id, now, existing["id"]),
            )
            conn.execute(
                "UPDATE records SET journey_id = %s WHERE reference_id = %s", (existing["id"], target.reference_id)
            )
            return Started(existing["id"], True, None)
        if existing:
            store.stop_journey(conn, existing["id"], "stopped", "replaced by a newer record", now)
        expires = now + timedelta(seconds=template.expires_after_secs) if template.expires_after_secs else None
        journey_id, first_run = store.insert_journey(
            conn,
            lead_key=lead_key,
            reference_id=target.reference_id,
            intake=target.intake,
            template=template.name,
            steps=template.steps,
            now=start_at,
            expires_at=expires,
        )
        conn.execute("UPDATE records SET journey_id = %s WHERE reference_id = %s", (journey_id, target.reference_id))
    logger.info(f"[journeys] started {template.name} #{journey_id} for {target.reference_id}")
    return Started(journey_id, False, first_run)


def signal(kind: str, *, reference_id: str = "", lead_key: str = "", journey_id: int | None = None,
           source: str = "", payload: dict | None = None, dedupe_key: str | None = None) -> int | None:
    _require_db()
    return store.insert_event(kind=kind, reference_id=reference_id, lead_key=lead_key, journey_id=journey_id,
                              source=source, payload=payload, dedupe_key=dedupe_key)


def record_outcome(event: OutcomeEvent, intake: str, raw: Any) -> bool:
    _require_db()
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO outcome_events (event_id, reference_id, kind, intake, canonical, raw)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING RETURNING id
            """,
            (event.event_id, event.reference_id, event.kind.value, intake,
             json.dumps(event.model_dump(mode="json")), json.dumps(raw, default=str)),
        ).fetchone()
    if row is None:
        return False
    signal(event.kind.value, reference_id=event.reference_id, source=f"intake:{intake}",
           payload=event.model_dump(mode="json"), dedupe_key=f"outcome:{event.event_id}")
    return True


def finish_task(task_id: int, outcome: TaskOutcome, *, provider_ref: str | None = None, detail: dict | None = None,
                retry: bool = False) -> str:
    return store.finish(task_id, outcome, now=_now(), provider_ref=provider_ref, detail=detail, retry=retry)


def complete_by_ref(provider_ref: str, outcome: TaskOutcome, detail: dict | None = None) -> str:
    found = store.task_by_provider_ref(provider_ref)
    if found is None:
        return "unknown"
    retry = outcome in (TaskOutcome.NO_ANSWER, TaskOutcome.BUSY)
    return store.finish(found.id, outcome, now=_now(), detail=detail, retry=retry)


def complete_task(task_id: int, outcome: TaskOutcome, detail: dict | None = None) -> str:
    retry = outcome in (TaskOutcome.NO_ANSWER, TaskOutcome.BUSY)
    return store.finish(task_id, outcome, now=_now(), detail=detail, retry=retry)


RESPONSE_OUTCOMES = {
    "whatsapp.replied": ("whatsapp", TaskOutcome.REPLIED),
    "email.replied": ("email", TaskOutcome.REPLIED),
    "email.clicked": ("email", TaskOutcome.CLICKED),
}
CHANNEL_OF_EVENT = {"call": "voice", "whatsapp": "whatsapp", "email": "email"}


def _apply_rule(conn, journey: dict, template: JourneyTemplate, rule, event: dict, now: datetime) -> str:
    journey_id = journey["id"]
    payload = event.get("payload") or {}
    if rule.action == "ignore":
        return "ignored"
    if rule.action == "complete":
        count = store.stop_journey(conn, journey_id, "converted", event["kind"], now)
        return f"converted, {count} step(s) cancelled"
    if rule.action == "stop":
        count = store.stop_journey(conn, journey_id, "stopped", event["kind"], now)
        return f"stopped, {count} step(s) cancelled"
    if rule.action == "cancel":
        return "cancelled " + rule.target if store.cancel_task(conn, journey_id, rule.target, event["kind"], now) else "nothing to cancel"
    if rule.action == "pause":
        store.pause_journey(conn, journey_id, now + timedelta(seconds=parse_duration(rule.target)), now)
        return f"paused {rule.target}"
    if rule.action == "reschedule":
        when_text = payload.get("at") or payload.get("callback_at")
        when = datetime.fromisoformat(str(when_text).replace("Z", "+00:00")) if when_text else now + timedelta(hours=2)
        key = rule.target
        if key == "*":
            key = payload.get("step") or next((s.key for s in template.steps if s.channel == "voice"), "")
        return f"rescheduled {key}" if key and store.reschedule_task(conn, journey_id, key, when, now) else "nothing to reschedule"
    if rule.action == "block":
        channel = CHANNEL_OF_EVENT.get(str(payload.get("channel") or ""), payload.get("channel") or "")
        channels = [channel] if channel else [s.channel for s in template.steps]
        for name in set(channels):
            store.block_channel(conn, journey["lead_key"], name, event["kind"])
            conn.execute(
                """
                UPDATE journey_tasks SET status = 'cancelled', outcome = 'skipped', updated_at = %s
                 WHERE journey_id = %s AND channel = %s AND status IN ('blocked', 'ready', 'waiting') RETURNING id
                """,
                (now, journey_id, name),
            )
        for row in conn.execute(
            "SELECT id FROM journey_tasks WHERE journey_id = %s AND status = 'cancelled'", (journey_id,)
        ).fetchall():
            store.resolve_dependents(conn, row["id"], now)
        store.close_if_finished(conn, journey_id, now)
        return f"blocked {', '.join(sorted(set(channels)))}"
    if rule.action == "start":
        return "start:" + rule.target
    return "unknown rule"


def process_events(limit: int = 50, now: datetime | None = None) -> int:
    now = now or _now()
    handled = 0
    starts: list[tuple[str, str]] = []
    with connection() as conn:
        for event in store.claim_events(conn, limit):
            outcomes = []
            response = RESPONSE_OUTCOMES.get(event["kind"])
            journeys = store.journeys_for_event(conn, event)
            if response and journeys:
                waiting = store.waiting_task_for(conn, journeys[0]["lead_key"], response[0])
                if waiting:
                    conn.execute(
                        """
                        UPDATE journey_tasks SET status = 'done', outcome = %s, window_ends_at = NULL, updated_at = %s
                         WHERE id = %s
                        """,
                        (response[1].value, now, waiting["id"]),
                    )
                    store.resolve_dependents(conn, waiting["id"], now)
                    store.close_if_finished(conn, waiting["journey_id"], now)
                    outcomes.append(f"{waiting['key']} {response[1].value}")
            for journey in journeys:
                template = templates().get(journey["template"])
                if template is None:
                    continue
                for rule in template.rules_for(event["kind"]):
                    result = _apply_rule(conn, journey, template, rule, event, now)
                    if result.startswith("start:"):
                        starts.append((rule.target, journey["reference_id"]))
                        store.stop_journey(conn, journey["id"], "stopped", f"{event['kind']} started {rule.target}", now)
                    outcomes.append(f"#{journey['id']} {result}")
            if not journeys and event.get("reference_id"):
                starter = (client_config.current().get("event_journeys") or {}).get(event["kind"])
                if starter:
                    starts.append((starter, event["reference_id"]))
                    outcomes.append(f"starting {starter}")
            store.mark_event(conn, event["id"], "; ".join(outcomes) or "no active journey", now)
            handled += 1
    for template_name, reference_id in starts:
        target = records.get(reference_id=reference_id)
        if target is not None:
            try:
                start_journey(template_name, target, now)
            except JourneyError as error:
                logger.error(f"[journeys] could not start {template_name} for {reference_id}: {error}")
    return handled


def sweep(now: datetime | None = None) -> dict[str, int]:
    now = now or _now()
    requeued = store.requeue_expired_leases(now)
    expired = 0
    for row in store.expired_windows(now):
        outcome = TaskOutcome(row["on_timeout"] or TaskOutcome.NO_RESPONSE.value)
        store.finish(row["id"], outcome, now=now, detail={"timed_out": True})
        expired += 1
    journeys = store.expire_journeys(now)
    return {"requeued": requeued, "windows": expired, "journeys": journeys}


__all__ = [
    "JourneyError",
    "Started",
    "TemplateError",
    "complete_by_ref",
    "complete_task",
    "finish_task",
    "process_events",
    "record_outcome",
    "signal",
    "start_journey",
    "sweep",
    "templates",
    "use_templates",
]
