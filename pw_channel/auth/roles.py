import logging
import re
import threading
import time

import psycopg
from psycopg.types.json import Jsonb

from pw_channel.auth.permissions import (
    DEFAULT_ROLES,
    FALLBACK_ROLE,
    KEYS,
    PERMISSIONS,
    SUPER_ADMIN,
    Rejected,
    label_for,
)
from pw_channel.db.core import DatabaseUnavailable, connection, is_configured

logger = logging.getLogger(__name__)

CACHE_SECS = 5.0
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
TEAM_LOCK = 741_001
_ORDER = {p["key"]: i for i, p in enumerate(PERMISSIONS)}

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "roles": None}


def _ordered(keys) -> list[str]:
    return sorted({k for k in keys if k in KEYS}, key=_ORDER.__getitem__)


def _defaults() -> dict[str, dict]:
    return {
        r["name"]: {
            "name": r["name"],
            "label": r["label"],
            "description": r["description"],
            "permissions": _ordered(r["permissions"]),
            "isSystem": r["is_system"],
            "updatedAt": None,
            "updatedBy": None,
        }
        for r in DEFAULT_ROLES
    }


def _view(row: dict) -> dict:
    return {
        "name": row["name"],
        "label": row["label"] or row["name"],
        "description": row["description"],
        "permissions": _ordered(row["permissions"] or []),
        "isSystem": row["is_system"],
        "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
        "updatedBy": row["updated_by"],
    }


def _load() -> dict[str, dict]:
    if not is_configured():
        return _defaults()
    try:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT name, label, description, permissions, is_system, updated_at, updated_by
                FROM roles ORDER BY id
                """
            ).fetchall()
    except psycopg.errors.UndefinedTable:
        return _defaults()
    return {row["name"]: _view(row) for row in rows} or _defaults()


def all_roles() -> dict[str, dict]:
    now = time.monotonic()
    with _lock:
        cached = _cache["roles"]
        if cached is not None and now - _cache["at"] < CACHE_SECS:
            return cached
    try:
        roles = _load()
    except DatabaseUnavailable:
        if cached is not None:
            return cached
        raise
    with _lock:
        _cache.update(at=now, roles=roles)
    return roles


def invalidate() -> None:
    with _lock:
        _cache["roles"] = None


def resolve(name: str) -> dict:
    roles = all_roles()
    role = roles.get(name) or roles.get(FALLBACK_ROLE)
    if role is None:
        return {"name": FALLBACK_ROLE, "label": "Viewer", "permissions": []}
    return role


def permissions_for(name: str) -> frozenset[str]:
    return frozenset(resolve(name)["permissions"])


def exists(name: str) -> bool:
    return name in all_roles()


def ensure_default_roles() -> None:
    with connection() as conn:
        for role in DEFAULT_ROLES:
            conn.execute(
                """
                INSERT INTO roles (name, label, description, permissions, is_system)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (role["name"], role["label"], role["description"],
                 Jsonb(_ordered(role["permissions"])), role["is_system"]),
            )
        conn.execute(
            "UPDATE roles SET permissions = %s, is_system = TRUE WHERE name = %s AND permissions <> %s",
            (Jsonb(_ordered(KEYS)), SUPER_ADMIN, Jsonb(_ordered(KEYS))),
        )
    invalidate()


def _clean_permissions(permissions) -> list[str]:
    unknown = sorted(set(permissions) - KEYS)
    if unknown:
        raise Rejected(400, f"Unknown permission: {', '.join(unknown)}")
    return _ordered(permissions)


def _no_escalation(actor, permissions: list[str]) -> None:
    if actor.role == SUPER_ADMIN:
        return
    missing = [k for k in permissions if k not in permissions_for(actor.role)]
    if missing:
        raise Rejected(
            403, f"You can't grant '{label_for(missing[0])}': your own role doesn't have it"
        )


def list_roles() -> list[dict]:
    with connection() as conn:
        counts = {
            row["role"]: row["n"]
            for row in conn.execute(
                "SELECT role, count(*) AS n FROM dashboard_users GROUP BY role"
            ).fetchall()
        }
    return [{**role, "userCount": counts.get(name, 0)} for name, role in all_roles().items()]


def create_role(*, actor, name: str, label: str, description: str, permissions) -> dict:
    name = (name or "").strip().lower()
    if not NAME_PATTERN.match(name):
        raise Rejected(
            400, "Role names are 2-31 characters: lowercase letters, digits and _, starting with a letter"
        )
    permissions = _clean_permissions(permissions)
    _no_escalation(actor, permissions)
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO roles (name, label, description, permissions, is_system, updated_by)
            VALUES (%s, %s, %s, %s, FALSE, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING name, label, description, permissions, is_system, updated_at, updated_by
            """,
            (name, (label or "").strip() or name, (description or "").strip(),
             Jsonb(permissions), actor.email),
        ).fetchone()
    if row is None:
        raise Rejected(409, f"A role called {name} already exists")
    invalidate()
    logger.info(f"[auth] {actor.email} created role {name}")
    return {**_view(row), "userCount": 0}


def update_role(*, actor, name: str, label=None, description=None, permissions=None) -> dict:
    current = all_roles().get(name)
    if current is None:
        raise Rejected(404, f"There is no role called {name}")
    if name == SUPER_ADMIN:
        raise Rejected(403, "The Super admin role can't be changed")
    if current["isSystem"] and actor.role != SUPER_ADMIN:
        raise Rejected(403, f"Only a super admin can change the {current['label']} role")
    if permissions is not None:
        permissions = _clean_permissions(permissions)
        _no_escalation(actor, [k for k in permissions if k not in current["permissions"]])

    with connection() as conn:
        row = conn.execute(
            """
            UPDATE roles SET
                label = COALESCE(%s, label),
                description = COALESCE(%s, description),
                permissions = COALESCE(%s, permissions),
                updated_at = now(),
                updated_by = %s
            WHERE name = %s
            RETURNING name, label, description, permissions, is_system, updated_at, updated_by
            """,
            (
                (label.strip() or name) if label is not None else None,
                description.strip() if description is not None else None,
                Jsonb(permissions) if permissions is not None else None,
                actor.email,
                name,
            ),
        ).fetchone()
        users = conn.execute(
            "SELECT count(*) AS n FROM dashboard_users WHERE role = %s", (name,)
        ).fetchone()["n"]
    if row is None:
        raise Rejected(404, f"There is no role called {name}")
    invalidate()
    logger.info(f"[auth] {actor.email} updated role {name}")
    return {**_view(row), "userCount": users}


def delete_role(*, actor, name: str) -> None:
    current = all_roles().get(name)
    if current is None:
        raise Rejected(404, f"There is no role called {name}")
    if current["isSystem"]:
        raise Rejected(409, f"{current['label']} is a built-in role and can't be deleted")
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (TEAM_LOCK,))
        users = conn.execute(
            "SELECT count(*) AS n FROM dashboard_users WHERE role = %s", (name,)
        ).fetchone()["n"]
        if users:
            raise Rejected(
                409,
                f"{users} {'user still has' if users == 1 else 'users still have'} the "
                f"{current['label']} role. Move them to another role first",
            )
        conn.execute("DELETE FROM roles WHERE name = %s", (name,))
    invalidate()
    logger.info(f"[auth] {actor.email} deleted role {name}")
