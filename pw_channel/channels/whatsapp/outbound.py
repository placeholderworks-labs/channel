import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from pw_channel.channels.whatsapp import sending
from pw_channel.channels.whatsapp.settings import settings
from pw_sdk.utils.auth import bearer, same_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel/whatsapp", tags=["whatsapp"])
legacy_router = APIRouter(include_in_schema=False)


async def verify_secret(x_admin_secret: str = Header(default=""), authorization: str = Header(default="")):
    expected = settings.voicebot_api_secret or settings.admin_secret
    if not expected:
        raise HTTPException(status_code=503, detail="server auth not configured")
    if not (same_secret(expected, x_admin_secret) or same_secret(expected, bearer(authorization))):
        raise HTTPException(status_code=403, detail="invalid or missing X-Admin-Secret")


def _digits(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isdigit())
    if not cleaned:
        raise ValueError("phone_number must contain digits")
    return value if value.startswith("+") else cleaned


class LinkSendIn(BaseModel):
    event: str = Field(default="resume_link", min_length=1)
    phone_number: str = Field(min_length=8)
    reference_id: str = Field(min_length=1)
    resume_url: str = ""
    booking_url: str = ""
    customer_name: str = ""
    language: str = "en"
    channel: str = ""
    call_reference_id: str = ""
    source: str = "voicebot"
    template_name: str = ""

    @field_validator("phone_number")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        return _digits(value)


class TextSendIn(BaseModel):
    phone_number: str = Field(min_length=8)
    text: str = Field(min_length=1, max_length=4096)
    dedupe_key: str = ""

    @field_validator("phone_number")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        return _digits(value)


async def send_link(payload: LinkSendIn) -> dict:
    event = "resume_link" if payload.event == "abandoned_cart_booking_link" else payload.event
    try:
        body, button = sending.resume_message(event, payload.customer_name, payload.reference_id)
    except KeyError:
        return {"success": False, "message": f"unsupported event '{payload.event}'"}
    link = sending.resume_link(payload.resume_url or payload.booking_url, payload.reference_id)
    if not link:
        return {"success": False, "message": "no resume link: the record has no resume_url and VOICEBOT_CART_LINK_BASE is not set"}
    outcome = await sending.send_cta(payload.phone_number, body, button, link,
                                     dedupe=f"{event}:{payload.reference_id}:{payload.phone_number}")
    if outcome.ok:
        return {"success": True, "status": "sent", "message_id": outcome.message_id, "duplicate": outcome.duplicate,
                "sender": outcome.sender}
    logger.error(f"[whatsapp] link send failed for {payload.reference_id}: {outcome.error}")
    return {"success": False, "message": outcome.error}


async def send_plain(payload: TextSendIn) -> dict:
    outcome = await sending.send_text(payload.phone_number, payload.text, dedupe=f"msg:{payload.dedupe_key}" if payload.dedupe_key else None)
    if outcome.ok:
        return {"success": True, "status": "sent", "message_id": outcome.message_id, "duplicate": outcome.duplicate}
    return {"success": False, "message": outcome.error}


@router.post("/send", dependencies=[Depends(verify_secret)])
async def post_send(payload: LinkSendIn):
    return await send_link(payload)


@router.post("/text", dependencies=[Depends(verify_secret)])
async def post_text(payload: TextSendIn):
    return await send_plain(payload)


@legacy_router.post("/api/whatsapp/voicebot/send", dependencies=[Depends(verify_secret)])
async def legacy_send(payload: LinkSendIn):
    return await send_link(payload)


@legacy_router.post("/api/whatsapp/voicebot/message", dependencies=[Depends(verify_secret)])
async def legacy_text(payload: TextSendIn):
    return await send_plain(payload)
