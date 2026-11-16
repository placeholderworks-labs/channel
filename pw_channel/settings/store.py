from __future__ import annotations

import logging
import os

from pw_channel.db.core import DatabaseUnavailable, connection, is_configured
from pw_channel.settings.registry import SETTINGS, all_keys

logger = logging.getLogger(__name__)

SECRET_PLACEHOLDER = "••••••••"


class SettingsStoreError(RuntimeError):
    pass


def read_all() -> dict[str, str]:
    with connection() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def read_meta() -> dict[str, dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at, updated_by FROM app_settings"
        ).fetchall()
    return {
        row["key"]: {
            "value": row["value"],
            "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
            "updatedBy": row["updated_by"],
        }
        for row in rows
    }


def load_overlay() -> dict[str, str]:
    if not is_configured():
        return {}
    try:
        stored = read_all()
    except DatabaseUnavailable as e:
        logger.warning(f"[settings] database unreachable, falling back to .env: {e}")
        return {}
    except Exception:
        logger.exception("[settings] could not read the settings store, falling back to .env")
        return {}

    known = set(all_keys())
    return {k: v for k, v in stored.items() if k in known}


def seed_from_environment(*, force: bool = False) -> int:
    seeded = 0
    with connection() as conn:
        existing = {
            row["key"] for row in conn.execute("SELECT key FROM app_settings").fetchall()
        }
        for key, setting in SETTINGS.items():
            if key in existing and not force:
                continue
            value = os.getenv(key)
            if value is None:
                value = setting.default
            value = value.strip()
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_by)
                VALUES (%s, %s, 'env-seed')
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = now()
                """,
                (key, value),
            )
            seeded += 1
    if seeded:
        logger.info(f"[settings] seeded {seeded} settings from the environment")
    return seeded


def write_many(updates: dict[str, str], *, changed_by: str) -> list[str]:
    if not updates:
        return []

    changed: list[str] = []
    with connection() as conn:
        current = {
            row["key"]: row["value"]
            for row in conn.execute(
                "SELECT key, value FROM app_settings WHERE key = ANY(%s)",
                (list(updates),),
            ).fetchall()
        }
        for key, value in updates.items():
            before = current.get(key)
            if before == value:
                continue
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_by, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = now()
                """,
                (key, value, changed_by),
            )
            setting = SETTINGS.get(key)
            redact = bool(setting and setting.secret)
            conn.execute(
                """
                INSERT INTO setting_changes (key, old_value, new_value, changed_by)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    key,
                    _for_audit(before, redact),
                    _for_audit(value, redact),
                    changed_by,
                ),
            )
            changed.append(key)
    return changed


def reset_keys(keys: list[str], *, changed_by: str) -> list[str]:
    if not keys:
        return []

    removed: list[str] = []
    with connection() as conn:
        current = {
            row["key"]: row["value"]
            for row in conn.execute(
                "SELECT key, value FROM app_settings WHERE key = ANY(%s)",
                (list(keys),),
            ).fetchall()
        }
        for key in keys:
            if key not in current:
                continue
            conn.execute("DELETE FROM app_settings WHERE key = %s", (key,))
            setting = SETTINGS.get(key)
            redact = bool(setting and setting.secret)
            conn.execute(
                """
                INSERT INTO setting_changes (key, old_value, new_value, changed_by)
                VALUES (%s, %s, %s, %s)
                """,
                (key, _for_audit(current[key], redact), "(reset to default)", changed_by),
            )
            removed.append(key)
    if removed:
        logger.info(f"[settings] {changed_by} reset {len(removed)} settings to default: {removed}")
    return removed


def recent_changes(limit: int = 40) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT key, old_value, new_value, changed_by, changed_at
            FROM setting_changes
            ORDER BY changed_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "key": row["key"],
            "label": SETTINGS[row["key"]].label if row["key"] in SETTINGS else row["key"],
            "from": row["old_value"],
            "to": row["new_value"],
            "by": row["changed_by"],
            "at": row["changed_at"].isoformat(),
        }
        for row in rows
    ]


def _for_audit(value: str | None, redact: bool) -> str | None:
    if value is None:
        return None
    if not redact:
        return value
    return SECRET_PLACEHOLDER if value else ""


def fingerprint() -> tuple[int, str]:
    with connection() as conn:
        row = conn.execute(
            "SELECT count(*) AS n, coalesce(max(updated_at)::text, '') AS latest "
            "FROM app_settings"
        ).fetchone()
    return int(row["n"]), row["latest"]


def prune_unknown() -> list[str]:
    known = set(all_keys())
    with connection() as conn:
        rows = conn.execute("SELECT key FROM app_settings WHERE NOT is_custom").fetchall()
        stale = sorted({row["key"] for row in rows} - known)
        if stale:
            conn.execute(
                "DELETE FROM app_settings WHERE key = ANY(%s) AND NOT is_custom", (stale,)
            )
    return stale
