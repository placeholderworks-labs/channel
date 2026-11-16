import logging

from pw_channel.auth import roles
from pw_channel.auth.permissions import LABELS, Rejected, label_for
from pw_channel.auth.sessions import SessionUser
from pw_channel.db.core import connection
from pw_channel.channels.email import mailer

logger = logging.getLogger(__name__)

STATUSES = ("pending", "granted", "dismissed")
_COLUMNS = "id, user_id, email, name, role, permission, page, note, status, resolved_by, resolved_at, created_at"


def _view(row: dict) -> dict:
    iso = lambda v: v.isoformat() if v else None
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "roleLabel": roles.resolve(row["role"])["label"] if row["role"] else "",
        "permission": row["permission"],
        "permissionLabel": label_for(row["permission"]),
        "page": row["page"],
        "note": row["note"],
        "status": row["status"],
        "resolvedBy": row["resolved_by"],
        "resolvedAt": iso(row["resolved_at"]),
        "createdAt": iso(row["created_at"]),
    }


def create(user: SessionUser, *, permission: str, page: str = "", note: str = "") -> tuple[dict, bool]:
    if permission not in LABELS:
        raise Rejected(422, f"unknown permission {permission!r}")
    if permission in roles.permissions_for(user.role):
        raise Rejected(409, "your role already has this permission; sign out and back in to pick it up")
    with connection() as conn:
        existing = conn.execute(
            f"SELECT {_COLUMNS} FROM access_requests WHERE user_id = %s AND permission = %s AND status = 'pending'",
            (user.id, permission),
        ).fetchone()
        if existing:
            return _view(existing), False
        row = conn.execute(
            f"""
            INSERT INTO access_requests (user_id, email, name, role, permission, page, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {_COLUMNS}
            """,
            (user.id, user.email, user.name or "", user.role, permission, page[:200], note.strip()[:500]),
        ).fetchone()
    request = _view(row)
    _notify_admins(request)
    return request, True


def _admins() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT email, name, role FROM dashboard_users WHERE is_active"
        ).fetchall()
    return [r for r in rows if "team.manage" in roles.permissions_for(r["role"])]


def _notify_admins(request: dict) -> None:
    link = f"{mailer.dashboard_url().rstrip('/')}/team"
    for admin in _admins():
        if admin["email"] == request["email"]:
            continue
        sent, error = mailer.send_access_request(
            admin["email"], admin["name"], request=request, link=link,
        )
        if not sent:
            logger.warning(f"[access] could not email {admin['email']} about request #{request['id']}: {error}")


def pending() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM access_requests WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    return [_view(r) for r in rows]


def mine(user_id: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM access_requests WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
    return [_view(r) for r in rows]


def resolve(request_id: int, *, status: str, actor: SessionUser) -> dict:
    if status not in ("granted", "dismissed"):
        raise Rejected(422, "status must be granted or dismissed")
    with connection() as conn:
        row = conn.execute(
            f"""
            UPDATE access_requests SET status = %s, resolved_by = %s, resolved_at = now()
            WHERE id = %s AND status = 'pending' RETURNING {_COLUMNS}
            """,
            (status, actor.email, request_id),
        ).fetchone()
    if row is None:
        raise Rejected(404, "no pending request with that id")
    request = _view(row)
    sent, error = mailer.send_access_decision(request["email"], request["name"], request=request,
                                              link=mailer.dashboard_url())
    if not sent:
        logger.warning(f"[access] could not email {request['email']} about request #{request_id}: {error}")
    return request
