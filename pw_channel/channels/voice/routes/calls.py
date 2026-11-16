import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from pw_channel import config
from pw_channel.db import DatabaseUnavailable, call_sessions, call_transcripts
from pw_channel.channels.voice.calls import masking as call_masking
from pw_sdk.utils.auth import bearer as parse_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calls", tags=["calls"])


def require_token(
    authorization: str = Header(default=""),
    x_api_key: str = Header(default=""),
) -> None:
    expected = config.ACEFONE_WEBHOOK_TOKEN
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="this endpoint needs ACEFONE_WEBHOOK_TOKEN set to guard it",
        )
    supplied = parse_bearer(authorization) or (x_api_key or "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="bad or missing token")


@router.get("/active", dependencies=[Depends(require_token)])
def active(did: str = ""):
    if not config.USE_DB:
        raise HTTPException(status_code=503, detail="live call tracking needs USE_DB=true")
    did = did.strip()
    if not did:
        raise HTTPException(
            status_code=400, detail="did is required: ask for one line's calls, not every call"
        )
    try:
        calls = call_sessions.active(did=did)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"count": len(calls), "calls": call_masking.agent_views(calls)}


@router.get("/{session_id}/transcript", dependencies=[Depends(require_token)])
def transcript(session_id: int):
    if not config.USE_DB:
        raise HTTPException(status_code=503, detail="live call tracking needs USE_DB=true")
    try:
        call = call_sessions.by_id(session_id)
        if call is None:
            raise HTTPException(status_code=404, detail="no such call")
        return {
            "call": call_masking.agent_view(call),
            "turns": call_transcripts.for_session(session_id),
        }
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
