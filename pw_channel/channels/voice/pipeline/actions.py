import asyncio
import logging

from pipecat.frames.frames import EndTaskFrame
from pipecat.processors.frame_processor import FrameDirection

from pw_channel import config
from pw_channel.db import call_sessions
from pw_channel.channels.voice.processors import voice_lines
from pw_channel.channels.voice.tts.factory import apply_tts_locale
from pw_channel.channels.voice.schema import CallDisposition
from pw_channel.channels.voice.telephony import lifecycle as call_lifecycle
from pw_channel.channels.voice.calls.logger import log_call_disposition
from pw_channel.channels.voice.telephony import registry as telephony
from pw_channel.channels.voice.telephony.base import CallRef, TelephonyError

logger = logging.getLogger(__name__)

_END_CALL_DRAIN_CAP_SECS = 8.0
_CHARS_PER_SEC = 11.0
_MAX_LINE_WAIT_SECS = 15.0

_detached: set[asyncio.Task] = set()


def _live_identifiers(transfer) -> dict[str, str]:
    ids = {"ref_id": transfer.ref_id, "call_id": transfer.call_id, "call_uuid": ""}
    row = call_sessions.by_id(transfer.session_row_id) if transfer.session_row_id else None
    if not row:
        return ids
    return {
        "ref_id": row.get("ref_id") or ids["ref_id"],
        "call_id": row.get("current_call_id") or ids["call_id"],
        "call_uuid": row.get("current_uuid") or "",
    }


