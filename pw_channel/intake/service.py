import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pw_channel.core import records
from pw_channel.core.target import CallTarget
from pw_channel.intake import adapters
from pw_channel.intake import events as ingestion_events
from pw_channel.intake import intakes
from pw_channel.intake.validation import allowed_countries, check_schedule
from pw_sdk.utils import phone as phones
from pw_sdk import AdapterContext, CustomerRecord, OutcomeEvent, TransformResult

logger = logging.getLogger(__name__)

TRANSFORM_TIMEOUT_SECS = float(os.getenv("ADAPTER_TIMEOUT_SECS", "5"))


@dataclass
class Delivery:
    results: list[dict] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for item in self.results if item["status"] == status)

    def status_code(self) -> int:
        accepted = self.count("scheduled") + self.count(ingestion_events.AWAITING) + self.count("duplicate") + self.count("merged")
        if accepted:
            return 202
        if self.count("failed") and not self.count("rejected"):
            return 503
        return 422

    def body(self) -> dict:
        return {
            "accepted": self.count("scheduled") + self.count("merged"),
            "trigger_pending": self.count(ingestion_events.AWAITING),
            "duplicates": self.count("duplicate"),
            "skipped": self.count("skipped"),
            "rejected": self.count("rejected"),
            "failed": self.count("failed"),
            "results": self.results,
        }


def context_for(intake: dict, received_at: datetime) -> AdapterContext:
    config = dict(intake.get("adapterConfig") or {})
    if intake.get("adapter") == "builtin.fields":
        config.setdefault("fields", intakes.all_fields(intake))
    return AdapterContext(
        intake_id=intake["id"],
        received_at=received_at,
        timezone=os.getenv("CLIENT_TIMEZONE", "Asia/Kolkata"),
        config=config,
    )


async def transform(intake: dict, payload: Any, kind: str, received_at: datetime) -> tuple[TransformResult, dict]:
    adapter = adapters.get(intake.get("adapter") or "builtin.fields")
    method = adapter.transform_records if kind == "records" else adapter.transform_events
    ctx = context_for(intake, received_at)
    result = await asyncio.wait_for(asyncio.to_thread(method, payload, ctx), timeout=TRANSFORM_TIMEOUT_SECS)
    return result, adapter.describe()


def core_problems(record: CustomerRecord, now: datetime) -> list[dict]:
    problems = []
    if record.customer.phone:
        country = phones.country_of(record.customer.phone)
        if country not in allowed_countries():
            problems.append({"field": "customer.phone", "error": f"numbers from {country or 'this country'} are not allowed"})
    schedule_problem = check_schedule(record.schedule.scheduled_at, now)
    if schedule_problem:
        problems.append({"field": "schedule.scheduled_at", "error": schedule_problem})
    return problems


def _payload_at(payload: Any, index: int) -> Any:
    if isinstance(payload, list):
        return payload[index] if index < len(payload) else None
    if isinstance(payload, dict):
        for key in ("records", "events", "items", "data"):
            if isinstance(payload.get(key), list):
                return payload[key][index] if index < len(payload[key]) else None
    return payload


async def _log(**fields) -> int:
    return await asyncio.to_thread(ingestion_events.create, **fields)


