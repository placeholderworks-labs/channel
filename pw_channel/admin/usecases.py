import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from pw_channel import config
from pw_channel.auth.guards import require
from pw_channel.auth.sessions import SessionUser
from pw_channel.observability import log_event
from pw_channel.channels.voice.routes.ws import channels
from pw_channel.settings.store import write_many
from pw_channel.channels.voice import usecases

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["voice-studio"])


async def _brain(method: str, path: str, *, user: SessionUser | None = None, json=None, params=None, timeout: float = 20.0):
    if not config.PW_CHAT_API_TOKEN:
        raise HTTPException(
            status_code=409,
            detail="PW_CHAT_API_TOKEN is not set, so the brain will not accept Studio changes",
        )
    url = f"{usecases.base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=3.0)) as client:
            response = await client.request(
                method, url, json=json, params=params,
                headers=usecases.headers(user.email if user else ""),
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"the brain is unreachable at {url}: {e}")

    if response.status_code == 204:
        return None
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text[:500] or f"brain answered HTTP {response.status_code}"}
    if response.status_code == 404 and isinstance(body, dict) and body.get("detail") == "Not Found":
        raise HTTPException(
            status_code=502,
            detail="The brain (pw-llm) is running an older build without this feature. "
            "restart it to load the latest code.",
        )
    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else body
        if isinstance(detail, list):
            detail = "; ".join(
                f"{'.'.join(str(p) for p in d.get('loc', [])[1:])}: {d.get('msg')}" for d in detail
            )
        raise HTTPException(status_code=response.status_code, detail=detail or "brain refused the request")
    return body


def _defaults() -> dict:
    out = {}
    for channel in channels():
        override = (config.PW_CHAT_USER_TYPES_BY_CHANNEL.get(channel) or "").strip()
        out[channel] = override or (
            config.PW_CHAT_USER_TYPE_WEBSITE if channel == "website" else config.PW_CHAT_USER_TYPE_PHONE
        )
    return out


def _allowed(user: SessionUser) -> set[str] | None:
    if not user.org_id:
        return None
    from pw_channel.auth import orgs

    return orgs.allowed_agents(user.org_id)


def _guard_slug(user: SessionUser, slug: str) -> None:
    allowed = _allowed(user)
    if allowed is not None and slug not in allowed:
        raise HTTPException(status_code=404, detail=f"no agent {slug!r}")


@router.get("/usecases")
async def list_usecases(user: SessionUser = Depends(require("usecases.view"))):
    body = await _brain("GET", "/usecases")
    allowed = _allowed(user)
    if allowed is not None:
        body = {**body, "usecases": [u for u in body.get("usecases") or [] if u.get("slug") in allowed]}
    return {**body, "defaults": _defaults(), "channels": channels()}


