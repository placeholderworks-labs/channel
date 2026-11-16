from __future__ import annotations

import contextlib
import logging
import secrets
import time
from contextvars import ContextVar
from typing import Any

_call_id: ContextVar[str] = ContextVar("call_id", default="")
_session_id: ContextVar[str] = ContextVar("session_id", default="")
_channel: ContextVar[str] = ContextVar("channel", default="")


def new_call_id() -> str:
    return f"{int(time.time()) % 100000:05d}-{secrets.token_hex(3)}"


def bind_call(
    *,
    call_id: str | None = None,
    session_id: str | None = None,
    channel: str | None = None,
) -> None:
    if call_id is not None:
        _call_id.set(call_id)
    if session_id is not None:
        _session_id.set(session_id)
    if channel is not None:
        _channel.set(channel)


@contextlib.contextmanager
def call_scope(
    *,
    channel: str,
    call_id: str | None = None,
    session_id: str | None = None,
):
    tokens = (
        _call_id.set(call_id or new_call_id()),
        _session_id.set(session_id or ""),
        _channel.set(channel),
    )
    try:
        yield _call_id.get()
    finally:
        _call_id.reset(tokens[0])
        _session_id.reset(tokens[1])
        _channel.reset(tokens[2])


def current_context() -> dict[str, str]:
    return {
        key: value
        for key, value in (
            ("call_id", _call_id.get()),
            ("session_id", _session_id.get()),
            ("channel", _channel.get()),
        )
        if value
    }


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    logger: logging.Logger | None = None,
    message: str | None = None,
    latency_ms: float | None = None,
    error: BaseException | str | None = None,
    **fields: Any,
) -> None:
    log = logger or logging.getLogger("pw.event")
    extra: dict[str, Any] = {"event": event}

    if latency_ms is not None:
        extra["latency_ms"] = round(float(latency_ms), 1)
    if error is not None:
        extra["error"] = (
            {"type": type(error).__name__, "message": str(error)}
            if isinstance(error, BaseException)
            else {"message": str(error)}
        )
    extra.update(fields)

    log.log(level, message or event, extra={"structured": extra})