async def accept_record(record: CustomerRecord, raw: Any, intake: dict, index: int, *, source_ip: str, adapter: dict,
                        dedupe: bool = True, now: datetime | None = None) -> dict:
    from pw_channel.orchestrator import service as journeys

    now = now or datetime.now(timezone.utc)
    identity = {
        "source_ip": source_ip,
        "reference_id": record.ref.reference_id,
        "phone_no": record.customer.phone or "",
        "customer_name": record.customer.name,
        "payload": raw,
        "canonical": record.model_dump(mode="json"),
        "adapter": adapter.get("name", ""),
        "adapter_version": adapter.get("version", ""),
        "schema_version": record.schema_version,
        "channel": ",".join(sorted(intake.get("channels") or [])) or "journey",
        "agent": intake.get("agent") or "",
        "source": intake["id"],
        "intake": intake["id"],
    }
    base = {"index": index, "reference_id": record.ref.reference_id}

    problems = core_problems(record, now)
    if problems:
        event_id = await _log(**identity, status="rejected", reason="; ".join(f"{p['field']} {p['error']}" for p in problems), errors=problems)
        return {**base, "ingestion_id": event_id, "status": "rejected", "errors": problems}

    window = intake.get("dedupeWindowSecs")
    if dedupe and window:
        duplicate = await asyncio.to_thread(
            ingestion_events.find_active_duplicate, record.ref.reference_id, record.customer.phone or "", window
        )
        if duplicate:
            reason = f"duplicate of ingestion #{duplicate['id']} within {window:.0f}s"
            event_id = await _log(**identity, status="duplicate", reason=reason)
            return {**base, "ingestion_id": event_id, "status": "duplicate", "duplicate_of": duplicate["id"], "reason": reason}

    target = CallTarget(record=record, intake=intake["id"], agent=intake.get("agent") or "", received_at=now)
    await asyncio.to_thread(records.save, target)

    template = intake.get("journey") or ""
    if not template:
        event_id = await _log(**identity, status=ingestion_events.AWAITING, reason="no journey is set on this intake")
        return {**base, "ingestion_id": event_id, "status": ingestion_events.AWAITING, "reason": "no journey is set on this intake"}

    try:
        started = await asyncio.to_thread(journeys.start_journey, template, target, now)
    except journeys.JourneyError as error:
        event_id = await _log(**identity, status="failed", reason=str(error))
        return {**base, "ingestion_id": event_id, "status": "failed", "reason": str(error)}

    status = "merged" if started.merged else "scheduled"
    event_id = await _log(**identity, status=status if status == "scheduled" else "duplicate",
                          reason="merged into the active journey" if started.merged else "",
                          scheduled_for=started.first_run_at, journey_id=started.journey_id)
    return {
        **base,
        "ingestion_id": event_id,
        "status": status,
        "journey_id": started.journey_id,
        "scheduled_for": started.first_run_at.isoformat() if started.first_run_at else None,
    }


async def ingest_records(intake: dict, payload: Any, *, source_ip: str = "", dedupe: bool = True) -> Delivery:
    now = datetime.now(timezone.utc)
    delivery = Delivery()
    count = len(payload) if isinstance(payload, list) else 1
    try:
        result, adapter = await transform(intake, payload, "records", now)
    except (asyncio.TimeoutError, Exception) as error:
        reason = "adapter timed out" if isinstance(error, asyncio.TimeoutError) else f"adapter failed: {type(error).__name__}: {error}"
        logger.error(f"[intake] {intake['id']}: {reason}")
        for index in range(count):
            event_id = await _log(source_ip=source_ip, status="rejected", reason=reason, payload=_payload_at(payload, index),
                                  adapter=intake.get("adapter", ""), source=intake["id"], intake=intake["id"])
            delivery.results.append({"index": index, "ingestion_id": event_id, "status": "rejected",
                                     "errors": [{"field": "", "error": reason}]})
        return delivery

    for item in result.items:
        delivery.results.append(await accept_record(item.value, _payload_at(payload, item.index), intake, item.index,
                                                    source_ip=source_ip, adapter=adapter, dedupe=dedupe, now=now))
    for rejection in result.rejections:
        error = {"field": rejection.field or "", "error": rejection.error}
        event_id = await _log(source_ip=source_ip, status="rejected", reason=f"{error['field'] or 'record'} {error['error']}",
                              errors=[error], payload=_payload_at(payload, rejection.index), adapter=adapter["name"],
                              adapter_version=adapter["version"], source=intake["id"], intake=intake["id"])
        delivery.results.append({"index": rejection.index, "ingestion_id": event_id, "status": "rejected", "errors": [error]})
    for skipped in result.skipped:
        delivery.results.append({"index": skipped.index, "status": "skipped", "reason": skipped.reason})
    delivery.results.sort(key=lambda item: item["index"])
    return delivery


async def ingest_events(intake: dict, payload: Any) -> Delivery:
    from pw_channel.orchestrator import service as journeys

    now = datetime.now(timezone.utc)
    delivery = Delivery()
    try:
        result, adapter = await transform(intake, payload, "events", now)
    except (asyncio.TimeoutError, Exception) as error:
        reason = "adapter timed out" if isinstance(error, asyncio.TimeoutError) else f"adapter failed: {error}"
        delivery.results.append({"index": 0, "status": "rejected", "errors": [{"field": "", "error": reason}]})
        return delivery
    for item in result.items:
        event: OutcomeEvent = item.value
        applied = await asyncio.to_thread(journeys.record_outcome, event, intake["id"], _payload_at(payload, item.index))
        delivery.results.append({"index": item.index, "status": "scheduled", "event_id": event.event_id,
                                 "kind": event.kind.value, "applied": applied})
    for rejection in result.rejections:
        delivery.results.append({"index": rejection.index, "status": "rejected",
                                 "errors": [{"field": rejection.field or "", "error": rejection.error}]})
    for skipped in result.skipped:
        delivery.results.append({"index": skipped.index, "status": "skipped", "reason": skipped.reason})
    delivery.results.sort(key=lambda item: item["index"])
    return delivery
