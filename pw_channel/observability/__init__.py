from pw_channel.observability import console
from pw_channel.observability.context import bind_call, call_scope, current_context, log_event
from pw_channel.observability.json_logging import (
    adopt_uvicorn_loggers,
    configure_logging,
    redact,
    shutdown_logging,
)
from pw_channel.observability.reader import follow_lines, tail_lines


def log_file():
    from pw_channel.observability import json_logging

    return json_logging.LOG_FILE


__all__ = [
    "adopt_uvicorn_loggers",
    "bind_call",
    "call_scope",
    "configure_logging",
    "console",
    "current_context",
    "follow_lines",
    "log_event",
    "log_file",
    "redact",
    "shutdown_logging",
    "tail_lines",
]
