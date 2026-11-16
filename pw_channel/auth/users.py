import logging
import secrets
import threading
import time

import psycopg

from pw_channel import config
from pw_channel.auth import roles
from pw_channel.auth.passwords import hash_password, verify_password
from pw_channel.auth.permissions import SUPER_ADMIN, Rejected
from pw_channel.auth.sessions import SessionUser
from pw_channel.db.core import connection

logger = logging.getLogger(__name__)

ACCOUNT_CACHE_SECS = 5.0

_USER_COLUMNS = """
    id, email, name, role, is_active, must_change_password, invited_by,
    created_at, last_login_at, org_id
"""


class LoginFailed(Exception):
    pass


def temp_password() -> str:
    return secrets.token_urlsafe(12)


_accounts: dict[int, tuple[float, dict | None]] = {}
_accounts_lock = threading.Lock()


def account(user_id: int) -> dict | None:
    now = time.monotonic()
    with _accounts_lock:
        hit = _accounts.get(user_id)
        if hit and now - hit[0] < ACCOUNT_CACHE_SECS:
            return hit[1]
    with connection() as conn:
        row = conn.execute(
            f"SELECT {_USER_COLUMNS} FROM dashboard_users WHERE id = %s", (user_id,)
        ).fetchone()
    with _accounts_lock:
        _accounts[user_id] = (now, row)
    return row


def forget(user_id: int | None = None) -> None:
    with _accounts_lock:
        if user_id is None:
            _accounts.clear()
        else:
            _accounts.pop(user_id, None)


def _view(row: dict) -> dict:
    role = roles.resolve(row["role"])
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": role["name"],
        "roleLabel": role["label"],
        "isActive": row["is_active"],
        "mustChangePassword": row["must_change_password"],
        "createdAt": row["created_at"].isoformat(),
        "lastLoginAt": row["last_login_at"].isoformat() if row["last_login_at"] else None,
        "invitedBy": row["invited_by"],
        "orgId": row.get("org_id"),
    }


def ensure_seed_admin() -> None:
    email = config.DASHBOARD_ADMIN_EMAIL
    password = config.DASHBOARD_ADMIN_PASSWORD
    if not email:
        logger.warning(
            "[auth] DASHBOARD_ADMIN_EMAIL is not set, so there is no super admin from the "
            "environment. Set it (and DASHBOARD_ADMIN_PASSWORD) and restart."
        )
        return

    with connection() as conn:
        row = conn.execute(
            "SELECT id, role FROM dashboard_users WHERE email = %s", (email,)
        ).fetchone()
        if row:
            if row["role"] == "admin":
                conn.execute(
                    "UPDATE dashboard_users SET role = %s, updated_at = now() WHERE id = %s",
                    (SUPER_ADMIN, row["id"]),
                )
                logger.info(f"[auth] promoted {email} to super admin")
            return
        if not password:
            logger.warning(
                f"[auth] DASHBOARD_ADMIN_PASSWORD is not set, so no login was created for {email}"
            )
            return
        conn.execute(
            """
            INSERT INTO dashboard_users (email, name, password_hash, role)
            VALUES (%s, %s, %s, %s)
            """,
            (email, config.DASHBOARD_ADMIN_NAME or email.split("@")[0],
             hash_password(password), SUPER_ADMIN),
        )
    logger.info(f"[auth] created the first dashboard login for {email}")


