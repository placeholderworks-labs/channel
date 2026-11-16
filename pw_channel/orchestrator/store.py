import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pw_sdk.contracts.outcomes import TaskOutcome
from pw_channel.db.core import connection

logger = logging.getLogger(__name__)

TERMINAL = ("done", "skipped", "cancelled")
OPEN = ("blocked", "ready", "running", "waiting")


@dataclass
class TaskRow:
    id: int
    journey_id: int
    key: str
    channel: str
    action: str
    params: dict
    status: str
    outcome: str | None
    attempts: int
    max_attempts: int
    retry_delay_secs: float
    response_window_secs: float
    provider_ref: str | None
    reference_id: str
    lead_key: str
    intake: str
    template: str

    @classmethod
    def of(cls, row: dict) -> "TaskRow":
        return cls(**{name: row.get(name) for name in cls.__dataclass_fields__})


TASK_SELECT = """
    SELECT t.*, j.reference_id, j.lead_key, j.intake, j.template
      FROM journey_tasks t JOIN journeys j ON j.id = t.journey_id
"""


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def active_journey(conn, lead_key: str, template: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM journeys WHERE lead_key = %s AND template = %s AND status IN ('active', 'paused') FOR UPDATE",
        (lead_key, template),
    ).fetchone()


def insert_journey(conn, *, lead_key: str, reference_id: str, intake: str, template: str, steps, now: datetime,
                   expires_at: datetime | None) -> tuple[int, datetime | None]:
    journey_id = conn.execute(
        """
        INSERT INTO journeys (lead_key, reference_id, intake, template, expires_at)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        """,
        (lead_key, reference_id, intake, template, expires_at),
    ).fetchone()["id"]
    ids: dict[str, int] = {}
    first_run: datetime | None = None
    for step in steps:
        ready = not step.depends_on
        run_at = now + timedelta(seconds=step.delay_secs) if ready else None
        if ready and (first_run is None or run_at < first_run):
            first_run = run_at
        ids[step.key] = conn.execute(
            """
            INSERT INTO journey_tasks (journey_id, key, channel, action, params, join_mode, delay_secs,
                                       response_window_secs, status, run_at, max_attempts, retry_delay_secs)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (journey_id, step.key, step.channel, step.action, _json(step.params), step.join, step.delay_secs,
             step.response_window_secs, "ready" if ready else "blocked", run_at, step.max_attempts, step.retry_delay_secs),
        ).fetchone()["id"]
    for step in steps:
        for parent in step.depends_on:
            conn.execute(
                "INSERT INTO task_deps (task_id, depends_on_task_id, when_outcomes) VALUES (%s, %s, %s)",
                (ids[step.key], ids[parent], sorted(outcome.value for outcome in step.when)),
            )
    return journey_id, first_run


def claim_ready(worker: str, limit: int, lease_secs: float, now: datetime) -> list[TaskRow]:
    with connection() as conn:
        rows = conn.execute(
            f"""
            WITH due AS (
                SELECT t.id FROM journey_tasks t JOIN journeys j ON j.id = t.journey_id
                 WHERE t.status = 'ready' AND t.run_at <= %(now)s
                   AND j.status = 'active' AND (j.paused_until IS NULL OR j.paused_until <= %(now)s)
                 ORDER BY t.run_at
                 LIMIT %(limit)s
                 FOR UPDATE OF t SKIP LOCKED
            )
            UPDATE journey_tasks t
               SET status = 'running', locked_by = %(worker)s, lease_until = %(lease)s,
                   attempts = t.attempts + 1, updated_at = %(now)s
              FROM due WHERE t.id = due.id
            RETURNING t.id
            """,
            {"now": now, "limit": limit, "worker": worker, "lease": now + timedelta(seconds=lease_secs)},
        ).fetchall()
        if not rows:
            return []
        found = conn.execute(TASK_SELECT + " WHERE t.id = ANY(%s) ORDER BY t.run_at", ([r["id"] for r in rows],)).fetchall()
    return [TaskRow.of(row) for row in found]


def task(task_id: int) -> TaskRow | None:
    with connection() as conn:
        row = conn.execute(TASK_SELECT + " WHERE t.id = %s", (task_id,)).fetchone()
    return TaskRow.of(row) if row else None


def defer(task_id: int, run_at: datetime, reason: str, now: datetime, refund_attempt: bool = True) -> None:
    with connection() as conn:
        conn.execute(
            f"""
            UPDATE journey_tasks
               SET status = 'ready', run_at = %s, locked_by = NULL, lease_until = NULL,
                   attempts = GREATEST(attempts - {1 if refund_attempt else 0}, 0),
                   result = result || %s::jsonb, updated_at = %s
             WHERE id = %s AND status = 'running'
            """,
            (run_at, _json({"deferred": reason}), now, task_id),
        )


def wait(task_id: int, *, provider_ref: str | None, window_ends_at: datetime, outcome: TaskOutcome | None,
         on_timeout: TaskOutcome, detail: dict, now: datetime) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE journey_tasks
               SET status = 'waiting', provider_ref = COALESCE(%s, provider_ref), window_ends_at = %s,
                   outcome = %s, locked_by = NULL, lease_until = NULL,
                   result = result || %s::jsonb, updated_at = %s
             WHERE id = %s AND status IN ('running', 'waiting')
            """,
            (provider_ref, window_ends_at, outcome.value if outcome else None,
             _json({**detail, "on_timeout": on_timeout.value}), now, task_id),
        )


