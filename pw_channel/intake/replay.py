import asyncio
from datetime import datetime, timezone

from pw_channel.intake import events as ingestion_events
from pw_channel.intake import intakes, service
from pw_channel.intake.labels import PHONE_TEST
from pw_channel.db.core import connection, is_configured


def phone_test_intake(agent: str, base: dict | None = None) -> dict:
    intake = dict(base or {})
    intake.update({
        "id": PHONE_TEST,
        "name": "Phone test",
        "agent": agent or intake.get("agent") or "",
        "adapter": intake.get("adapter") or "builtin.fields",
        "adapterConfig": intake.get("adapterConfig") or {},
        "journey": "single_call",
        "dedupeWindowSecs": None,
        "fields": intake.get("fields") or [],
        "enabled": True,
    })
    return intake


async def replay_event(event: dict, actor: str) -> dict:
    payload = event.get("payload")
    if not isinstance(payload, (dict, list)) or (isinstance(payload, dict) and "_raw_body" in payload):
        return {"status": "rejected", "reason": "this record has no usable payload to replay"}
    intake = intakes.get(event.get("intake") or event.get("source") or "")
    if intake is None:
        return {"status": "rejected", "reason": "the intake this record came in on no longer exists"}
    delivery = await service.ingest_records(intake, payload, source_ip=f"replay:{actor}", dedupe=False)
    result = delivery.results[0] if delivery.results else {"status": "rejected", "reason": "nothing to replay"}
    if result.get("ingestion_id"):
        await asyncio.to_thread(
            ingestion_events.update, event["id"],
            reason=f"{event.get('reason') or event['status']} · replayed as #{result['ingestion_id']} by {actor}",
        )
    return result


async def release(intake_id: str, actor: str) -> dict:
    intake = intakes.get(intake_id)
    if intake is None:
        return {"released": 0, "reason": "no such intake"}
    if not intake.get("journey"):
        return {"released": 0, "reason": "set a journey on this intake first"}
    held = await asyncio.to_thread(ingestion_events.recent, 500, ingestion_events.AWAITING, "", "", intake_id)
    released = 0
    for event in held:
        result = await replay_event(event, actor)
        if result.get("status") in ("scheduled", "merged"):
            released += 1
            await asyncio.to_thread(ingestion_events.update, event["id"], status="cancelled")
    return {"released": released, "reason": ""}


async def on_agent_changed(agent: str, actor: str) -> list[dict]:
    out = []
    for intake in intakes.for_agent(agent):
        result = await release(intake["id"], actor)
        if result["released"]:
            out.append({"intake": intake["id"], **result})
    return out


def cancel_journey_of(event: dict, actor: str) -> bool:
    journey_id = event.get("journeyId")
    if not journey_id or not is_configured():
        return False
    from pw_channel.orchestrator import store

    with connection() as conn:
        count = store.stop_journey(conn, journey_id, "stopped", f"cancelled by {actor}", datetime.now(timezone.utc))
    return count > 0
