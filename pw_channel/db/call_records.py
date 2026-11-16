import json
import logging
from typing import Any

from pw_channel.db.core import DatabaseUnavailable, connection, is_configured

logger = logging.getLogger(__name__)


def record_request(
    *,
    channel: str,
    phone_no: str,
    reference_id: str = "",
    customer_name: str = "",
    status: str = "requested",
    triggered_by: str = "dashboard",
    provider_call_id: str = "",
    provider_response: dict | None = None,
    error: str | None = None,
    cart: dict | None = None,
) -> int | None:
    if not is_configured():
        return None
    try:
        with connection() as conn:
            row = conn.execute(
                """
                INSERT INTO call_records (
                    channel, phone_no, reference_id, customer_name, status,
                    triggered_by, provider_call_id, provider_response, error, cart
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    channel,
                    phone_no,
                    reference_id,
                    customer_name,
                    status,
                    triggered_by,
                    provider_call_id,
                    json.dumps(provider_response) if provider_response is not None else None,
                    error,
                    json.dumps(cart) if cart is not None else None,
                ),
            ).fetchone()
        return row["id"]
    except (DatabaseUnavailable, Exception):
        logger.exception("[calls] could not record the call attempt")
        return None


def record_disposition(
    *,
    reference_id: str,
    status: str,
    duration_secs: float | None = None,
    transcript_turns: int = 0,
    ended_reason: str | None = None,
) -> None:
    if not is_configured() or not reference_id:
        return
    try:
        with connection() as conn:
            conn.execute(
                """
                UPDATE call_records
                SET status = %s,
                    ended_at = now(),
                    duration_secs = %s,
                    transcript_turns = %s,
                    ended_reason = %s
                WHERE id = (
                    SELECT id FROM call_records
                    WHERE reference_id = %s AND ended_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                """,
                (status, duration_secs, transcript_turns, ended_reason, reference_id),
            )
    except Exception:
        logger.exception("[calls] could not record the disposition")


def recent(limit: int = 50, agents: list[str] | None = None) -> list[dict[str, Any]]:
    where, params = "", [limit]
    if agents is not None:
        where, params = "WHERE cart->>'use_case' = ANY(%s)", [agents, limit]
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, channel, phone_no, reference_id, customer_name, status,
                   triggered_by, provider_call_id, provider_response, error,
                   created_at, ended_at, duration_secs, transcript_turns, ended_reason
            FROM call_records
            {where}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return [
        {
            "id": row["id"],
            "channel": row["channel"],
            "phone": row["phone_no"],
            "referenceId": row["reference_id"],
            "name": row["customer_name"],
            "status": row["status"],
            "triggeredBy": row["triggered_by"],
            "providerCallId": row["provider_call_id"],
            "providerResponse": row["provider_response"],
            "error": row["error"],
            "createdAt": row["created_at"].isoformat(),
            "endedAt": row["ended_at"].isoformat() if row["ended_at"] else None,
            "durationSecs": row["duration_secs"],
            "transcriptTurns": row["transcript_turns"],
            "endedReason": row["ended_reason"],
        }
        for row in rows
    ]


def counts() -> dict[str, int]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT
                count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS last_24h,
                count(*) FILTER (WHERE error IS NOT NULL
                                 AND created_at > now() - interval '24 hours') AS failed_24h,
                count(*) AS total
            FROM call_records
            """
        ).fetchone()
    return {
        "last24h": row["last_24h"],
        "failed24h": row["failed_24h"],
        "total": row["total"],
    }


def record_metrics(*, metrics: dict, session_row_id: int | None = None, reference_id: str = "") -> None:
    if not is_configured() or not (session_row_id or reference_id):
        return
    try:
        with connection() as conn:
            record_id = None
            if session_row_id:
                found = conn.execute(
                    "SELECT call_record_id FROM call_sessions WHERE id = %s", (session_row_id,)
                ).fetchone()
                record_id = found and found["call_record_id"]
            if not record_id and reference_id:
                found = conn.execute(
                    "SELECT id FROM call_records WHERE reference_id = %s ORDER BY created_at DESC LIMIT 1",
                    (reference_id,),
                ).fetchone()
                record_id = found and found["id"]
            if record_id:
                conn.execute(
                    "UPDATE call_records SET metrics = %s WHERE id = %s",
                    (json.dumps(metrics, default=str), record_id),
                )
    except Exception:
        logger.exception("[calls] could not record the call metrics")


def get(record_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM call_records WHERE id = %s", (record_id,)).fetchone()
    if not row:
        return None
    iso = lambda v: v.isoformat() if v else None
    return {
        "id": row["id"],
        "channel": row["channel"],
        "phone": row["phone_no"],
        "referenceId": row["reference_id"],
        "customerName": row["customer_name"],
        "status": row["status"],
        "triggeredBy": row["triggered_by"],
        "providerCallId": row["provider_call_id"],
        "error": row["error"],
        "createdAt": iso(row["created_at"]),
        "endedAt": iso(row["ended_at"]),
        "durationSecs": row["duration_secs"],
        "transcriptTurns": row["transcript_turns"],
        "endedReason": row["ended_reason"],
        "metrics": row.get("metrics"),
        "summary": row.get("summary"),
        "summaryAt": iso(row.get("summary_at")),
    }


def set_summary(record_id: int, summary: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE call_records SET summary = %s, summary_at = now() WHERE id = %s", (summary, record_id)
        )