def finish(task_id: int, outcome: TaskOutcome, *, now: datetime, provider_ref: str | None = None,
           detail: dict | None = None, retry: bool = False) -> str:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM journey_tasks WHERE id = %s FOR UPDATE", (task_id,)
        ).fetchone()
        if row is None or row["status"] in TERMINAL:
            return "ignored"
        if retry and row["attempts"] < row["max_attempts"]:
            conn.execute(
                """
                UPDATE journey_tasks
                   SET status = 'ready', run_at = %s, outcome = %s, locked_by = NULL, lease_until = NULL,
                       window_ends_at = NULL, provider_ref = COALESCE(%s, provider_ref),
                       result = result || %s::jsonb, updated_at = %s
                 WHERE id = %s
                """,
                (now + timedelta(seconds=row["retry_delay_secs"]), outcome.value, provider_ref,
                 _json({**(detail or {}), "retrying_after": outcome.value}), now, task_id),
            )
            return "retrying"
        conn.execute(
            """
            UPDATE journey_tasks
               SET status = 'done', outcome = %s, locked_by = NULL, lease_until = NULL, window_ends_at = NULL,
                   provider_ref = COALESCE(%s, provider_ref), result = result || %s::jsonb, updated_at = %s
             WHERE id = %s
            """,
            (outcome.value, provider_ref, _json(detail or {}), now, task_id),
        )
        resolve_dependents(conn, task_id, now)
        close_if_finished(conn, row["journey_id"], now)
    return "done"


def resolve_dependents(conn, parent_id: int, now: datetime) -> None:
    pending = [parent_id]
    while pending:
        current = pending.pop()
        children = conn.execute(
            """
            SELECT c.* FROM task_deps d JOIN journey_tasks c ON c.id = d.task_id
             WHERE d.depends_on_task_id = %s AND c.status = 'blocked' FOR UPDATE OF c
            """,
            (current,),
        ).fetchall()
        for child in children:
            deps = conn.execute(
                """
                SELECT p.status, p.outcome, d.when_outcomes FROM task_deps d
                  JOIN journey_tasks p ON p.id = d.depends_on_task_id WHERE d.task_id = %s
                """,
                (child["id"],),
            ).fetchall()
            decision = decide(child["join_mode"], deps)
            if decision == "ready":
                conn.execute(
                    "UPDATE journey_tasks SET status = 'ready', run_at = %s, updated_at = %s WHERE id = %s",
                    (now + timedelta(seconds=child["delay_secs"]), now, child["id"]),
                )
            elif decision == "skip":
                conn.execute(
                    "UPDATE journey_tasks SET status = 'skipped', outcome = 'skipped', updated_at = %s WHERE id = %s",
                    (now, child["id"]),
                )
                pending.append(child["id"])


def decide(join_mode: str, deps: list[dict]) -> str:
    def matched(dep: dict) -> bool:
        if dep["status"] not in TERMINAL:
            return False
        outcome = dep["outcome"] if dep["status"] == "done" else "skipped"
        return outcome in dep["when_outcomes"]

    finished = [dep for dep in deps if dep["status"] in TERMINAL]
    if join_mode == "any":
        if any(matched(dep) for dep in deps):
            return "ready"
        return "skip" if len(finished) == len(deps) else "wait"
    if len(finished) < len(deps):
        return "wait"
    return "ready" if all(matched(dep) for dep in deps) else "skip"


