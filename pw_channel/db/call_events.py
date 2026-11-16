import json
import logging

from pw_channel.db.core import connection, is_configured

logger = logging.getLogger(__name__)


def record_once(
    *,
    event_key: str,
    kind: str,
    ref_id: str = "",
    call_id: str = "",
    call_uuid: str = "",
    session_id: int | None = None,
    payload: dict | None = None,
) -> int | None:
    if not is_configured() or not event_key:
        return None
    try:
        with connection() as conn:
            row = conn.execute(
                """
                INSERT INTO call_events (
                    session_id, event_key, kind, ref_id, call_id, call_uuid, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_key) DO NOTHING
                RETURNING id
                """,
                (
                    session_id,
                    event_key,
                    kind,
                    ref_id,
                    call_id,
                    call_uuid,
                    json.dumps(payload) if payload is not None else None,
                ),
            ).fetchone()
        return row["id"] if row else None
    except Exception:
        logger.exception("[lifecycle] could not record a provider event")
        return None


def link(event_id: int, session_id: int) -> None:
    if not is_configured() or not event_id or not session_id:
        return
    try:
        with connection() as conn:
            conn.execute(
                "UPDATE call_events SET session_id = %s WHERE id = %s",
                (session_id, event_id),
            )
    except Exception:
        logger.exception("[lifecycle] could not link a provider event")


def for_session(session_id: int, limit: int = 50) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, kind, ref_id, call_id, call_uuid, payload, received_at
            FROM call_events
            WHERE session_id = %s
            ORDER BY received_at
            LIMIT %s
            """,
            (session_id, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "kind": row["kind"],
            "refId": row["ref_id"],
            "callId": row["call_id"],
            "uuid": row["call_uuid"],
            "payload": row["payload"],
            "receivedAt": row["received_at"].isoformat(),
        }
        for row in rows
    ]
