import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from pw_channel import config
from pw_channel.auth import SessionUser
from pw_channel.auth.guards import require
from pw_channel.admin.schema import SettingsResetRequest, SettingsUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/brain", tags=["dashboard"])

TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=3.0)

def _unreachable(url: str) -> str:
    return (
        f"The chatbot did not answer at {url}, so its settings cannot be read or changed "
        "from here. Check that it is running and that PW_CHAT_API_URL reaches it from "
        "this process."
    )


def _headers() -> dict[str, str]:
    if not config.PW_CHAT_API_TOKEN:
        raise HTTPException(
            status_code=409,
            detail="PW_CHAT_API_TOKEN is not set, so this dashboard cannot authenticate "
                   "against the chatbot. Set it under Settings → Common → Chatbot brain.",
        )
    return {"X-Api-Token": config.PW_CHAT_API_TOKEN, "Content-Type": "application/json"}


async def _call(method: str, path: str = "", **kwargs) -> dict:
    url = config.PW_CHAT_SETTINGS_URL + path
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(method, url, headers=_headers(), **kwargs)
    except httpx.HTTPError as e:
        logger.warning(f"[brain] {method} {url} failed: {e}")
        raise HTTPException(status_code=502, detail=_unreachable(url))

    if response.status_code >= 400:
        detail = response.text
        try:
            body = response.json()
            detail = body.get("detail") or detail
        except ValueError:
            pass
        if isinstance(detail, list):
            detail = "; ".join(str(d) for d in detail)
        raise HTTPException(status_code=response.status_code, detail=str(detail)[:400])

    return response.json()


@router.get("/settings")
async def get_brain_settings(_: SessionUser = Depends(require("settings.view"))):
    if not config.PW_CHAT_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="The chatbot brain is switched off for this container, so it has no "
                   "settings to show. Turn on PW_CHAT_ENABLED first.",
        )

    payload = await _call("GET")
    return {
        "sections": payload.get("sections", []),
        "values": payload.get("values", {}),
        "editable": bool(payload.get("editable")),
        "source": payload.get("source", "environment"),
        "restartKeys": [],
        "url": config.PW_CHAT_SETTINGS_URL,
    }


@router.put("/settings")
async def put_brain_settings(
    req: SettingsUpdateRequest, user: SessionUser = Depends(require("settings.edit"))
):
    payload = await _call("PUT", json={"values": req.values})
    saved = payload.get("saved") or payload.get("updated") or []
    logger.info(f"[brain] {user.email} changed {len(saved)} chatbot settings: {saved}")
    return {
        "saved": saved,
        "applied": True,
        "restartRequired": [],
        "message": payload.get("message")
        or f"Applied {len(saved)} " + ("change" if len(saved) == 1 else "changes") + ".",
    }


@router.post("/settings/reset")
async def reset_brain_settings(
    req: SettingsResetRequest, user: SessionUser = Depends(require("settings.edit"))
):
    removed = []
    for key in req.keys:
        payload = await _call("DELETE", f"/{key}")
        if payload.get("cleared"):
            removed.append(key)

    logger.info(f"[brain] {user.email} reset {len(removed)} chatbot settings to default: {removed}")
    return {
        "reset": removed,
        "message": (
            f"{len(removed)} " + ("setting is" if len(removed) == 1 else "settings are")
            + " back on the default."
            if removed
            else "Nothing was stored for those — they were already on their defaults."
        ),
    }
