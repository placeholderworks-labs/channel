import asyncio
import logging

from pw_channel import config
from pw_channel.db import call_transcripts

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def recorder_for(session_row_id: int | None):
    if not session_row_id or not config.CALL_TRANSCRIPT_ENABLED:
        return None

    def record(turn: int, user_text: str, bot_text: str, spoken: bool) -> None:
        _spawn(session_row_id, turn, user_text, bot_text, spoken)

    return record


def _spawn(session_row_id: int, turn: int, user_text: str, bot_text: str, spoken: bool) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    task = loop.create_task(
        asyncio.to_thread(_write, session_row_id, turn, user_text, bot_text, spoken)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _write(session_row_id: int, turn: int, user_text: str, bot_text: str, spoken: bool) -> None:
    lines = []
    if user_text:
        lines.append(("customer", user_text, True))
    if bot_text:
        lines.append(("bot", bot_text, spoken))

    call_transcripts.append_turn(session_id=session_row_id, turn=turn, lines=lines)
