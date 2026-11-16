import logging
from urllib.parse import quote

import httpx

from pw_channel import config
from pw_sdk.utils.http import base_url

logger = logging.getLogger(__name__)

TABLE = "voice_history"
LABEL = "Brain history"
BLURB = "What the brain stored for voice sessions, in the chatbot's own database."
NOTE = "Deleted over the chatbot's API rather than with a query from here."
TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)


class BrainUnavailable(RuntimeError):
    pass


def _url(path: str = "") -> str:
    return base_url(config.PW_CHAT_API_URL) + "/history" + path


def enabled() -> bool:
    return bool(config.PW_CHAT_ENABLED and config.PW_CHAT_API_TOKEN)


async def call(method: str, path: str = "", **kwargs) -> dict:
    if not config.PW_CHAT_ENABLED:
        raise BrainUnavailable(
            "The chatbot is switched off for this container, so voice_history cannot be "
            "reached from here. Turn on PW_CHAT_ENABLED first."
        )
    if not config.PW_CHAT_API_TOKEN:
        raise BrainUnavailable(
            "PW_CHAT_API_TOKEN is not set, so this dashboard cannot authenticate against "
            "the chatbot."
        )

    url = _url(path)
    headers = {"X-Api-Token": config.PW_CHAT_API_TOKEN, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        logger.warning(f"[data] {method} {url} failed: {e}")
        raise BrainUnavailable(
            f"The chatbot did not answer at {url}. Check that it is running and that this "
            "build carries its /voice/history routes."
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("detail") or detail
        except ValueError:
            pass
        raise BrainUnavailable(str(detail)[:400])

    return response.json()


async def summary() -> dict:
    payload = await call("GET")
    return {
        "table": TABLE,
        "label": LABEL,
        "blurb": BLURB,
        "note": NOTE,
        "remote": True,
        "exists": bool(payload.get("exists")),
        "rows": payload.get("rows", 0),
        "newest": payload.get("newest"),
        "bytes": payload.get("bytes", 0),
        "database": payload.get("database", ""),
    }


def unreachable_card(reason: str) -> dict:
    return {
        "table": TABLE,
        "label": LABEL,
        "blurb": BLURB,
        "note": NOTE,
        "remote": True,
        "exists": False,
        "rows": 0,
        "newest": None,
        "bytes": 0,
        "database": "",
        "error": reason,
    }


async def read(*, limit: int = 50, offset: int = 0, term: str = "") -> dict:
    return await call(
        "GET", f"/rows?limit={limit}&offset={offset}&q={quote(term or '')}"
    )


async def row(row_id: int) -> dict:
    return await call("GET", f"/rows/{row_id}")


async def delete_row(row_id: int) -> dict:
    return await call("DELETE", f"/rows/{row_id}")


async def purge(*, older_than_days: int = 0) -> dict:
    return await call("POST", "/purge", json={"olderThanDays": older_than_days})
