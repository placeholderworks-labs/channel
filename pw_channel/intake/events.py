import json
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any

from pw_channel.db.core import connection, is_configured

logger = logging.getLogger(__name__)

AWAITING = "awaiting_agent"
STATUSES = ("rejected", "duplicate", AWAITING, "scheduled", "dialing", "triggered", "failed", "cancelled", "skipped")
ACTIVE_STATUSES = ("scheduled", "dialing", "triggered")
_DUPLICATE_OF = (*ACTIVE_STATUSES, AWAITING)

_COLUMNS = (
    "source_ip", "reference_id", "phone_no", "customer_name", "status", "reason",
    "errors", "payload", "channel", "scheduled_for", "triggered_at", "call_record_id",
    "provider_call_id", "agent", "source", "intake", "canonical", "adapter", "adapter_version",
    "schema_version", "journey_id",
)
_JSON_COLUMNS = ("errors", "payload", "canonical")
_MEMORY_LIMIT = 1000

_memory: "OrderedDict[int, dict]" = OrderedDict()
_memory_lock = threading.Lock()
_memory_next_id = -1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _memory_create(fields: dict) -> int:
    global _memory_next_id
    with _memory_lock:
        event_id = _memory_next_id
        _memory_next_id -= 1
        now = _now()
        _memory[event_id] = {
            "id": event_id, "received_at": now, "updated_at": now,
            **{c: None for c in _COLUMNS}, **fields,
        }
        while len(_memory) > _MEMORY_LIMIT:
            _memory.popitem(last=False)
    return event_id


def create(**fields: Any) -> int:
    fields = {k: v for k, v in fields.items() if k in _COLUMNS}
    fields.setdefault("errors", [])
    if not is_configured():
        return _memory_create(fields)

    names = list(fields)
    values = [json.dumps(fields[n], default=str) if n in _JSON_COLUMNS else fields[n] for n in names]
    try:
        with connection() as conn:
            row = conn.execute(
                f"INSERT INTO ingestion_events ({', '.join(names)}) "
                f"VALUES ({', '.join(['%s'] * len(names))}) RETURNING id",
                values,
            ).fetchone()
        return row["id"]
    except Exception:
        logger.exception("[ingestion] could not write the event to Postgres — keeping it in memory")
        return _memory_create(fields)


def update(event_id: int | None, **fields: Any) -> None:
    if not event_id:
        return
    fields = {k: v for k, v in fields.items() if k in _COLUMNS}
    if not fields:
        return

    if event_id < 0:
        with _memory_lock:
            row = _memory.get(event_id)
            if row is not None:
                row.update(fields, updated_at=_now())
        return

    assignments = ", ".join(f"{n} = %s" for n in fields)
    values = [json.dumps(v, default=str) if n in _JSON_COLUMNS else v for n, v in fields.items()]
    try:
        with connection() as conn:
            conn.execute(
                f"UPDATE ingestion_events SET {assignments}, updated_at = now() WHERE id = %s",
                [*values, event_id],
            )
    except Exception:
        logger.exception(f"[ingestion] could not update event {event_id}")


def _view(row: dict) -> dict:
    def iso(value):
        return value.isoformat() if isinstance(value, datetime) else value

    return {
        "id": row["id"],
        "receivedAt": iso(row["received_at"]),
        "updatedAt": iso(row["updated_at"]),
        "sourceIp": row["source_ip"] or "",
        "referenceId": row["reference_id"] or "",
        "phone": row["phone_no"] or "",
        "name": row["customer_name"] or "",
        "status": row["status"],
        "reason": row["reason"] or "",
        "errors": row["errors"] or [],
        "payload": row["payload"],
        "channel": row["channel"] or "",
        "scheduledFor": iso(row["scheduled_for"]),
        "triggeredAt": iso(row["triggered_at"]),
        "callRecordId": row["call_record_id"],
        "providerCallId": row["provider_call_id"] or "",
        "agent": row.get("agent") or "",
        "source": row.get("source") or "",
        "intake": row.get("intake") or "",
        "canonical": row.get("canonical"),
        "adapter": row.get("adapter") or "",
        "adapterVersion": row.get("adapter_version") or "",
        "schemaVersion": row.get("schema_version") or "",
        "journeyId": row.get("journey_id"),
        "persisted": row["id"] > 0,
    }


def _memory_rows() -> list[dict]:
    with _memory_lock:
        return [dict(r) for r in _memory.values()]


def _matches(row: dict, status: str, q: str, agent: str = "", source: str = "") -> bool:
    if status and row["status"] != status:
        return False
    if agent and (row.get("agent") or "") != agent:
        return False
    if source and (row.get("source") or "") != source:
        return False
    if q:
        hay = " ".join(str(row.get(k) or "") for k in ("reference_id", "phone_no", "customer_name", "reason"))
        return q.lower() in hay.lower()
    return True


