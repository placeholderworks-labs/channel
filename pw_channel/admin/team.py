import logging
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException

from pw_channel.auth import access_requests
from pw_channel.auth import roles
from pw_channel.auth import users
from pw_channel.auth.guards import current_user, require
from pw_channel.auth.permissions import PERMISSIONS, Rejected
from pw_channel.auth.sessions import SessionUser
from pw_channel.db.core import DatabaseUnavailable
from pw_channel.admin.schema import (
    CreateRoleRequest,
    CreateUserRequest,
    UpdateRoleRequest,
    UpdateUserRequest,
)
from pw_channel.channels.email import mailer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["dashboard"])


@contextmanager
def _http():
    try:
        yield
    except Rejected as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=f"the database is unreachable: {e}")


def _delivery(emailed: bool, error: str | None, password: str) -> dict:
    return {"emailed": emailed, "emailError": error, "tempPassword": None if emailed else password}


@router.get("/users")
def list_users(_: SessionUser = Depends(require("team.view"))):
    with _http():
        return {"users": users.list_users()}


@router.post("/users", status_code=201)
def invite_user(req: CreateUserRequest, actor: SessionUser = Depends(require("team.manage"))):
    with _http():
        user, password = users.create_user(
            actor=actor, email=req.email, name=req.name, role=req.role, password=req.password
        )
    emailed, error = False, None
    if req.sendInvite:
        emailed, error = mailer.send_invite(
            user["email"], user["name"], password, user["roleLabel"], actor.name or actor.email
        )
    return {"user": user, **_delivery(emailed, error, password)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, req: UpdateUserRequest, actor: SessionUser = Depends(require("team.manage"))
):
    with _http():
        return {
            "user": users.update_user(
                actor=actor, user_id=user_id, name=req.name, role=req.role, is_active=req.isActive
            )
        }


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, actor: SessionUser = Depends(require("team.manage"))):
    with _http():
        user, password = users.reset_password(actor=actor, user_id=user_id)
    emailed, error = mailer.send_password_reset(
        user["email"], user["name"], password, actor.name or actor.email
    )
    return {"user": user, **_delivery(emailed, error, password)}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, actor: SessionUser = Depends(require("team.manage"))):
    with _http():
        users.delete_user(actor=actor, user_id=user_id)
    return {"ok": True}


@router.get("/roles")
def list_roles(_: SessionUser = Depends(require("team.view"))):
    with _http():
        return {"roles": roles.list_roles(), "catalog": list(PERMISSIONS)}


@router.post("/roles", status_code=201)
def create_role(req: CreateRoleRequest, actor: SessionUser = Depends(require("roles.manage"))):
    with _http():
        return {
            "role": roles.create_role(
                actor=actor, name=req.name, label=req.label,
                description=req.description, permissions=req.permissions,
            )
        }


@router.put("/roles/{name}")
def update_role(
    name: str, req: UpdateRoleRequest, actor: SessionUser = Depends(require("roles.manage"))
):
    with _http():
        return {
            "role": roles.update_role(
                actor=actor, name=name, label=req.label,
                description=req.description, permissions=req.permissions,
            )
        }


@router.delete("/roles/{name}")
def delete_role(name: str, actor: SessionUser = Depends(require("roles.manage"))):
    with _http():
        roles.delete_role(actor=actor, name=name)
    return {"ok": True}


@router.post("/access-requests", status_code=201)
def request_access(payload: dict, user: SessionUser = Depends(current_user)):
    with _http():
        request, created = access_requests.create(
            user,
            permission=str(payload.get("permission") or "").strip(),
            page=str(payload.get("page") or "").strip(),
            note=str(payload.get("note") or ""),
        )
    if created:
        logger.info(f"[access] {user.email} asked for {request['permission']} (#{request['id']})")
    return {"request": request, "alreadyPending": not created}


@router.get("/access-requests/mine")
def my_access_requests(user: SessionUser = Depends(current_user)):
    with _http():
        return {"requests": access_requests.mine(user.id), "catalog": list(PERMISSIONS)}


@router.get("/access-requests")
def pending_access_requests(_: SessionUser = Depends(require("team.view"))):
    with _http():
        return {"requests": access_requests.pending()}


@router.post("/access-requests/{request_id}/resolve")
def resolve_access_request(request_id: int, payload: dict, actor: SessionUser = Depends(require("team.manage"))):
    with _http():
        request = access_requests.resolve(request_id, status=str(payload.get("status") or ""), actor=actor)
    logger.info(f"[access] {actor.email} marked request #{request_id} {request['status']}")
    return {"request": request}


def _internal(user: SessionUser) -> None:
    if user.org_id:
        raise HTTPException(status_code=403, detail="Client accounts cannot manage clients")


@router.get("/clients")
def list_clients(actor: SessionUser = Depends(require("team.view"))):
    from pw_channel.auth import orgs

    _internal(actor)
    with _http():
        everyone = users.list_users()
        by_org: dict[int, list[dict]] = {}
        for person in everyone:
            if person.get("orgId"):
                by_org.setdefault(person["orgId"], []).append(person)
        return {"clients": orgs.list_all(by_org), "internal": [p for p in everyone if not p.get("orgId")]}


@router.post("/clients", status_code=201)
def create_client(payload: dict, actor: SessionUser = Depends(require("team.manage"))):
    from pw_channel.auth import orgs

    _internal(actor)
    with _http():
        return orgs.create(name=payload.get("name", ""), agents=payload.get("agents") or [], actor=actor.email)


@router.patch("/clients/{org_id}")
def update_client(org_id: int, payload: dict, actor: SessionUser = Depends(require("team.manage"))):
    from pw_channel.auth import orgs

    _internal(actor)
    with _http():
        return orgs.update(org_id, name=payload.get("name"), agents=payload.get("agents"))


@router.delete("/clients/{org_id}", status_code=204)
def delete_client(org_id: int, actor: SessionUser = Depends(require("team.manage"))):
    from pw_channel.auth import orgs

    _internal(actor)
    with _http():
        orgs.delete(org_id)


@router.post("/clients/{org_id}/members", status_code=201)
def add_client_member(org_id: int, req: CreateUserRequest, actor: SessionUser = Depends(require("team.manage"))):
    from pw_channel.auth import orgs

    _internal(actor)
    with _http():
        org = orgs.get(org_id)
        if org is None:
            raise Rejected(404, "No such client")
        user, password = users.create_user(
            actor=actor, email=req.email, name=req.name, role="client", password=req.password
        )
        users.set_org(user["id"], org_id)
        user = {**user, "orgId": org_id}
    emailed, error = False, None
    if req.sendInvite:
        emailed, error = mailer.send_invite(
            user["email"], user["name"], password, f"{user['roleLabel']} · {org['name']}", actor.name or actor.email
        )
    return {"user": user, **_delivery(emailed, error, password)}
