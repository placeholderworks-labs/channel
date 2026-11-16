from fastapi import Depends, Header, HTTPException

from pw_channel.auth import roles
from pw_channel.auth import users
from pw_channel.auth.permissions import KEYS, PERMISSIONS, denied
from pw_channel.auth.sessions import InvalidSession, SessionUser, read_token
from pw_channel.db.core import DatabaseUnavailable, is_configured
from pw_sdk.utils.auth import bearer as parse_bearer

_ORDER = [p["key"] for p in PERMISSIONS]


def bearer(authorization: str) -> str:
    return parse_bearer(authorization)


def resolve_token(token: str) -> SessionUser:
    claims = read_token(token)
    if not is_configured():
        role = roles.resolve(claims.role)
        return SessionUser(
            id=claims.id, email=claims.email, name=claims.name, role=role["name"],
            permissions=frozenset(role["permissions"]),
        )

    row = users.account(claims.id)
    if row is None:
        raise InvalidSession("this account no longer exists")
    if not row["is_active"]:
        raise InvalidSession("this account has been deactivated")
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


def current_user(authorization: str = Header(default="")) -> SessionUser:
    try:
        return resolve_token(bearer(authorization))
    except InvalidSession as e:
        raise HTTPException(status_code=401, detail=str(e))
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=f"could not check your session: {e}")


def check(user: SessionUser, *perms: str) -> None:
    try:
        granted = roles.permissions_for(user.role)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=f"could not check your permissions: {e}")
    for perm in perms:
        if perm not in granted:
            raise HTTPException(status_code=403, detail=denied(perm))


def require(*perms: str):
    unknown = set(perms) - KEYS
    if unknown:
        raise ValueError(f"unknown permission(s): {sorted(unknown)}")

    def dependency(user: SessionUser = Depends(current_user)) -> SessionUser:
        check(user, *perms)
        return user

    dependency.__name__ = "require_" + "_".join(p.replace(".", "_") for p in perms)
    return dependency


def describe(user: SessionUser) -> dict:
    role = roles.resolve(user.role)
    granted = set(role["permissions"])
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": role["name"],
        "roleLabel": role["label"],
        "permissions": [k for k in _ORDER if k in granted],
        "mustChangePassword": user.must_change_password,
        **_org_fields(user),
    }


def _org_fields(user: SessionUser) -> dict:
    if not user.org_id:
        return {"orgId": None, "orgName": None, "agents": None}
    from pw_channel.auth import orgs

    org = orgs.get(user.org_id)
    return {"orgId": user.org_id, "orgName": org["name"] if org else None, "agents": org["agents"] if org else []}