def authenticate(email: str, password: str) -> SessionUser:
    email = (email or "").strip().lower()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, name, password_hash, role, is_active, must_change_password
            FROM dashboard_users WHERE email = %s
            """,
            (email,),
        ).fetchone()

        if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
            raise LoginFailed("that email and password don't match an account")

    role = roles.resolve(row["role"])
    return SessionUser(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=role["name"],
        permissions=frozenset(role["permissions"]),
        must_change_password=row["must_change_password"],
    )


def session_user(user_id: int) -> SessionUser:
    forget(user_id)
    row = account(user_id)
    if not row or not row["is_active"]:
        raise LoginFailed("this account can no longer sign in")
    with connection() as conn:
        conn.execute("UPDATE dashboard_users SET last_login_at = now() WHERE id = %s", (user_id,))
    role = roles.resolve(row["role"])
    return SessionUser(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=role["name"],
        permissions=frozenset(role["permissions"]),
        must_change_password=row["must_change_password"],
        org_id=row.get("org_id"),
    )


def set_org(user_id: int, org_id: int | None) -> None:
    with connection() as conn:
        conn.execute("UPDATE dashboard_users SET org_id = %s WHERE id = %s", (org_id, user_id))
    forget(user_id)


def change_password(*, user_id: int, current_password: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("the new password needs at least 8 characters")

    with connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM dashboard_users WHERE id = %s", (user_id,)
        ).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            raise LoginFailed("your current password is wrong")
        if current_password == new_password:
            raise ValueError("choose a password different from the current one")
        conn.execute(
            """
            UPDATE dashboard_users
            SET password_hash = %s, must_change_password = FALSE, updated_at = now()
            WHERE id = %s
            """,
            (hash_password(new_password), user_id),
        )
    forget(user_id)


RESET_LINK_MINUTES = 15


def _reset_hash(token: str) -> str:
    from pw_channel.auth.sessions import _signing_key
    import hashlib
    import hmac

    return hmac.new(_signing_key(), f"reset:{token}".encode(), hashlib.sha256).hexdigest()


def request_reset(email: str) -> tuple[dict, str] | None:
    email = (email or "").strip().lower()
    with connection() as conn:
        row = conn.execute(
            f"SELECT {_USER_COLUMNS} FROM dashboard_users WHERE email = %s AND is_active", (email,)
        ).fetchone()
        if row is None:
            return None
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM password_resets WHERE user_id = %s AND used_at IS NULL", (row["id"],))
        conn.execute(
            "INSERT INTO password_resets (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, now() + make_interval(mins => %s))",
            (row["id"], _reset_hash(token), RESET_LINK_MINUTES),
        )
    return _view(row), token


def reset_with_token(token: str, new_password: str) -> dict:
    if len(new_password or "") < 8:
        raise ValueError("the new password needs at least 8 characters")
    with connection() as conn:
        found = conn.execute(
            "SELECT id, user_id FROM password_resets "
            "WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()",
            (_reset_hash(token or ""),),
        ).fetchone()
        if found is None:
            raise LoginFailed("this reset link has expired or was already used. Ask for a new one")
        row = conn.execute(
            f"""
            UPDATE dashboard_users
            SET password_hash = %s, must_change_password = FALSE, updated_at = now()
            WHERE id = %s AND is_active
            RETURNING {_USER_COLUMNS}
            """,
            (hash_password(new_password), found["user_id"]),
        ).fetchone()
        if row is None:
            raise LoginFailed("this account can no longer sign in")
        conn.execute("UPDATE password_resets SET used_at = now() WHERE id = %s", (found["id"],))
        conn.execute("DELETE FROM password_resets WHERE user_id = %s AND used_at IS NULL", (found["user_id"],))
    forget(row["id"])
    return _view(row)


def list_users() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            f"SELECT {_USER_COLUMNS} FROM dashboard_users ORDER BY created_at"
        ).fetchall()
    return [_view(row) for row in rows]


def _lock_team(conn) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (roles.TEAM_LOCK,))


def _load(conn, user_id: int) -> dict:
    row = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM dashboard_users WHERE id = %s", (user_id,)
    ).fetchone()
    if row is None:
        raise Rejected(404, "There is no such user")
    return row


def _can_assign(actor: SessionUser, role_name: str) -> None:
    if not roles.exists(role_name):
        raise Rejected(400, f"There is no role called {role_name}")
    if actor.role == SUPER_ADMIN:
        return
    if role_name == SUPER_ADMIN:
        raise Rejected(403, "Only a super admin can grant the Super admin role")
    if not roles.permissions_for(role_name) <= roles.permissions_for(actor.role):
        raise Rejected(
            403, f"You can't grant the {roles.resolve(role_name)['label']} role. "
            "It has permissions your own role doesn't"
        )


def _can_manage(actor: SessionUser, target: dict) -> None:
    if actor.role == SUPER_ADMIN:
        return
    if target["role"] == SUPER_ADMIN:
        raise Rejected(403, "Only a super admin can change a super admin's account")
    if not roles.permissions_for(target["role"]) <= roles.permissions_for(actor.role):
        raise Rejected(
            403, f"{target['email']} has permissions your own role doesn't, so you can't change "
            "their account"
        )


def _keep_a_super_admin(conn, leaving_id: int) -> None:
    other = conn.execute(
        "SELECT 1 FROM dashboard_users WHERE role = %s AND is_active AND id <> %s LIMIT 1",
        (SUPER_ADMIN, leaving_id),
    ).fetchone()
    if other is None:
        raise Rejected(409, "There must always be at least one active super admin")


def create_user(
    *,
    actor: SessionUser,
    email: str,
    name: str = "",
    role: str = "operator",
    password: str | None = None,
) -> tuple[dict, str]:
    email = (email or "").strip().lower()
    if not email or "@" not in email or " " in email:
        raise Rejected(400, "Enter a valid email address")
    if password is not None and len(password) < 8:
        raise Rejected(400, "The password needs at least 8 characters")
    _can_assign(actor, role)
    password = password or temp_password()

    try:
        with connection() as conn:
            _lock_team(conn)
            row = conn.execute(
                f"""
                INSERT INTO dashboard_users
                    (email, name, password_hash, role, must_change_password, invited_by)
                VALUES (%s, %s, %s, %s, TRUE, %s)
                ON CONFLICT (email) DO NOTHING
                RETURNING {_USER_COLUMNS}
                """,
                (email, (name or "").strip() or email.split("@")[0],
                 hash_password(password), role, actor.email),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        row = None
    if row is None:
        raise Rejected(409, f"{email} already has an account")
    logger.info(f"[auth] {actor.email} added {email} as {role}")
    return _view(row), password


def update_user(
    *,
    actor: SessionUser,
    user_id: int,
    name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> dict:
    with connection() as conn:
        _lock_team(conn)
        target = _load(conn, user_id)
        _can_manage(actor, target)

        role_changes = role is not None and role != target["role"]
        if user_id == actor.id:
            if role_changes:
                raise Rejected(403, "You can't change your own role")
            if is_active is False:
                raise Rejected(403, "You can't deactivate your own account")
        if role_changes:
            _can_assign(actor, role)

        leaves_super = target["role"] == SUPER_ADMIN and target["is_active"] and (
            (role_changes and role != SUPER_ADMIN) or is_active is False
        )
        if leaves_super:
            _keep_a_super_admin(conn, user_id)

        row = conn.execute(
            f"""
            UPDATE dashboard_users SET
                name = COALESCE(%s, name),
                role = COALESCE(%s, role),
                is_active = COALESCE(%s, is_active),
                updated_at = now()
            WHERE id = %s
            RETURNING {_USER_COLUMNS}
            """,
            (
                ((name or "").strip() or target["email"].split("@")[0]) if name is not None else None,
                role if role_changes else None,
                is_active,
                user_id,
            ),
        ).fetchone()
    forget(user_id)
    logger.info(f"[auth] {actor.email} updated {row['email']}")
    return _view(row)


def reset_password(*, actor: SessionUser, user_id: int) -> tuple[dict, str]:
    password = temp_password()
    with connection() as conn:
        _lock_team(conn)
        target = _load(conn, user_id)
        _can_manage(actor, target)
        row = conn.execute(
            f"""
            UPDATE dashboard_users
            SET password_hash = %s, must_change_password = TRUE, updated_at = now()
            WHERE id = %s
            RETURNING {_USER_COLUMNS}
            """,
            (hash_password(password), user_id),
        ).fetchone()
    forget(user_id)
    logger.info(f"[auth] {actor.email} reset the password for {row['email']}")
    return _view(row), password


def delete_user(*, actor: SessionUser, user_id: int) -> None:
    if user_id == actor.id:
        raise Rejected(403, "You can't delete your own account")
    with connection() as conn:
        _lock_team(conn)
        target = _load(conn, user_id)
        _can_manage(actor, target)
        if target["role"] == SUPER_ADMIN and target["is_active"]:
            _keep_a_super_admin(conn, user_id)
        conn.execute("DELETE FROM dashboard_users WHERE id = %s", (user_id,))
    forget(user_id)
    logger.info(f"[auth] {actor.email} deleted {target['email']}")