class VoiceActionExecutor:
    def __init__(
        self,
        *,
        engine,
        gate,
        session,
        call_context,
        task_ref: dict,
        tts=None,
        transfer=None,
    ):
        self._engine = engine
        self._gate = gate
        self._session = session
        self._call_context = call_context
        self._task_ref = task_ref
        self._tts = tts
        self._transfer = transfer

        self._executed: dict = {}
        self._terminal_done = False
        self._last_action_turn = 0
        self._lock = asyncio.Lock()

    @property
    def capabilities(self) -> list:
        available = ["end_call", "log_disposition"]
        if self._transfer is not None:
            available.insert(0, "transfer_to_agent")
        if config.ENABLE_LANGUAGE_SWITCH and self._tts is not None:
            available.append("switch_language")
        available.append("send_booking_link")
        return available

    def _is_call_live(self) -> bool:
        return not self._session.call_ended_event.is_set()

    async def __call__(self, action, seq: int) -> None:
        async with self._lock:
            await self._run(action, seq)

    async def _run(self, action, seq: int) -> None:
        if not config.PW_CHAT_ACTIONS_ENABLED:
            logger.warning(
                f"[voice.action.disabled] {action.action_id!r} type={action.type} — "
                "PW_CHAT_ACTIONS_ENABLED is off"
            )
            return

        previous = self._executed.get(action.action_id)
        if previous is not None:
            logger.info(
                f"[voice.action.duplicate] {action.action_id!r} first_outcome={previous}"
            )
            self._ack(action, previous)
            return

        if self._terminal_done:
            logger.warning(
                f"[voice.action.dropped] {action.action_id!r} reason=terminal_latched"
            )
            self._ack(action, "dropped", "terminal_latched")
            return

        if not self._is_call_live():
            logger.warning(f"[voice.action.dropped] {action.action_id!r} reason=call_ended")
            self._ack(action, "dropped", "call_ended")
            return

        if seq < self._last_action_turn:
            logger.warning(
                f"[voice.action.dropped] {action.action_id!r} reason=stale_turn "
                f"seq={seq} last={self._last_action_turn}"
            )
            self._ack(action, "dropped", "stale_turn")
            return

        if action.type not in self.capabilities:
            logger.error(
                f"[voice.action.dropped] {action.action_id!r} reason=not_capable "
                f"type={action.type} available={self.capabilities} — the chatbot offered "
                "something this call cannot do"
            )
            self._ack(action, "dropped", "not_capable")
            return

        handler = getattr(self, f"_do_{action.type}", None)
        if handler is None:
            logger.warning(f"[voice.action.unknown] type={action.type}")
            self._ack(action, "dropped", "unknown_type")
            return

        self._last_action_turn = seq
        await handler(action, seq)

    def _ack(self, action, status: str, detail: str = None) -> None:
        self._engine.set_action_ack(
            {
                "action_id": action.action_id,
                "type": action.type,
                "status": status,
                "detail": detail,
            }
        )

    def _line_wait(self, floor: float) -> float:
        text = getattr(self._engine, "last_reply_text", "") or ""
        return min(_MAX_LINE_WAIT_SECS, max(floor, len(text) / _CHARS_PER_SEC + 1.5))

    async def _await_speech(self, action, cap: float) -> bool:
        snapshot_gen = self._gate.generation
        snapshot_int = self._gate.interrupts
        logger.info(
            f"[voice.action.received] {action.action_id!r} execute_after_speech=True — "
            f"waiting up to {cap}s for the line to finish"
        )
        drained = await self._gate.wait_for_drain(snapshot_gen, cap)
        interrupted = self._gate.interrupts > snapshot_int
        if interrupted:
            logger.info(f"[voice.action.received] {action.action_id!r} — customer barged in")
        return not interrupted if drained else False

    async def _do_switch_language(self, action, seq: int) -> None:
        language = str(action.params.get("language", "")).strip().lower()
        state = self._session.language_state

        if not state.is_supported(language):
            logger.warning(
                f"[voice.action.failed] {action.action_id!r} unsupported language {language!r}"
            )
            self._executed[action.action_id] = "failed"
            self._ack(action, "failed", "unsupported_language")
            return

        if not state.set(language):
            logger.info(
                f"[voice.action.executed] {action.action_id!r} — already speaking {language}"
            )
            self._executed[action.action_id] = "executed"
            self._ack(action, "executed", "already_active")
            return

        applied = apply_tts_locale(self._tts, state.locale) if self._tts is not None else False
        logger.info(
            f"[voice.action.executed] {action.action_id!r} language={language} "
            f"locale={state.locale} tts_applied={applied}"
        )
        self._executed[action.action_id] = "executed"
        self._ack(action, "executed")

    async def _do_log_disposition(self, action, seq: int) -> None:
        outcome = str(action.params.get("outcome", "other"))
        notes = str(action.params.get("notes", ""))
        await self._record_disposition(outcome, notes)
        self._session.wrap_up_started_event.set()
        self._session.disposition_logged.set()
        logger.info(f"[voice.action.executed] {action.action_id!r} outcome={outcome}")
        self._executed[action.action_id] = "executed"
        self._ack(action, "executed")

    async def _do_send_booking_link(self, action, seq: int) -> None:
        logger.info(
            f"[voice.action.executed] {action.action_id!r} — booking link already sent by "
            f"the tool to {action.params.get('phone_number', '')}"
        )
        self._executed[action.action_id] = "executed"
        self._ack(action, "executed")

    async def _do_transfer_to_agent(self, action, seq: int) -> None:
        transfer = self._transfer
        reason = str(action.params.get("reason", ""))

        if transfer.transferred:
            logger.warning(
                f"[voice.action.dropped] {action.action_id!r} reason=already_transferred"
            )
            self._ack(action, "dropped", "already_transferred")
            return

        await self._await_speech(action, self._line_wait(config.CALL_TRANSFER_HOLD_SECS))

        if not self._is_call_live():
            logger.warning(
                f"[voice.action.dropped] {action.action_id!r} reason=call_ended_while_speaking"
            )
            self._ack(action, "dropped", "call_ended")
            return

        ids = _live_identifiers(transfer)
        logger.info(
            f"[voice.action.executing] {action.action_id!r} type=transfer_to_agent "
            f"reason={reason!r} destination={transfer.destination} "
            f"ref_id={ids['ref_id']!r} call_id={ids['call_id']!r} uuid={ids['call_uuid']!r} "
            f"(snapshot was call_id={transfer.call_id!r})"
        )

        call_lifecycle.transfer_started(
            transfer.session_row_id, destination=transfer.destination
        )

        provider = telephony.for_call(self._session.call_context.channel)
        if provider is None or not provider.supports_transfer:
            self._ack(action, "failed", "this call's provider cannot transfer")
            await self._engine.speak_line(voice_lines.transfer_failed_line(self._session.language_state.current))
            return
        call = asyncio.ensure_future(provider.transfer(CallRef(**ids), transfer.destination))
        try:
            result = await asyncio.shield(call)
        except asyncio.CancelledError:
            self._detach_transfer(call, transfer, action.action_id)
            raise
        except (TelephonyError, ValueError) as e:
            logger.error(f"[voice.action.failed] {action.action_id!r} transfer FAILED: {e}")
            call_lifecycle.transfer_failed(transfer.session_row_id, error=str(e))
            self._executed[action.action_id] = "failed"
            self._ack(action, "failed", str(e))
            await self._engine.speak_line(
                voice_lines.transfer_failed_line(self._session.language_state.current)
            )
            return

        transfer.transferred = True
        call_lifecycle.transfer_succeeded(
            transfer.session_row_id, destination=transfer.destination
        )
        if transfer.on_transferred:
            transfer.on_transferred()

        self._session.call_ended_event.set()
        self._terminal_done = True
        self._executed[action.action_id] = "executed"

        logger.info(
            f"[voice.action.executed] {action.action_id!r} TRANSFERRED "
            f"via {result['identifier']}={result['value']} to intercom={result['intercom']} "
            f"terminal=true — the customer is now with customer care, the bot leg is done"
        )
        self._ack(action, "executed")

    def _detach_transfer(self, call, transfer, action_id: str) -> None:
        _detached.add(call)
        call.add_done_callback(_detached.discard)
        call.add_done_callback(
            lambda done: self._record_detached_transfer(done, transfer, action_id)
        )
        logger.warning(
            f"[voice.action.detached] {action_id!r} the bot leg closed while Acefone "
            "was still answering — waiting for the result off-pipeline"
        )

    @staticmethod
    def _record_detached_transfer(call, transfer, action_id: str) -> None:
        if call.cancelled():
            logger.error(
                f"[voice.action.failed] {action_id!r} transfer cancelled before "
                "Acefone answered — outcome unknown"
            )
            return

        error = call.exception()
        if error is not None:
            logger.error(
                f"[voice.action.failed] {action_id!r} transfer FAILED after the "
                f"bot leg closed: {error}"
            )
            call_lifecycle.transfer_failed(transfer.session_row_id, error=str(error))
            return

        result = call.result()
        transfer.transferred = True
        call_lifecycle.transfer_succeeded(
            transfer.session_row_id, destination=transfer.destination
        )
        logger.info(
            f"[voice.action.executed] {action_id!r} TRANSFERRED "
            f"via {result['identifier']}={result['value']} to intercom={result['intercom']} "
            "— confirmed after the bot leg had already closed"
        )

    async def _do_end_call(self, action, seq: int) -> None:
        reason = str(action.params.get("reason", "call completed"))
        disposition = action.params.get("disposition")

        if isinstance(disposition, dict):
            await self._record_disposition(
                str(disposition.get("outcome", "other")), str(disposition.get("notes", ""))
            )
            self._session.disposition_logged.set()

        self._session.wrap_up_started_event.set()

        finished = await self._await_speech(action, self._line_wait(_END_CALL_DRAIN_CAP_SECS))
        if not finished:
            logger.info(
                f"[voice.action.dropped] {action.action_id!r} reason=customer_spoke_over_goodbye "
                "— the end-of-call watchdog will close this call once they go quiet"
            )
            self._ack(action, "dropped", "barge_in")
            return

        task = self._task_ref.get("task")
        if task is None:
            logger.error(f"[voice.action.failed] {action.action_id!r} no pipeline task to end")
            self._executed[action.action_id] = "failed"
            self._ack(action, "failed", "no_task")
            return

        self._session.call_ended_event.set()
        self._terminal_done = True
        self._executed[action.action_id] = "executed"

        logger.info(
            f"[voice.action.executed] {action.action_id!r} END_CALL reason={reason!r} "
            "terminal=true"
        )
        self._ack(action, "executed")
        await task.queue_frame(EndTaskFrame(reason=reason), FrameDirection.UPSTREAM)

    async def _record_disposition(self, outcome: str, notes: str) -> None:
        context = self._call_context
        try:
            await log_call_disposition(
                CallDisposition(
                    call_id=context.reference_id or "unknown",
                    channel=context.channel or "unknown",
                    reference_id=context.booking_reference_id or None,
                    phone_no=context.phone_number or None,
                    status=outcome,
                    ended_reason=notes or None,
                )
            )
            logger.info(f"[disposition] recorded outcome={outcome} notes={notes!r}")
        except Exception:
            logger.exception("[disposition] failed to record disposition")
