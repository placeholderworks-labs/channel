import asyncio
import json
import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from pw_channel import config

logger = logging.getLogger(__name__)

class ResultSurface:
    async def results(
        self, seq: int, html: str, user_text: str, *, spoken: bool, result_id: str = ""
    ) -> None:
        return

    async def empty(self, seq: int) -> None:
        return

    async def error(self, seq: int, reason: str) -> None:
        return

    async def handoff(self, seq: int, *, agent: bool, main_menu: bool) -> None:
        return

    async def status(self, seq: int, text: str) -> None:
        return

    def latency(self, turn: dict) -> None:
        return


class NullResultSurface(ResultSurface):
    async def results(
        self, seq: int, html: str, user_text: str, *, spoken: bool, result_id: str = ""
    ) -> None:
        if html:
            logger.info(
                f"[voice_engine] seq={seq} html={len(html.encode('utf-8'))}bytes discarded "
                "(no screen on this channel)"
            )


class BrowserResultSurface(ResultSurface):
    def __init__(self, websocket: WebSocket):
        self._websocket = websocket
        self._loop = None

    async def _send(self, payload: dict) -> None:
        if self._websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await self._websocket.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"[voice_engine] send failed: {e.__class__.__name__} ({e})")

    async def _send_html(self, seq: int, html: str, result_id: str = "") -> None:
        size = config.PW_CHAT_HTML_CHUNK_BYTES
        pieces = [html[i:i + size] for i in range(0, len(html), size)]
        for index, piece in enumerate(pieces):
            await self._send(
                {
                    "type": "result_html",
                    "seq": seq,
                    "chunk": index,
                    "chunks": len(pieces),
                    "html": piece,
                    "result_id": result_id,
                }
            )

    async def results(
        self, seq: int, html: str, user_text: str, *, spoken: bool, result_id: str = ""
    ) -> None:
        if html and len(html.encode("utf-8")) <= config.PW_CHAT_MAX_HTML_BYTES:
            logger.info(
                f"[voice_engine] results seq={seq} html={len(html)}chars"
                + ("" if spoken else " (turn was abandoned — shown, not spoken)")
            )
            await self._send({"type": "result_pending", "seq": seq})
            await self._send_html(seq, html, result_id)
        else:
            if html:
                logger.warning(
                    f"[voice_engine] results seq={seq} dropped — "
                    f"{len(html.encode('utf-8'))} bytes over PW_CHAT_MAX_HTML_BYTES"
                )
            await self._send({"type": "result_empty", "seq": seq})

    async def empty(self, seq: int) -> None:
        await self._send({"type": "result_empty", "seq": seq})

    async def status(self, seq: int, text: str) -> None:
        await self._send({"type": "status", "seq": seq, "text": text})

    async def error(self, seq: int, reason: str) -> None:
        await self._send({"type": "result_error", "seq": seq, "reason": reason})

    async def handoff(self, seq: int, *, agent: bool, main_menu: bool) -> None:
        await self._send(
            {"type": "result_handoff", "seq": seq, "agent": agent, "main_menu": main_menu}
        )

    def latency(self, turn: dict) -> None:
        loop = self._loop
        if loop is None:
            try:
                loop = self._loop = asyncio.get_running_loop()
            except RuntimeError:
                return
        loop.create_task(self._send({"type": "latency", **turn}))
