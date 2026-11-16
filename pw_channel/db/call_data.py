import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pw_channel.db.core import connection, is_configured

logger = logging.getLogger(__name__)

MAX_LIMIT = 200


class UnknownTable(ValueError):
    pass


TABLES: dict[str, dict[str, Any]] = {
    "call_sessions": {
        "label": "Sessions",
        "blurb": "One row per call, from the first ring to how it ended.",
        "columns": (
            "id", "ref_id", "channel", "direction", "customer_number", "customer_name",
            "booking_reference_id", "did", "agent_number", "status", "ended_reason",
            "duration_secs", "recording_url", "call_record_id", "started_at",
            "answered_at", "transferred_at", "ended_at", "updated_at",
        ),
        "primary": ("id", "ref_id", "customer_number", "status", "duration_secs", "started_at"),
        "order_by": "started_at",
        "time_column": "started_at",
        "search": (
            "ref_id", "current_call_id", "original_call_id", "customer_number",
            "customer_name", "booking_reference_id", "did", "status",
        ),
        "note": "Deleting a session takes its events and its transcript with it.",
    },
    "call_records": {
        "label": "Dial attempts",
        "blurb": "Every call the dashboard or a journey asked for, placed or not.",
        "columns": (
            "id", "channel", "phone_no", "reference_id", "customer_name", "status",
            "triggered_by", "provider_call_id", "error", "created_at", "ended_at",
            "duration_secs", "transcript_turns", "ended_reason",
        ),
        "primary": ("id", "reference_id", "phone_no", "status", "triggered_by", "created_at"),
        "order_by": "created_at",
        "time_column": "created_at",
        "search": (
            "phone_no", "reference_id", "customer_name", "status", "triggered_by",
            "provider_call_id", "error",
        ),
        "note": "Sessions that point at a deleted attempt keep running; the link is cleared.",
    },
    "ingestion_events": {
        "label": "Ingestion",
        "blurb": "Every customer record the ingestion API received, and what became of its call.",
        "columns": (
            "id", "received_at", "source_ip", "reference_id", "phone_no", "customer_name",
            "status", "reason", "channel", "scheduled_for", "triggered_at", "call_record_id",
            "provider_call_id", "updated_at",
        ),
        "primary": ("id", "reference_id", "phone_no", "status", "received_at"),
        "order_by": "received_at",
        "time_column": "received_at",
        "search": ("reference_id", "phone_no", "customer_name", "status", "reason"),
        "note": "Deleting a scheduled record does not stop its call — cancel it on the Ingestion screen.",
    },
    "call_events": {
        "label": "Provider events",
        "blurb": "Raw webhooks the telephony provider sent about a call.",
        "columns": (
            "id", "session_id", "event_key", "kind", "ref_id", "call_id", "call_uuid",
            "received_at",
        ),
        "primary": ("id", "session_id", "kind", "ref_id", "received_at"),
        "order_by": "received_at",
        "time_column": "received_at",
        "search": ("event_key", "kind", "ref_id", "call_id", "call_uuid", "payload"),
        "note": "",
    },
    "call_transcripts": {
        "label": "Transcripts",
        "blurb": "What was said, one conversation per session.",
        "columns": (
            "id", "session_id", "call_record_id", "turns", "started_at", "updated_at",
        ),
        "primary": ("id", "session_id", "turns", "started_at", "updated_at"),
        "order_by": "updated_at",
        "time_column": "updated_at",
        "search": ("messages",),
        "note": "",
    },
    "call_transcripts_legacy": {
        "label": "Old transcripts",
        "blurb": "The pre-migration transcript table, one row per line said.",
        "columns": ("id", "session_id", "turn", "role", "text", "spoken", "created_at"),
        "primary": ("id", "session_id", "turn", "role", "text", "created_at"),
        "order_by": "created_at",
        "time_column": "created_at",
        "search": ("role", "text"),
        "note": "Nothing writes here any more — it is kept only for what predates the migration.",
    },
}

PURGE_ORDER = (
    "ingestion_events",
    "call_events",
    "call_transcripts",
    "call_transcripts_legacy",
    "call_sessions",
    "call_records",
)


def spec(table: str) -> dict[str, Any]:
    found = TABLES.get(table)
    if found is None:
        raise UnknownTable(f"{table!r} is not one of the voice tables")
    return found