def close_if_finished(conn, journey_id: int, now: datetime) -> None:
    left = conn.execute(
        "SELECT count(*) AS n FROM journey_tasks WHERE journey_id = %s AND status = ANY(%s)", (journey_id, list(OPEN))
    ).fetchone()["n"]
    if not left:
        conn.execute(
            "UPDATE journeys SET status = 'completed', updated_at = %s WHERE id = %s AND status IN ('active', 'paused')",
            (now, journey_id),
        )


def stop_journey(conn, journey_id: int, status: str, reason: str, now: datetime) -> int:
    cancelled = conn.execute(
        """
        UPDATE journey_tasks SET status = 'cancelled', outcome = COALESCE(outcome, 'skipped'),
               locked_by = NULL, lease_until = NULL, updated_at = %s
         WHERE journey_id = %s AND status = ANY(%s)
        """,
        (now, journey_id, ["blocked", "ready", "waiting"]),
    ).rowcount
    conn.execute(
        "UPDATE journeys SET status = %s, stop_reason = %s, updated_at = %s WHERE id = %s AND status IN ('active', 'paused')",
        (status, reason[:300], now, journey_id),
    )
    return cancelled or 0


def cancel_task(conn, journey_id: int, key: str, reason: str, now: datetime) -> bool:
    row = conn.execute(
        """
        UPDATE journey_tasks SET status = 'cancelled', outcome = 'skipped', result = result || %s::jsonb, updated_at = %s
         WHERE journey_id = %s AND key = %s AND status = ANY(%s) RETURNING id
        """,
        (_json({"cancelled": reason}), now, journey_id, key, ["blocked", "ready", "waiting"]),
    ).fetchone()
    if row:
        resolve_dependents(conn, row["id"], now)
        close_if_finished(conn, journey_id, now)
    return bool(row)


def reschedule_task(conn, journey_id: int, key: str, run_at: datetime, now: datetime) -> bool:
    row = conn.execute(
        """
        UPDATE journey_tasks SET status = 'ready', run_at = %s, outcome = NULL, window_ends_at = NULL,
               locked_by = NULL, lease_until = NULL, attempts = 0, updated_at = %s
         WHERE journey_id = %s AND key = %s AND status <> 'running' RETURNING id
        """,
        (run_at, now, journey_id, key),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE journeys SET status = 'active', stop_reason = '', updated_at = %s WHERE id = %s AND status = 'completed'",
            (now, journey_id),
        )
    return bool(row)


def pause_journey(conn, journey_id: int, until: datetime, now: datetime) -> None:
    conn.execute(
        "UPDATE journeys SET paused_until = GREATEST(COALESCE(paused_until, %s), %s), updated_at = %s WHERE id = %s",
        (until, until, now, journey_id),
    )


def requeue_expired_leases(now: datetime) -> int:
    with connection() as conn:
        return conn.execute(
            """
            UPDATE journey_tasks SET status = 'ready', locked_by = NULL, lease_until = NULL,
                   run_at = %s, updated_at = %s
             WHERE status = 'running' AND lease_until < %s
            """,
            (now, now, now),
        ).rowcount or 0


