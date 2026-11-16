import json
import logging
from typing import Any

from pw_channel.db.core import DatabaseUnavailable, connection, is_configured
from pw_channel.channels.voice.states import call_lifecycle

logger = logging.getLogger(__name__)

_COLUMNS = """
    id, ref_id, original_call_id, current_call_id, original_uuid, current_uuid,
    leg_history, channel, direction, customer_number, customer_name,
    booking_reference_id, did, agent_number, status, status_rank, ended_reason,
    recording_url, duration_secs, call_record_id, started_at, answered_at,
    transferred_at, agent_answered_at, ended_at, updated_at, task_id
"""

_SETTABLE = (
    "task_id",
    "customer_number",
    "customer_name",
    "booking_reference_id",
    "direction",
    "did",
    "agent_number",
    "ended_reason",
    "recording_url",
    "duration_secs",
    "call_record_id",
)

_STAMP_FOR = {
    call_lifecycle.ACTIVE: "answered_at",
    call_lifecycle.TRANSFERRED: "transferred_at",
    call_lifecycle.ACTIVE_WITH_AGENT: "agent_answered_at",
    call_lifecycle.ENDED: "ended_at",
}


def view(row: dict) -> dict[str, Any]:
    return {
        "id": row["id"],
        "refId": row["ref_id"],
        "originalCallId": row["original_call_id"],
        "currentCallId": row["current_call_id"],
        "originalUuid": row["original_uuid"],
        "currentUuid": row["current_uuid"],
        "legHistory": row["leg_history"] or [],
        "channel": row["channel"],
        "direction": row["direction"],
        "customerNumber": row["customer_number"],
        "customerName": row["customer_name"],
        "bookingReferenceId": row["booking_reference_id"],
        "did": row["did"],
        "agentNumber": row["agent_number"],
        "status": row["status"],
        "endedReason": row["ended_reason"],
        "recordingUrl": row["recording_url"],
        "durationSecs": row["duration_secs"],
        "callRecordId": row["call_record_id"],
        "taskId": row.get("task_id"),
        "startedAt": row["started_at"].isoformat(),
        "answeredAt": row["answered_at"].isoformat() if row["answered_at"] else None,
        "transferredAt": row["transferred_at"].isoformat() if row["transferred_at"] else None,
        "agentAnsweredAt": (
            row["agent_answered_at"].isoformat() if row["agent_answered_at"] else None
        ),
        "endedAt": row["ended_at"].isoformat() if row["ended_at"] else None,
        "updatedAt": row["updated_at"].isoformat(),
    }


def begin(
    *,
    ref_id: str = "",
    call_id: str = "",
    call_uuid: str = "",
    status: str = call_lifecycle.INITIATED,
    channel: str = "acefone",
    **fields: Any,
) -> int | None:
    if not is_configured():
        return None

    columns = {
        "ref_id": ref_id,
        "original_call_id": call_id,
        "current_call_id": call_id,
        "original_uuid": call_uuid,
        "current_uuid": call_uuid,
        "channel": channel,
        "status": status,
        "status_rank": call_lifecycle.rank(status),
    }
    columns.update(
        {key: value for key, value in fields.items() if key in _SETTABLE and value not in (None, "")}
    )

    names = list(columns)
    values = ["%s"] * len(names)
    stamp = _STAMP_FOR.get(status)
    if stamp:
        names.append(stamp)
        values.append("now()")

    try:
        with connection() as conn:
            row = conn.execute(
                f"""
                INSERT INTO call_sessions ({", ".join(names)})
                VALUES ({", ".join(values)})
                RETURNING id
                """,
                tuple(columns.values()),
            ).fetchone()
        return row["id"]
    except Exception:
        logger.exception("[lifecycle] could not open a call session")
        return None


