from __future__ import annotations

import logging
import os
import re

from pw_channel.db.core import connection
from pw_channel.settings.registry import SETTINGS
from pw_channel.settings.store import SECRET_PLACEHOLDER

logger = logging.getLogger(__name__)

KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,199}$")

_exported: set[str] = set()


class CustomVariableError(ValueError):
    pass


def clean_key(key: str) -> str:
    key = (key or "").strip()
    if not KEY_PATTERN.match(key):
        raise CustomVariableError(
            f"{key!r} is not a usable variable name — start with a letter or underscore "
            "and use only letters, digits and underscores"
        )
    return key


def read_rows() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT key, value, is_custom, updated_at, updated_by "
            "FROM app_settings ORDER BY is_custom DESC, key"
        ).fetchall()

    out = []
    for row in rows:
        setting = SETTINGS.get(row["key"])
        secret = bool(setting and setting.secret)
        custom = bool(row["is_custom"]) or setting is None
        default = setting.default if setting else ""
        drifted = not custom and (row["value"] or "").strip() != (default or "").strip()

        out.append(
            {
                "key": row["key"],
                "value": SECRET_PLACEHOLDER if secret and row["value"] else row["value"],
                "secret": secret,
                "stored": True,
                "custom": custom,
                "managed": setting is not None,
                "label": setting.label if setting else "",
                "type": setting.type if setting else "text",
                "options": list(setting.options) if setting else [],
                "unit": setting.unit if setting else "",
                "help": setting.help if setting else "",
                "restart": bool(setting and setting.restart),
                "defaultValue": None if (secret or custom) else default,
                "changedFromDefault": drifted,
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
                "updatedBy": row["updated_by"],
            }
        )

    unstored = set(SETTINGS) - {row["key"] for row in rows}
    for key in sorted(unstored):
        setting = SETTINGS[key]
        value = setting.default
        out.append(
            {
                "key": key,
                "value": SECRET_PLACEHOLDER if setting.secret and value else value,
                "secret": setting.secret,
                "stored": False,
                "custom": False,
                "managed": True,
                "label": setting.label,
                "type": setting.type,
                "options": list(setting.options),
                "unit": setting.unit,
                "help": setting.help,
                "restart": setting.restart,
                "defaultValue": None if setting.secret else setting.default,
                "changedFromDefault": False,
                "updatedAt": None,
                "updatedBy": "",
            }
        )
    return out


def upsert(key: str, value: str, *, changed_by: str) -> dict:
    key = clean_key(key)
    if key in SETTINGS:
        raise CustomVariableError(
            f"{key} is a managed setting — change it on the Settings screen so its "
            "validation still runs"
        )

    text = "" if value is None else str(value)
    with connection() as conn:
        before = conn.execute(
            "SELECT value FROM app_settings WHERE key = %s", (key,)
        ).fetchone()
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_by, updated_at, is_custom)
            VALUES (%s, %s, %s, now(), TRUE)
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now(),
                    is_custom = TRUE
            """,
            (key, text, changed_by),
        )
        conn.execute(
            """
            INSERT INTO setting_changes (key, old_value, new_value, changed_by)
            VALUES (%s, %s, %s, %s)
            """,
            (key, before["value"] if before else None, text, changed_by),
        )

    os.environ[key] = text
    _exported.add(key)
    logger.info(f"[settings] {changed_by} set custom variable {key}")
    return {"key": key, "value": text, "created": before is None}


def delete(key: str, *, changed_by: str) -> bool:
    key = clean_key(key)
    with connection() as conn:
        before = conn.execute(
            "SELECT value, is_custom FROM app_settings WHERE key = %s", (key,)
        ).fetchone()
        if not before:
            return False
        conn.execute("DELETE FROM app_settings WHERE key = %s", (key,))
        setting = SETTINGS.get(key)
        old = before["value"]
        if setting is not None and setting.secret and old:
            old = SECRET_PLACEHOLDER
        conn.execute(
            """
            INSERT INTO setting_changes (key, old_value, new_value, changed_by)
            VALUES (%s, %s, %s, %s)
            """,
            (key, old, "(deleted)", changed_by),
        )

    if key in _exported:
        os.environ.pop(key, None)
        _exported.discard(key)
    logger.info(f"[settings] {changed_by} deleted variable {key}")
    return True


def apply_to_environment() -> int:
    with connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE is_custom"
        ).fetchall()
    for row in rows:
        os.environ[row["key"]] = row["value"]
        _exported.add(row["key"])
    return len(rows)


def reveal(key: str) -> str:
    key = clean_key(key)
    with connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
    if row:
        return row["value"]

    setting = SETTINGS.get(key)
    return setting.default if setting else ""
