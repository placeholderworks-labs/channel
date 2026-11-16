import json

import psycopg

from pw_channel.auth.permissions import Rejected
from pw_channel.db.core import connection

_COLUMNS = "id, name, agents, created_by, created_at, updated_at"


def _view(row: dict, members: list[dict] | None = None) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "agents": list(row["agents"] or []),
        "createdBy": row["created_by"],
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
        "members": members or [],
    }


def _clean_agents(agents) -> list[str]:
    seen = []
    for slug in agents or []:
        slug = str(slug).strip()
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def get(org_id: int | None) -> dict | None:
    if not org_id:
        return None
    with connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM organizations WHERE id = %s", (org_id,)).fetchone()
    return _view(row) if row else None


def list_all(members_by_org: dict[int, list[dict]]) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM organizations ORDER BY name").fetchall()
    return [_view(r, members_by_org.get(r["id"], [])) for r in rows]


def create(*, name: str, agents, actor: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise Rejected(400, "Give the client a name")
    try:
        with connection() as conn:
            row = conn.execute(
                f"INSERT INTO organizations (name, agents, created_by) VALUES (%s, %s, %s) RETURNING {_COLUMNS}",
                (name, json.dumps(_clean_agents(agents)), actor),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise Rejected(409, f"A client called {name!r} already exists")
    return _view(row)


def update(org_id: int, *, name: str | None = None, agents=None) -> dict:
    current = get(org_id)
    if current is None:
        raise Rejected(404, "No such client")
    new_name = (name if name is not None else current["name"]).strip()
    if not new_name:
        raise Rejected(400, "Give the client a name")
    new_agents = _clean_agents(agents) if agents is not None else current["agents"]
    try:
        with connection() as conn:
            row = conn.execute(
                f"UPDATE organizations SET name = %s, agents = %s, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
                (new_name, json.dumps(new_agents), org_id),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise Rejected(409, f"A client called {new_name!r} already exists")
    return _view(row)


def delete(org_id: int) -> None:
    with connection() as conn:
        members = conn.execute("SELECT count(*) AS n FROM dashboard_users WHERE org_id = %s", (org_id,)).fetchone()["n"]
        if members:
            raise Rejected(409, "Remove the client's people first")
        conn.execute("DELETE FROM organizations WHERE id = %s", (org_id,))


def allowed_agents(org_id: int | None) -> set[str] | None:
    if not org_id:
        return None
    org = get(org_id)
    return set(org["agents"]) if org else set()