def _clean(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).decode("utf-8", "replace")
    return value


def _row_view(row: dict) -> dict[str, Any]:
    return {key: _clean(value) for key, value in row.items()}


def _exists(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS oid", (table,)).fetchone()["oid"] is not None


def overview() -> list[dict[str, Any]]:
    if not is_configured():
        return []

    out = []
    with connection() as conn:
        for name, meta in TABLES.items():
            entry = {
                "table": name,
                "label": meta["label"],
                "blurb": meta["blurb"],
                "note": meta["note"],
                "remote": False,
                "columns": list(meta["columns"]),
                "primary": list(meta["primary"]),
                "exists": _exists(conn, name),
                "rows": 0,
                "newest": None,
                "bytes": 0,
            }
            if entry["exists"]:
                row = conn.execute(
                    f"""
                    SELECT count(*) AS n,
                           max({meta['time_column']}) AS newest,
                           pg_total_relation_size('{name}') AS bytes
                    FROM {name}
                    """
                ).fetchone()
                entry.update(
                    rows=row["n"], newest=_clean(row["newest"]), bytes=row["bytes"]
                )
            out.append(entry)
    return out


def _search_clause(table: str, term: str) -> tuple[str, list[Any]]:
    meta = spec(table)
    term = (term or "").strip()
    if not term:
        return "TRUE", []

    clauses = [f"{column}::text ILIKE %s" for column in meta["search"]]
    params: list[Any] = [f"%{term}%"] * len(meta["search"])
    if term.isdigit():
        clauses.append("id = %s")
        params.append(int(term))
        if "session_id" in meta["columns"]:
            clauses.append("session_id = %s")
            params.append(int(term))
    if not clauses:
        return "FALSE", []
    return "(" + " OR ".join(clauses) + ")", params


def read(table: str, *, limit: int = 50, offset: int = 0, term: str = "") -> dict[str, Any]:
    meta = spec(table)
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    where, params = _search_clause(table, term)
    columns = ", ".join(meta["columns"])

    with connection() as conn:
        if not _exists(conn, table):
            return {
                "table": table,
                "columns": list(meta["columns"]),
                "primary": list(meta["primary"]),
                "rows": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "missing": True,
            }
        total = conn.execute(
            f"SELECT count(*) AS n FROM {table} WHERE {where}", tuple(params)
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT {columns} FROM {table}
            WHERE {where}
            ORDER BY {meta['order_by']} DESC NULLS LAST, id DESC
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        ).fetchall()

    return {
        "table": table,
        "columns": list(meta["columns"]),
        "primary": list(meta["primary"]),
        "rows": [_row_view(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "missing": False,
    }


def row(table: str, row_id: int) -> dict[str, Any] | None:
    spec(table)
    with connection() as conn:
        found = conn.execute(f"SELECT * FROM {table} WHERE id = %s", (row_id,)).fetchone()
    return _row_view(found) if found else None


def children(session_id: int) -> dict[str, int]:
    with connection() as conn:
        events = conn.execute(
            "SELECT count(*) AS n FROM call_events WHERE session_id = %s", (session_id,)
        ).fetchone()["n"]
        transcripts = conn.execute(
            "SELECT count(*) AS n FROM call_transcripts WHERE session_id = %s", (session_id,)
        ).fetchone()["n"]
    return {"call_events": events, "call_transcripts": transcripts}


def delete_row(table: str, row_id: int) -> dict[str, Any]:
    spec(table)
    cascaded = children(row_id) if table == "call_sessions" else {}
    with connection() as conn:
        deleted = conn.execute(f"DELETE FROM {table} WHERE id = %s", (row_id,)).rowcount
    return {"deleted": deleted, "cascaded": {k: v for k, v in cascaded.items() if v}}


def purge(table: str, *, older_than_days: int = 0) -> int:
    meta = spec(table)
    where, params = "TRUE", ()
    if older_than_days > 0:
        where = f"{meta['time_column']} < now() - %s * interval '1 day'"
        params = (older_than_days,)
    with connection() as conn:
        if not _exists(conn, table):
            return 0
        return conn.execute(f"DELETE FROM {table} WHERE {where}", params).rowcount


def purge_all(*, older_than_days: int = 0) -> dict[str, int]:
    return {name: purge(name, older_than_days=older_than_days) for name in PURGE_ORDER}