def find(*, ref_id: str = "", call_id: str = "", call_uuid: str = "") -> dict | None:
    if not is_configured():
        return None
    clauses = [
        ("ref_id = %s", ref_id),
        ("current_call_id = %s", call_id),
        ("original_call_id = %s", call_id),
        ("current_uuid = %s", call_uuid),
        ("original_uuid = %s", call_uuid),
    ]
    try:
        with connection() as conn:
            for clause, value in clauses:
                if not value:
                    continue
                row = conn.execute(
                    f"""
                    SELECT {_COLUMNS} FROM call_sessions
                    WHERE {clause}
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (value,),
                ).fetchone()
                if row:
                    return row
    except Exception:
        logger.exception("[lifecycle] could not look up a call session")
    return None


def mark(session_id: int, status: str, **fields: Any) -> bool:
    if not is_configured() or not session_id:
        return False
    extra = {key: value for key, value in fields.items() if key in _SETTABLE and value not in (None, "")}
    assignments = "".join(f", {key} = %s" for key in extra)
    stamp = _STAMP_FOR.get(status)
    stamped = f", {stamp} = COALESCE({stamp}, now())" if stamp else ""
    try:
        with connection() as conn:
            row = conn.execute(
                f"""
                UPDATE call_sessions
                SET status = %s,
                    status_rank = %s,
                    updated_at = now()
                    {stamped}
                    {assignments}
                WHERE id = %s AND status_rank < %s
                RETURNING id
                """,
                (
                    status,
                    call_lifecycle.rank(status),
                    *extra.values(),
                    session_id,
                    call_lifecycle.rank(status),
                ),
            ).fetchone()
        return row is not None
    except Exception:
        logger.exception("[lifecycle] could not move a call session forward")
        return False


def end_bot_leg(session_id: int, *, reason: str) -> bool:
    if not is_configured() or not session_id:
        return False
    try:
        with connection() as conn:
            row = conn.execute(
                """
                UPDATE call_sessions
                SET status = %s,
                    status_rank = %s,
                    ended_reason = %s,
                    ended_at = COALESCE(ended_at, now()),
                    updated_at = now()
                WHERE id = %s AND status_rank < %s
                RETURNING id
                """,
                (
                    call_lifecycle.ENDED,
                    call_lifecycle.rank(call_lifecycle.ENDED),
                    reason,
                    session_id,
                    call_lifecycle.HANDED_OVER_RANK,
                ),
            ).fetchone()
        return row is not None
    except Exception:
        logger.exception("[lifecycle] could not close the bot leg")
        return False


def update(session_id: int, **fields: Any) -> None:
    if not is_configured() or not session_id:
        return
    extra = {key: value for key, value in fields.items() if key in _SETTABLE and value not in (None, "")}
    if not extra:
        return
    assignments = ", ".join(f"{key} = %s" for key in extra)
    try:
        with connection() as conn:
            conn.execute(
                f"UPDATE call_sessions SET {assignments}, updated_at = now() WHERE id = %s",
                (*extra.values(), session_id),
            )
    except Exception:
        logger.exception("[lifecycle] could not update a call session")


def attach_leg(session_id: int, *, call_id: str = "", call_uuid: str = "") -> None:
    if not is_configured() or not session_id or not (call_id or call_uuid):
        return
    try:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT original_call_id, current_call_id, original_uuid, current_uuid,
                       leg_history
                FROM call_sessions WHERE id = %s
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return

            moved_call = bool(call_id) and call_id != row["current_call_id"]
            moved_uuid = bool(call_uuid) and call_uuid != row["current_uuid"]
            if not moved_call and not moved_uuid:
                return

            history = list(row["leg_history"] or [])
            history.append(
                {
                    "call_id": row["current_call_id"],
                    "uuid": row["current_uuid"],
                }
            )
            conn.execute(
                """
                UPDATE call_sessions
                SET current_call_id = CASE WHEN %s <> '' THEN %s ELSE current_call_id END,
                    current_uuid = CASE WHEN %s <> '' THEN %s ELSE current_uuid END,
                    original_call_id = CASE
                        WHEN original_call_id = '' THEN %s ELSE original_call_id END,
                    original_uuid = CASE
                        WHEN original_uuid = '' THEN %s ELSE original_uuid END,
                    leg_history = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    call_id, call_id,
                    call_uuid, call_uuid,
                    call_id,
                    call_uuid,
                    json.dumps(history),
                    session_id,
                ),
            )
    except Exception:
        logger.exception("[lifecycle] could not attach a call leg")


