from __future__ import annotations

import json
import os
import logging
import logging.handlers
import queue
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from pw_channel.observability.console import (
    FILTER as CONSOLE_FILTER,
    ConsoleFormatter,
    ErrorCounter,
    supports_color,
)
from pw_channel.observability.context import current_context


LOG_DIR = Path(os.getenv("PW_LOG_DIR", "logs")).resolve()
LOG_FILE = LOG_DIR / f"{os.getenv('PW_SERVICE', 'pw')}.log"
LOG_MAX_BYTES = 32 * 1024 * 1024
LOG_BACKUP_COUNT = 5

_RESERVED = {"ts", "level", "logger", "event", "msg"}

_LOGRECORD_BUILTINS = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName", "structured", "log_context"}


_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|token|secret|password|passwd|authorization|auth|"
    r"credential|private[_-]?key|session|cookie|bearer)",
    re.IGNORECASE,
)

_SCRUBBERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 «redacted»"),
    (re.compile(r"(?i)\b(basic)\s+[A-Za-z0-9+/=]{8,}"), r"\1 «redacted»"),
    (
        re.compile(
            r"(?i)\b((?:api[_-]?key|apikey|token|secret|password|passwd|"
            r"auth[_-]?token|access[_-]?token|x-api-key|webhook[_-]?token)"
            r"[\"']?\s*[=:]\s*[\"']?)"
            r"([A-Za-z0-9._~+/=-]{6,})[\"']?"
        ),
        r"\1«redacted»",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9._-]{12,}"), "«redacted»"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "«redacted»"),
    (re.compile(r"\bap2_[A-Za-z0-9-]{20,}"), "«redacted»"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{30,}"), "«redacted»"),
    (re.compile(r"\bSK[0-9a-f]{32}\b"), "«redacted»"),
    (re.compile(r"\bAC[0-9a-f]{32}\b"), "«redacted»"),
    (re.compile(r"(?i)\b([a-z+]+://[^:/\s]+):[^@/\s]+@"), r"\1:«redacted»@"),
)

_PHONE_RE = re.compile(r"(?<![\w.])(\+?\d[\d\s-]{8,16}\d)(?![\w.])")


def _mask_phone(match: re.Match[str]) -> str:
    raw = match.group(1)
    digits = re.sub(r"\D", "", raw)

    explicit = raw.lstrip().startswith("+")
    indian_mobile = len(digits) == 10 and digits[0] in "6789"
    with_country_code = (
        11 <= len(digits) <= 13 and digits.startswith("91") and digits[2] in "6789"
    )

    if not (explicit or indian_mobile or with_country_code):
        return raw
    if not 10 <= len(digits) <= 15:
        return raw
    return f"{'+' if explicit else ''}{'*' * (len(digits) - 4)}{digits[-4:]}"


def redact(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 6:
        return "«too deep»"

    if isinstance(value, str):
        out = value
        for pattern, replacement in _SCRUBBERS:
            out = pattern.sub(replacement, out)
        return _PHONE_RE.sub(_mask_phone, out)

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key):
                result[key] = "«redacted»" if item not in (None, "") else None
            else:
                result[key] = redact(item, _depth=_depth + 1)
        return result

    if isinstance(value, (list, tuple)):
        return [redact(item, _depth=_depth + 1) for item in value]

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return redact(str(value), _depth=_depth + 1)


_TAG_RE = re.compile(r"^\s*\[([a-z0-9_.-]{2,24})\]\s*")


class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        event = None
        structured: dict[str, Any] = {}
        raw = getattr(record, "structured", None)
        if isinstance(raw, dict):
            structured = dict(raw)
            event = structured.pop("event", None)

        tag_match = _TAG_RE.match(message)
        if tag_match:
            message = message[tag_match.end() :]
            if event is None:
                event = tag_match.group(1)

        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "event": event or record.name.rsplit(".", 1)[-1],
            "logger": record.name,
            "msg": redact(message),
        }

        payload.update(getattr(record, "log_context", None) or current_context())

        if record.exc_info:
            kind, value, tb = record.exc_info
            payload["error"] = {
                "type": getattr(kind, "__name__", str(kind)),
                "message": redact(str(value)),
                "stack": redact("".join(traceback.format_exception(kind, value, tb))[-4000:]),
            }

        for key, item in structured.items():
            if key in _RESERVED:
                key = f"field_{key}"
            payload[key] = redact(item)

        for key, item in record.__dict__.items():
            if key in _LOGRECORD_BUILTINS or key in payload or key.startswith("_"):
                continue
            payload[key] = redact(item)

        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return json.dumps(
                {
                    "ts": payload["ts"],
                    "level": payload["level"],
                    "event": "log.unserializable",
                    "logger": record.name,
                    "msg": redact(message),
                }
            )


class _ExcInfoQueueHandler(logging.handlers.QueueHandler):

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        record.log_context = current_context()
        return record


_listener: logging.handlers.QueueListener | None = None


def configure_logging(level: str = "INFO", service: str | None = None) -> Path:
    global _listener, LOG_FILE
    if service and _listener is None:
        LOG_FILE = LOG_DIR / f"{service}.log"

    numeric = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)

    if _listener is not None:
        return LOG_FILE

    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter(supports_color(sys.stdout)))
    console.addFilter(CONSOLE_FILTER)
    root.addHandler(console)
    root.addHandler(ErrorCounter())

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(JsonFormatter())
    except OSError as e:
        root.warning(
            f"[logging] cannot write to {LOG_FILE} ({e}); JSON file logging is off "
            "and /internal/logs will have nothing to serve"
        )
        return LOG_FILE

    record_queue: queue.Queue = queue.Queue(maxsize=20000)
    root.addHandler(_ExcInfoQueueHandler(record_queue))

    _listener = logging.handlers.QueueListener(
        record_queue, file_handler, respect_handler_level=True
    )
    _listener.daemon = True
    _listener.start()

    _bridge_loguru(numeric)
    return LOG_FILE


_loguru_sink: int | None = None


def _bridge_loguru(level: int) -> None:
    global _loguru_sink
    if _loguru_sink is not None:
        return
    try:
        from loguru import logger as loguru_logger
    except ImportError:
        return

    loguru_logger.remove()

    def sink(message) -> None:
        record = message.record
        logging.getLogger(f"pipecat.{record['name']}").log(
            record["level"].no, record["message"]
        )

    _loguru_sink = loguru_logger.add(sink, level=level, colorize=False, format="{message}")


_QUIET_ACCESS_PATHS = ("/api/admin/status",)


class _QuietPollingFilter(logging.Filter):

    def __init__(self) -> None:
        super().__init__()
        self._seen: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for path in _QUIET_ACCESS_PATHS:
            if path in message:
                if path in self._seen:
                    return False
                self._seen.add(path)
                break
        return True


def adopt_uvicorn_loggers() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.propagate = True

    logging.getLogger("uvicorn.access").addFilter(_QuietPollingFilter())


def shutdown_logging() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None
