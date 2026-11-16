import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from pw_channel import config
from pw_channel.auth import SessionUser
from pw_channel.auth.guards import require
from pw_channel.db.core import DatabaseUnavailable
from pw_channel.settings import custom_store
from pw_channel.settings.custom_store import CustomVariableError
from pw_sdk.utils.http import base_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["dashboard"])

TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=3.0)


def _brain_url(path: str = "") -> str:
    return base_url(config.PW_CHAT_API_URL) + "/variables" + path


async def _brain_call(method: str, path: str = "", **kwargs) -> dict:
    if not config.PW_CHAT_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="The chatbot brain is switched off for this container, so its table "
            "cannot be read from here. Turn on PW_CHAT_ENABLED first.",
        )
    if not config.PW_CHAT_API_TOKEN:
        raise HTTPException(
            status_code=409,
            detail="PW_CHAT_API_TOKEN is not set, so this dashboard cannot authenticate "
            "against the chatbot.",
        )

    url = _brain_url(path)
    headers = {"X-Api-Token": config.PW_CHAT_API_TOKEN, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        logger.warning(f"[db] {method} {url} failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"The chatbot did not answer at {url}. Check that it is running and "
            "that this build carries its /voice/variables routes.",
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("detail") or detail
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=str(detail)[:400])

    return response.json()


@router.get("/settings/{key}/reveal")
def reveal_setting(key: str, user: SessionUser = Depends(require("secrets.reveal"))):
    try:
        value = custom_store.reveal(key)
    except CustomVariableError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    logger.info(f"[settings] {user.email} revealed {key}")
    return {"key": key, "value": value}


@router.get("/brain/settings/{key}/reveal")
async def reveal_brain_setting(key: str, user: SessionUser = Depends(require("secrets.reveal"))):
    payload = await _brain_call("GET", f"/{key}/reveal")
    logger.info(f"[settings] {user.email} revealed chatbot {key}")
    return payload
