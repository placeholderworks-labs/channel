import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pw_channel import config
from pw_channel.channels.voice.routes import dynamic
from pw_channel.observability import call_scope, log_event

logger = logging.getLogger(__name__)
router = APIRouter()

def channels() -> list[str]:
    from pw_channel.channels.voice.telephony import registry

    return registry.TELEPHONY.names()

DISABLED_CLOSE_CODE = 1013


def is_enabled(channel: str) -> bool:
    return bool(getattr(config, f"ENABLE_{channel.upper()}", False))


def path_for(channel: str) -> str:
    return getattr(config, f"{channel.upper()}_WS_PATH", f"/ws/{channel}")


async def _serve(channel: str, websocket: WebSocket, handler, **scope) -> None:
    if not is_enabled(channel):
        logger.warning(
            f"[{channel}] refused a connection — the channel is off "
            f"(set ENABLE_{channel.upper()}=true; no restart needed)"
        )
        await websocket.close(code=DISABLED_CLOSE_CODE, reason="channel disabled")
        return

    with call_scope(channel=channel, **scope):
        started = time.monotonic()
        log_event("call.connected")
        try:
            await handler()
        except WebSocketDisconnect as e:
            detail = f" code={e.code} reason={e.reason!r}" if channel == "acefone" else ""
            logger.info(f"[{channel}] websocket disconnected{detail}")
        except Exception as e:
            logger.exception(f"[{channel}] pipeline error")
            log_event("call.failed", level=logging.ERROR, error=e)
        finally:
            log_event("call.disconnected", latency_ms=(time.monotonic() - started) * 1000)


async def ws_acefone(websocket: WebSocket):
    from pw_channel.channels.voice.telephony.acefone.stream import handle_acefone_websocket

    await _serve("acefone", websocket, lambda: handle_acefone_websocket(websocket))


async def ws_website(
    websocket: WebSocket,
    session_id: str | None = None,
    sample_rate: int | None = None,
    tts_provider: str | None = None,
    tts_voice: str | None = None,
    tts_model: str | None = None,
    use_case: str | None = None,
    test_record: str | None = None,
):
    from pw_channel.channels.voice.telephony.webrtc.stream import handle_website_websocket

    overrides = {
        k: v
        for k, v in {
            "provider": tts_provider,
            "voice": tts_voice,
            "model": tts_model,
        }.items()
        if v
    }

    await _serve(
        "website",
        websocket,
        lambda: handle_website_websocket(
            websocket,
            session_id=session_id,
            sample_rate=sample_rate,
            tts_overrides=overrides or None,
            use_case=use_case,
            test_record=test_record,
        ),
        session_id=session_id or "",
    )


def active_paths() -> list[str]:
    return [path_for(channel) for channel in channels() if is_enabled(channel)]


@dynamic.installer
def install_channel_routes(app) -> list[str]:
    from pw_channel.channels.voice.telephony import registry

    paths = []
    for provider in registry.all_providers():
        channel = provider.name
        path = path_for(channel)
        app.add_api_websocket_route(path, provider.websocket_endpoint(), name=dynamic.ROUTE_TAG)
        paths.append(path)
        logger.info(
            f"[channels] {channel} {'ENABLED' if is_enabled(channel) else 'disabled'} at {path}"
        )
    return paths