def _did_clause(did: str) -> tuple[str, str]:
    return (
        " AND ltrim(regexp_replace(did, '[^0-9]', '', 'g'), '0') = %s",
        "".join(ch for ch in did if ch.isdigit()).lstrip("0"),
    )


def active(*, did: str = "", limit: int = 100) -> list[dict[str, Any]]:
    where = "status_rank >= %s AND status_rank < %s"
    params: list[Any] = [
        call_lifecycle.rank(call_lifecycle.ACTIVE),
        call_lifecycle.rank(call_lifecycle.ENDED),
    ]
    if did:
        clause, value = _did_clause(did)
        where += clause
        params.append(value)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_COLUMNS} FROM call_sessions
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (*params, limit),
        ).fetchall()
    return [view(row) for row in rows]


def recently_ended(*, did: str = "", limit: int = 20) -> list[dict[str, Any]]:
    where = "status = %s"
    params: list[Any] = [call_lifecycle.ENDED]
    if did:
        clause, value = _did_clause(did)
        where += clause
        params.append(value)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_COLUMNS} FROM call_sessions
            WHERE {where}
            ORDER BY COALESCE(ended_at, updated_at) DESC
            LIMIT %s
            """,
            (*params, limit),
        ).fetchall()
    return [view(row) for row in rows]


def by_id(session_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM call_sessions WHERE id = %s", (session_id,)
        ).fetchone()
    return view(row) if row else None


def dids() -> list[str]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT did FROM call_sessions
            WHERE did <> ''
            ORDER BY did
            """
        ).fetchall()
    return [row["did"] for row in rows]


def live_ids() -> list[dict[str, Any]]:
    if not is_configured():
        return []
    try:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT id, ref_id, current_call_id, original_call_id, status, status_rank,
                       customer_number,
                       EXTRACT(EPOCH FROM (now() - started_at)) AS age_secs,
                       EXTRACT(EPOCH FROM (now() - COALESCE(transferred_at, started_at))) AS handed_secs
                FROM call_sessions
                WHERE status_rank >= %s AND status_rank < %s
                """,
                (
                    call_lifecycle.rank(call_lifecycle.ACTIVE),
                    call_lifecycle.rank(call_lifecycle.ENDED),
                ),
            ).fetchall()
        return [dict(row) for row in rows]
    except (DatabaseUnavailable, Exception):
        logger.exception("[lifecycle] could not read live call sessions")
        return []


def counts(*, did: str = "") -> dict[str, int]:
    where, params = "TRUE", []
    if did:
        clause, value = _did_clause(did)
        where += clause
        params.append(value)
    with connection() as conn:
        row = conn.execute(
            f"""
            SELECT
                count(*) FILTER (WHERE status = 'ACTIVE') AS with_bot,
                count(*) FILTER (WHERE status IN ('TRANSFER_INITIATED', 'TRANSFERRED'))
                    AS transferring,
                count(*) FILTER (WHERE status = 'ACTIVE_WITH_AGENT') AS with_agent,
                count(*) FILTER (WHERE status_rank >= 30 AND status_rank < 100) AS live
            FROM call_sessions
            WHERE {where}
            """,
            tuple(params),
        ).fetchone()
    return {
        "withBot": row["with_bot"],
        "transferring": row["transferring"],
        "withAgent": row["with_agent"],
        "live": row["live"],
    }


def by_call_record(record_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM call_sessions WHERE call_record_id = %s ORDER BY id DESC LIMIT 1", (record_id,)
        ).fetchone()
    return view(row) if row else None
