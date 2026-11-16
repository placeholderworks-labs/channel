import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from pw_channel.channels.whatsapp import forward
from pw_channel.channels.whatsapp.providers.pool import pool
from pw_channel.channels.whatsapp.sessions import session_manager
from pw_channel.channels.whatsapp.settings import settings
from pw_sdk.utils.auth import same_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel/whatsapp", tags=["whatsapp"])
legacy_router = APIRouter(include_in_schema=False)


def _any_provider(name: str):
    provider = pool().pick(name)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"no {name} WhatsApp number is configured")
    return provider


async def verify(name: str, request: Request):
    challenge = _any_provider(name).verify(request)
    if challenge is None:
        if request.query_params.get("hub.challenge") is None:
            return {"status": "ok"}
        raise HTTPException(status_code=403, detail="verification failed")
    return PlainTextResponse(content=challenge)


async def receive(name: str, request: Request) -> Response:
    probe = _any_provider(name)
    if not probe.authorized(request):
        raise HTTPException(status_code=401, detail="unauthorised webhook")
    try:
        payload = await request.json()
    except ValueError:
        return Response(status_code=200)
    if not probe.is_inbound(payload):
        return Response(status_code=200)
    from_number, to_number = probe.routing(payload)
    if request.headers.get(forward.FORWARDED_HEADER) != "true" and from_number:
        target = forward.target_for(name, from_number, to_number)
        if target:
            extra = {"X-Webhook-Secret": settings.nowonextel_webhook_secret} if name == "nowonextel" and settings.nowonextel_webhook_secret else {}
            forward.forward(target, payload, extra)
            return Response(status_code=200)
    provider = pool().pick(name, to_number)
    message = provider.parse_webhook_message(payload)
    if not message:
        return Response(status_code=200)
    logger.info(f"[whatsapp] {name} {provider.sender} <- {message.from_number}")
    asyncio.create_task(pool().handler(provider).process_incoming_message(
        message.from_number, message.message_text, message.message_id,
        audio_media_id=message.audio_media_id or "", audio_url=message.audio_url or "", media=message.media,
    ))
    return Response(status_code=200)


@router.get("/webhook")
async def verify_meta(request: Request):
    return await verify("meta", request)


@router.post("/webhook")
async def receive_meta(request: Request):
    return await receive("meta", request)


@router.get("/webhook/{name}")
async def verify_named(name: str, request: Request):
    return await verify(name, request)


@router.post("/webhook/{name}")
async def receive_named(name: str, request: Request):
    return await receive(name, request)


@router.get("/media/{name}/{sender}/{media_id}")
async def serve_media(name: str, sender: str, media_id: str):
    provider = pool().providers(name).get(sender) or pool().pick(name)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown number")
    result = await provider.download_media(media_id)
    if not result:
        raise HTTPException(status_code=404, detail="media not found or expired")
    return Response(content=result["content"], media_type=result["content_type"], headers={"Cache-Control": "private, max-age=3600"})


async def require_admin(x_admin_secret: str = Header(default="")):
    if not same_secret(settings.admin_secret, x_admin_secret):
        raise HTTPException(status_code=403, detail="forbidden")


@router.post("/agent-reply", dependencies=[Depends(require_admin)])
async def agent_reply(request: Request):
    payload = await request.json()
    message = payload.get("message", {})
    recipient = message.get("recipient", {}).get("to")
    content = message.get("content", {})
    if not recipient:
        raise HTTPException(status_code=400, detail="missing recipient.to")
    provider = pool().for_sender(message.get("sender", {}).get("from", "")) or pool().default()
    if provider is None:
        raise HTTPException(status_code=503, detail="no WhatsApp number is configured")
    kind = content.get("type", "").upper()
    sent = False
    if kind == "TEXT":
        text = content.get("text", "")
        sent = await provider.send_text_message(recipient, text)
        if settings.agent_chat_ended_marker in (text or ""):
            await session_manager.clear_flow_mode(recipient)
    elif kind == "ATTACHMENT":
        attachment = content.get("attachment", {})
        url, caption = attachment.get("url", ""), attachment.get("caption", "")
        if attachment.get("type", "").lower() == "image":
            sent = await provider.send_image_with_caption(recipient, url, caption)
        else:
            sent = await provider.send_document(recipient, url, caption)
    elif kind == "INTERACTIVE":
        interactive = content.get("interactive", {})
        body = interactive.get("body", {}).get("text", "")
        action = interactive.get("action", {})
        kind_of = interactive.get("type", "").lower()
        if kind_of == "cta_url":
            params = action.get("parameters", {})
            sent = await provider.send_interactive_button(recipient, body, params.get("display_text", "View"), params.get("url", ""))
        elif kind_of == "button":
            buttons = [{"id": b.get("reply", {}).get("id", b.get("id", "")), "title": b.get("reply", {}).get("title", b.get("title", ""))}
                       for b in action.get("buttons", [])]
            sent = await provider.send_interactive_reply_button(recipient, body, buttons)
        elif kind_of == "list":
            sent = await provider.send_list_message(recipient, interactive.get("header", {}).get("text", ""), body,
                                                    interactive.get("footer", {}).get("text", ""), action.get("sections", []))
    logger.info(f"[whatsapp] agent reply to {recipient} type={kind} sent={sent}")
    return {"messages": [{"status": {"groupId": 3, "groupName": "DELIVERED" if sent else "REJECTED"}}]}


@router.get("/sessions", dependencies=[Depends(require_admin)])
async def sessions_info():
    return {"active": await session_manager.get_active_session_count(), "redis": await session_manager.get_redis_info()}


@router.delete("/sessions/{session_id}", dependencies=[Depends(require_admin)])
async def delete_session(session_id: str):
    await session_manager.delete_session(session_id)
    return {"deleted": session_id}


@legacy_router.get("/webhook")
async def legacy_verify_meta(request: Request):
    return await verify("meta", request)


@legacy_router.post("/webhook")
async def legacy_receive_meta(request: Request):
    return await receive("meta", request)


@legacy_router.get("/webhook/{name}")
async def legacy_verify_named(name: str, request: Request):
    return await verify(name, request)


@legacy_router.post("/webhook/{name}")
async def legacy_receive_named(name: str, request: Request):
    return await receive(name, request)


@legacy_router.post("/sendMessage", dependencies=[Depends(require_admin)])
async def legacy_send_message(request: Request):
    return await agent_reply(request)
