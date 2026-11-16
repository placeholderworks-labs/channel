import logging

import httpx

from pw_channel import config
from pw_sdk.utils.http import base_url

logger = logging.getLogger(__name__)


async def send_minutes(*, chat_session_id: str, user_type: str, call_context, user_turns: int) -> None:
    if not config.POST_CALL_MOM_ENABLED or not config.PW_CHAT_ENABLED or user_turns < 2:
        return
    url = base_url(config.PW_CHAT_API_URL) + "/calls/mom"
    payload = {
        "session_id": chat_session_id,
        "user_type": user_type,
        "channel": call_context.channel,
        "customer_name": call_context.customer_name or "",
        "phone_number": call_context.phone_number or "",
        "reference_id": call_context.booking_reference_id or "",
    }
    headers = {"X-Api-Token": config.PW_CHAT_API_TOKEN, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, json=payload, headers=headers)
        body = response.json() if response.content else {}
        logger.info(
            f"[post_call] minutes for session={chat_session_id} sent={body.get('sent')} "
            f"reason={body.get('reason', '')}"
        )
    except Exception as exc:
        logger.warning(f"[post_call] minutes for session={chat_session_id} failed: {exc}")