@router.put("/usecases/defaults")
async def set_defaults(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    if not config.USE_DB:
        raise HTTPException(status_code=409, detail="Saving needs USE_DB=true")
    updates = {}
    for channel, slug in (payload or {}).items():
        if channel not in channels():
            raise HTTPException(status_code=400, detail=f"{channel!r} is not a channel")
        usecase = await usecases.fetch(slug)
        if not usecases.usable_on(usecase, channel):
            raise HTTPException(
                status_code=400,
                detail=f"{slug!r} is not an active agent on the {channel} channel",
            )
        updates[f"PW_CHAT_BRAIN_{channel.upper()}"] = slug
    write_many(updates, changed_by=user.email)
    config.reload()
    log_event("usecase.defaults", requested_by=user.email, **updates)
    return {"defaults": _defaults()}


@router.post("/usecases/suggest-greetings")
async def suggest_greetings(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    return await _brain("POST", "/usecases/suggest-greetings", user=user, json=payload)


@router.post("/usecases/suggest-refusals")
async def suggest_refusals(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    return await _brain("POST", "/usecases/suggest-refusals", user=user, json=payload)


@router.get("/usecases/{slug}")
async def get_usecase(slug: str, _: SessionUser = Depends(require("usecases.view"))):
    _guard_slug(_, slug)
    return await _brain("GET", f"/usecases/{slug}")


@router.post("/usecases", status_code=201)
async def create_usecase(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    body = await _brain("POST", "/usecases", user=user, json=payload)
    log_event("usecase.created", slug=body.get("slug"), requested_by=user.email)
    return body


@router.put("/usecases/{slug}")
async def update_usecase(slug: str, payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    body = await _brain("PUT", f"/usecases/{slug}", user=user, json=payload)
    usecases.forget(slug)
    log_event("usecase.updated", slug=slug, version=body.get("version"), requested_by=user.email)
    return {**body, "qmsReleased": await _release_held(slug, user)}


async def _release_held(slug: str, user: SessionUser) -> list[dict]:
    from pw_channel.intake import replay as qms_release

    try:
        released = await qms_release.on_agent_changed(slug, user.email)
    except Exception:
        logger.exception(f"[qms] could not release held records for {slug}")
        return []
    for r in released:
        log_event("qms.released", intake=r["intake"], agent=slug, released=r["released"], requested_by=user.email)
    return released


@router.delete("/usecases/{slug}", status_code=204)
async def delete_usecase(slug: str, user: SessionUser = Depends(require("usecases.delete"))):
    if slug in _defaults().values():
        raise HTTPException(
            status_code=409,
            detail=f"{slug!r} is a channel's default agent. Pick another default first",
        )
    await _brain("DELETE", f"/usecases/{slug}", user=user)
    usecases.forget(slug)
    log_event("usecase.deleted", slug=slug, requested_by=user.email)
    return Response(status_code=204)


@router.post("/usecases/{slug}/duplicate", status_code=201)
async def duplicate_usecase(slug: str, payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    return await _brain("POST", f"/usecases/{slug}/duplicate", user=user, json=payload)


@router.get("/usecases/{slug}/versions")
async def usecase_versions(slug: str, _: SessionUser = Depends(require("usecases.view"))):
    _guard_slug(_, slug)
    return await _brain("GET", f"/usecases/{slug}/versions")


@router.post("/usecases/{slug}/rollback")
async def rollback_usecase(slug: str, payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    body = await _brain("POST", f"/usecases/{slug}/rollback", user=user, json=payload)
    usecases.forget(slug)
    return {**body, "qmsReleased": await _release_held(slug, user)}


@router.get("/usecases/{slug}/preview")
async def preview_usecase(
    slug: str, language: str = "hindi", _: SessionUser = Depends(require("usecases.view"))
):
    _guard_slug(_, slug)
    return await _brain("GET", f"/usecases/{slug}/preview", params={"language": language})


@router.get("/tools")
async def list_tools(_: SessionUser = Depends(require("tools.view"))):
    return await _brain("GET", "/tools")


@router.get("/tools/custom/{name}")
async def get_custom_tool(name: str, _: SessionUser = Depends(require("tools.view"))):
    return await _brain("GET", f"/tools/custom/{name}")


@router.post("/tools/custom", status_code=201)
async def create_custom_tool(payload: dict, user: SessionUser = Depends(require("tools.edit"))):
    body = await _brain("POST", "/tools/custom", user=user, json=payload)
    log_event("tool.created", name=payload.get("name"), requested_by=user.email)
    return body


@router.put("/tools/custom/{name}")
async def update_custom_tool(name: str, payload: dict, user: SessionUser = Depends(require("tools.edit"))):
    body = await _brain("PUT", f"/tools/custom/{name}", user=user, json=payload)
    log_event("tool.updated", name=name, requested_by=user.email)
    return body


@router.delete("/tools/custom/{name}", status_code=204)
async def delete_custom_tool(name: str, user: SessionUser = Depends(require("tools.edit"))):
    await _brain("DELETE", f"/tools/custom/{name}", user=user)
    log_event("tool.deleted", name=name, requested_by=user.email)
    return Response(status_code=204)


@router.post("/tools/custom/{name}/test")
async def test_custom_tool(name: str, payload: dict, user: SessionUser = Depends(require("tools.edit"))):
    return await _brain("POST", f"/tools/custom/{name}/test", user=user, json=payload, timeout=45.0)


@router.post("/tools/custom/{name}/sync")
async def sync_mcp_server(name: str, user: SessionUser = Depends(require("tools.edit"))):
    body = await _brain("POST", f"/tools/custom/{name}/sync", user=user, timeout=45.0)
    log_event("tool.synced", name=name, requested_by=user.email)
    return body


@router.post("/tools/mcp/discover")
async def discover_mcp_server(payload: dict, _: SessionUser = Depends(require("tools.edit"))):
    return await _brain("POST", "/tools/mcp/discover", json=payload, timeout=45.0)


@router.put("/tools/builtin/{name}")
async def switch_builtin_tool(name: str, payload: dict, user: SessionUser = Depends(require("tools.edit"))):
    body = await _brain("PUT", f"/tools/builtin/{name}", user=user, json=payload)
    log_event("tool.switched", name=name, enabled=payload.get("enabled"), requested_by=user.email)
    return body


@router.get("/globals")
async def list_globals(_: SessionUser = Depends(require("usecases.view"))):
    return await _brain("GET", "/globals")


@router.put("/globals")
async def save_globals(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    body = await _brain("PUT", "/globals", user=user, json=payload)
    usecases.forget()
    log_event("globals.saved", count=len(body.get("variables") or []), requested_by=user.email)
    return body


@router.get("/guardrails")
async def list_guardrails(_: SessionUser = Depends(require("usecases.view"))):
    return await _brain("GET", "/guardrails")


@router.post("/guardrails", status_code=201)
async def create_guardrail(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    body = await _brain("POST", "/guardrails", user=user, json=payload)
    usecases.forget()
    log_event("guardrail.created", id=body.get("id"), requested_by=user.email)
    return body


@router.put("/guardrails/{gid}")
async def update_guardrail(gid: str, payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    body = await _brain("PUT", f"/guardrails/{gid}", user=user, json=payload)
    usecases.forget()
    log_event("guardrail.updated", id=gid, requested_by=user.email)
    return body


@router.delete("/guardrails/{gid}", status_code=204)
async def delete_guardrail(gid: str, user: SessionUser = Depends(require("usecases.delete"))):
    await _brain("DELETE", f"/guardrails/{gid}", user=user)
    usecases.forget()
    log_event("guardrail.deleted", id=gid, requested_by=user.email)
    return Response(status_code=204)


@router.post("/transliterate")
async def transliterate(payload: dict, user: SessionUser = Depends(require("usecases.edit"))):
    return await _brain("POST", "/transliterate", user=user, json={"text": str((payload or {}).get("text") or "")[:60]})


@router.get("/llm/options")
async def llm_options(_: SessionUser = Depends(require("usecases.view"))):
    return await _brain("GET", "/llm/options")