def expired_windows(now: datetime, limit: int = 100) -> list[dict]:
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, result->>'on_timeout' AS on_timeout FROM journey_tasks
             WHERE status = 'waiting' AND window_ends_at <= %s ORDER BY window_ends_at LIMIT %s
            """,
            (now, limit),
        ).fetchall()


def expire_journeys(now: datetime) -> int:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id FROM journeys WHERE status IN ('active', 'paused') AND expires_at <= %s FOR UPDATE SKIP LOCKED",
            (now,),
        ).fetchall()
        for row in rows:
            stop_journey(conn, row["id"], "expired", "journey expired", now)
    return len(rows)


def waiting_task_for(conn, lead_key: str, channel: str | None) -> dict | None:
    clause = "AND t.channel = %s" if channel else ""
    params = [lead_key] + ([channel] if channel else [])
    return conn.execute(
        f"""
        SELECT t.* FROM journey_tasks t JOIN journeys j ON j.id = t.journey_id
         WHERE j.lead_key = %s AND j.status IN ('active', 'paused') AND t.status = 'waiting' {clause}
         ORDER BY t.updated_at DESC LIMIT 1 FOR UPDATE OF t
        """,
        params,
    ).fetchone()


def task_by_provider_ref(provider_ref: str) -> TaskRow | None:
    with connection() as conn:
        row = conn.execute(TASK_SELECT + " WHERE t.provider_ref = %s ORDER BY t.id DESC LIMIT 1", (provider_ref,)).fetchone()
    return TaskRow.of(row) if row else None


def contacts_today(lead_key: str, since: datetime) -> int:
    with connection() as conn:
        return conn.execute(
            """
            SELECT count(*) AS n FROM journey_tasks t JOIN journeys j ON j.id = t.journey_id
             WHERE j.lead_key = %s AND t.status IN ('done', 'waiting') AND t.outcome IS DISTINCT FROM 'skipped'
               AND t.updated_at >= %s
            """,
            (lead_key, since),
        ).fetchone()["n"]


def blocked_channels(lead_key: str) -> set[str]:
    with connection() as conn:
        rows = conn.execute("SELECT channel FROM contact_blocks WHERE lead_key = %s", (lead_key,)).fetchall()
    return {row["channel"] for row in rows}


def block_channel(conn, lead_key: str, channel: str, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO contact_blocks (lead_key, channel, reason) VALUES (%s, %s, %s)
        ON CONFLICT (lead_key, channel) DO UPDATE SET reason = EXCLUDED.reason
        """,
        (lead_key, channel, reason),
    )


def insert_event(*, kind: str, lead_key: str = "", reference_id: str = "", journey_id: int | None = None,
                 source: str = "", payload: dict | None = None, dedupe_key: str | None = None) -> int | None:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO journey_events (journey_id, lead_key, reference_id, kind, source, payload, dedupe_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dedupe_key) DO NOTHING RETURNING id
            """,
            (journey_id, lead_key, reference_id, kind, source, _json(payload or {}), dedupe_key),
        ).fetchone()
    return row["id"] if row else None


def claim_events(conn, limit: int) -> list[dict]:
    return conn.execute(
        """
        SELECT * FROM journey_events WHERE processed_at IS NULL
         ORDER BY received_at LIMIT %s FOR UPDATE SKIP LOCKED
        """,
        (limit,),
    ).fetchall()


def journeys_for_event(conn, event: dict) -> list[dict]:
    if event.get("journey_id"):
        return conn.execute("SELECT * FROM journeys WHERE id = %s FOR UPDATE", (event["journey_id"],)).fetchall()
    if event.get("reference_id"):
        rows = conn.execute(
            """
            SELECT j.* FROM journeys j
             WHERE j.status IN ('active', 'paused')
               AND (j.reference_id = %s OR j.lead_key = (SELECT lead_key FROM records WHERE reference_id = %s))
             FOR UPDATE
            """,
            (event["reference_id"], event["reference_id"]),
        ).fetchall()
        if rows:
            return rows
    if event.get("lead_key"):
        return conn.execute(
            "SELECT * FROM journeys WHERE lead_key = %s AND status IN ('active', 'paused') FOR UPDATE",
            (event["lead_key"],),
        ).fetchall()
    return []


def mark_event(conn, event_id: int, result: str, now: datetime) -> None:
    conn.execute("UPDATE journey_events SET processed_at = %s, result = %s WHERE id = %s", (now, result[:300], event_id))


def journey_view(journey_id: int) -> dict | None:
    with connection() as conn:
        journey = conn.execute("SELECT * FROM journeys WHERE id = %s", (journey_id,)).fetchone()
        if journey is None:
            return None
        tasks = conn.execute("SELECT * FROM journey_tasks WHERE journey_id = %s ORDER BY id", (journey_id,)).fetchall()
        events = conn.execute(
            "SELECT * FROM journey_events WHERE journey_id = %s OR (journey_id IS NULL AND reference_id = %s) ORDER BY id",
            (journey_id, journey["reference_id"]),
        ).fetchall()
    return {"journey": journey, "tasks": tasks, "events": events}


def recent_journeys(limit: int = 50, status: str = "") -> list[dict]:
    with connection() as conn:
        if status:
            return conn.execute("SELECT * FROM journeys WHERE status = %s ORDER BY id DESC LIMIT %s", (status, limit)).fetchall()
        return conn.execute("SELECT * FROM journeys ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