def _filters(agent: str, source: str) -> tuple[list[str], list]:
    where, params = [], []
    if agent:
        where.append("agent = %s")
        params.append(agent)
    if source:
        where.append("source = %s")
        params.append(source)
    return where, params


def recent(limit: int = 100, status: str = "", q: str = "", agent: str = "", source: str = "") -> list[dict]:
    limit = max(1, min(limit, 500))
    rows = [r for r in _memory_rows() if _matches(r, status, q, agent, source)]

    if is_configured():
        where, params = _filters(agent, source)
        if status:
            where.append("status = %s")
            params.append(status)
        if q:
            where.append(
                "(reference_id ILIKE %s OR phone_no ILIKE %s OR customer_name ILIKE %s OR reason ILIKE %s)"
            )
            params.extend([f"%{q}%"] * 4)
        sql = "SELECT * FROM ingestion_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY received_at DESC LIMIT %s"
        with connection() as conn:
            rows.extend(conn.execute(sql, [*params, limit]).fetchall())

    rows.sort(key=lambda r: r["received_at"], reverse=True)
    return [_view(r) for r in rows[:limit]]


def get(event_id: int) -> dict | None:
    if event_id < 0:
        with _memory_lock:
            row = _memory.get(event_id)
        return _view(dict(row)) if row else None
    if not is_configured():
        return None
    with connection() as conn:
        row = conn.execute("SELECT * FROM ingestion_events WHERE id = %s", (event_id,)).fetchone()
    return _view(row) if row else None


def counts(agent: str = "", source: str = "") -> dict[str, int]:
    since = _now() - timedelta(hours=24)
    totals = {s: 0 for s in STATUSES}
    pending = 0
    last = None

    for row in _memory_rows():
        if not _matches(row, "", "", agent, source):
            continue
        if row["status"] == "scheduled":
            pending += 1
        last = max(last, row["received_at"]) if last else row["received_at"]
        if row["received_at"] >= since:
            totals[row["status"]] = totals.get(row["status"], 0) + 1

    if is_configured():
        where, params = _filters(agent, source)
        extra = "".join(f" AND {w}" for w in where)
        with connection() as conn:
            for row in conn.execute(
                "SELECT status, count(*) AS n FROM ingestion_events "
                f"WHERE received_at > now() - interval '24 hours'{extra} GROUP BY status",
                params,
            ).fetchall():
                totals[row["status"]] = totals.get(row["status"], 0) + row["n"]
            pending += conn.execute(
                f"SELECT count(*) AS n FROM ingestion_events WHERE status = 'scheduled'{extra}", params
            ).fetchone()["n"]
            newest = conn.execute(
                f"SELECT max(received_at) AS at FROM ingestion_events WHERE TRUE{extra}", params
            ).fetchone()["at"]
            if newest and (last is None or newest > last):
                last = newest

    return {**totals, "received": sum(totals.values()), "pending": pending,
            "lastAt": last.isoformat() if last else None}


def find_active_duplicate(
    reference_id: str, phone_no: str, window_secs: float, exclude: int | None = None, include_held: bool = True,
) -> dict | None:
    if window_secs <= 0:
        return None
    since = _now() - timedelta(seconds=window_secs)
    ref = (reference_id or "").strip().lower()
    statuses = _DUPLICATE_OF if include_held else ACTIVE_STATUSES

    for row in reversed(_memory_rows()):
        if (
            row["id"] != exclude
            and row["status"] in statuses
            and row["received_at"] >= since
            and ((ref and (row["reference_id"] or "").lower() == ref) or row["phone_no"] == phone_no)
        ):
            return _view(row)

    if not is_configured():
        return None
    with connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM ingestion_events
            WHERE status = ANY(%s)
              AND received_at > %s
              AND (lower(reference_id) = %s OR phone_no = %s)
              AND id <> %s
            ORDER BY received_at DESC
            LIMIT 1
            """,
            (list(statuses), since, ref, phone_no, exclude or 0),
        ).fetchone()
    return _view(row) if row else None


def awaiting_count(source: str) -> int:
    n = sum(1 for r in _memory_rows() if r["status"] == AWAITING and r.get("source") == source)
    if is_configured():
        with connection() as conn:
            n += conn.execute(
                "SELECT count(*) AS n FROM ingestion_events WHERE status = %s AND source = %s", (AWAITING, source)
            ).fetchone()["n"]
    return n


def agents_seen() -> list[str]:
    seen = {r.get("agent") or "" for r in _memory_rows()}
    if is_configured():
        with connection() as conn:
            seen |= {r["agent"] for r in conn.execute("SELECT DISTINCT agent FROM ingestion_events").fetchall()}
    return sorted(a for a in seen if a)
