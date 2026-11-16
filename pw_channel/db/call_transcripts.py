import json
import logging
from datetime import datetime, timezone
from typing import Any

from pw_channel.db.core import connection, is_configured

logger = logging.getLogger(__name__)

MAX_TEXT = 4000
MAX_MESSAGES = 400


def append_turn(
    *,
    session_id: int,
    turn: int,
    lines: list[tuple[str, str, bool]],
    call_record_id: int | None = None,
) -> None:
    if not is_configured() or not session_id:
        return

    at = datetime.now(timezone.utc).isoformat()
    messages = [
        {"turn": turn, "role": role, "text": text[:MAX_TEXT], "spoken": spoken, "at": at}
        for role, text, spoken in lines
        if text
    ]
    if not messages:
        return

    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO call_transcripts
                    (session_id, call_record_id, messages, turns, updated_at)
                VALUES (
                    %s,
                    COALESCE(
                        %s, (SELECT call_record_id FROM call_sessions WHERE id = %s)
                    ),
                    %s::jsonb,
                    %s,
                    now()
                )
                ON CONFLICT (session_id) DO UPDATE
                    SET messages = CASE
                            WHEN jsonb_array_length(call_transcripts.messages) >= %s
                            THEN call_transcripts.messages
                            ELSE call_transcripts.messages || EXCLUDED.messages
                        END,
                        turns = GREATEST(call_transcripts.turns, EXCLUDED.turns),
                        call_record_id = COALESCE(
                            call_transcripts.call_record_id, EXCLUDED.call_record_id
                        ),
                        updated_at = now()
                """,
                (
                    session_id,
                    call_record_id,
                    session_id,
                    json.dumps(messages, ensure_ascii=False),
                    turn,
                    MAX_MESSAGES,
                ),
            )
    except Exception:
        logger.exception("[lifecycle] could not record a transcript turn")


def for_session(session_id: int, limit: int = 200) -> list[dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(
            "SELECT messages, updated_at FROM call_transcripts WHERE session_id = %s",
            (session_id,),
        ).fetchone()

    if not row:
        return []

    messages = row["messages"] or []
    return [
        {
            "id": index + 1,
            "turn": message.get("turn"),
            "role": message.get("role", ""),
            "text": message.get("text", ""),
            "spoken": message.get("spoken", True),
            "at": message.get("at", ""),
        }
        for index, message in enumerate(messages[:limit])
    ]


def chat_for_session(session_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT session_id, call_record_id, messages, turns, started_at, updated_at
            FROM call_transcripts
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "sessionId": row["session_id"],
        "callRecordId": row["call_record_id"],
        "turns": row["turns"],
        "messages": row["messages"] or [],
        "startedAt": row["started_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
    }
