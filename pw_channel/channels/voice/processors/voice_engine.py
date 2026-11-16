import asyncio
import logging

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from pw_channel import config
from pw_channel.channels.voice import usecases
from pw_channel.channels.voice.processors import voice_lines
from pw_channel.channels.voice.processors.result_surface import NullResultSurface, ResultSurface
from pw_channel.channels.voice import brain as pw_chat

logger = logging.getLogger(__name__)

_SENTENCE_ENDS = ("।", ".", "!", "?")
_HOLD_COMPOSE_FLOOR_SECS = 0.5

_SILENT_TURN_KINDS = frozenset({"greeting", "recovery", "closing"})


class VoiceEngineProcessor(FrameProcessor):
    def __init__(
        self,
        *,
        session_id: str,
        user_type: str,
        context_provider=None,
        surface: ResultSurface | None = None,
        language_state=None,
        on_actions=None,
        usage_sink=None,
        transcript_sink=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._session_id = session_id
        self._user_type = user_type
        self._context_provider = context_provider
        self._surface = surface or NullResultSurface()
        self._language_state = language_state
        self._on_actions = on_actions
        self._usage_sink = usage_sink
        self.last_reply_text = ""
        self._transcript_sink = transcript_sink

        self._seq = 0
        self._active_seq = 0
        self._user_speaking = False
        self._sent_at_length = 0
        self._children: set[asyncio.Task] = set()
        self._background: set[asyncio.Task] = set()
        self._pool = voice_lines.LinePool()
        self._last_shown_seq = 0
        self._consecutive_failures = 0
        self._pending_ack: dict | None = None
        self._leaks = 0
        self._turns = 0
        self._chat_ms = 0

    def can_generate_metrics(self) -> bool:
        return True

    @property
    def language(self) -> str:
        current = getattr(self._language_state, "current", None)
        return current or config.BOT_LANGUAGE

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def note_leak(self) -> None:
        self._leaks += 1

    def set_action_ack(self, ack: dict | None) -> None:
        self._pending_ack = ack

    def _context(self) -> dict | None:
        if self._context_provider is None:
            return None
        try:
            return self._context_provider()
        except Exception:
            logger.exception("[voice_engine] could not build the call context")
            return None

    def _turn_id(self, seq: int) -> str:
        return f"t-{self._session_id[-12:]}-{seq:04d}"

    def _note_usage(self, reply) -> None:
        if self._usage_sink is None:
            return
        tokens = (getattr(reply, "diagnostics", None) or {}).get("tokens")
        if tokens:
            self._usage_sink.note_llm_usage(tokens)

    async def _chat(self, message: str, seq: int, kind: str, reason: str, prefix: str):
        ack = self._pending_ack
        self._pending_ack = None
        try:
            return await pw_chat.chat(
                session_id=self._session_id,
                message=message,
                user_type=self._user_type,
                turn_id=self._turn_id(seq),
                turn_kind=kind,
                turn_reason=reason,
                assistant_prefix=prefix,
                voice_context=self._context(),
                last_action_ack=ack,
                deadline_ms=int(pw_chat.read_timeout_for(self._user_type) * 1000),
            )
        except pw_chat.PWChatError as e:
            return e

    def _track(self, coro, name: str) -> asyncio.Task:
        task = self.create_task(coro, name=name)
        self._children.add(task)
        task.add_done_callback(self._children.discard)
        return task

    def _track_background(self, coro, name: str) -> asyncio.Task:
        task = self.create_task(coro, name=name)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def _settle(self, task: asyncio.Task) -> None:
        if not task.done():
            await self.cancel_task(task)
            return
        if not task.cancelled():
            task.exception()

    async def _drop_children(self) -> None:
        for task in list(self._children):
            await self._settle(task)
        self._children.clear()

    @staticmethod
    def _content_of(message: dict) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return " ".join(parts).strip()
        return ""

    @classmethod
    def _pending_user_text(cls, messages: list) -> str:
        parts: list[str] = []
        for message in reversed(messages):
            role = message.get("role")
            if role == "assistant":
                break
            if role != "user":
                continue
            text = cls._content_of(message)
            if text and not text.startswith("[SYSTEM"):
                parts.append(text)
        parts.reverse()
        return " ".join(parts).strip()

    _USER_SPEAKING_CEILING_SECS = 30.0

    def _user_speaking_stale(self) -> bool:
        if not self._user_speaking_since:
            return False
        elapsed = asyncio.get_running_loop().time() - self._user_speaking_since
        return elapsed > self._USER_SPEAKING_CEILING_SECS

    def _set_user_speaking(self, speaking: bool) -> None:
        self._user_speaking = speaking
        self._user_speaking_since = (
            asyncio.get_running_loop().time() if speaking else 0.0
        )

    def _may_speak(self, what: str, seq: int) -> bool:
        if not self._user_speaking:
            return True
        if self._user_speaking_stale():
            logger.warning(
                "[voice_engine] no UserStoppedSpeakingFrame arrived within "
                f"{self._USER_SPEAKING_CEILING_SECS}s — treating the turn as closed "
                "rather than going mute for the rest of the session"
            )
            self._user_speaking = False
            return True
        logger.info(
            f"[voice_engine] seq={seq} {what} withheld — the customer is still speaking"
        )
        return False

    async def _speak(self, text: str, seq: int = 0) -> None:
        if not text:
            return
        if not self._may_speak("line", seq):
            return
        self._pool.remember(text)
        await self.push_frame(
            TTSSpeakFrame(text=text, append_to_context=False), FrameDirection.DOWNSTREAM
        )

    async def speak_line(self, text: str) -> None:
        await self._speak(text)

    @staticmethod
    def _sentence_count(text: str) -> int:
        return sum(1 for char in text if char in _SENTENCE_ENDS) or 1

    async def _speak_reply(self, reply: pw_chat.PWChatReply, seq: int) -> None:
        text = reply.spoken_text
        if not text:
            logger.warning(f"[voice_engine] seq={seq} had nothing to speak")
            return
        if not self._may_speak("reply", seq):
            return

        sentences = self._sentence_count(text)
        if len(text) > config.VOICE_REPLY_WARN_CHARS:
            logger.warning(
                f"[voice_engine] reply seq={seq} is {len(text)}chars over "
                f"VOICE_REPLY_WARN_CHARS={config.VOICE_REPLY_WARN_CHARS} - the chatbot's "
                "voice output policy may have regressed"
            )
        logger.info(
            f"[voice_engine] reply seq={seq} spoken={len(text)}chars sentences={sentences} "
            f"actions={reply.action.type if reply.action else 'none'}"
        )

        self.last_reply_text = text
        await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
        await self.stop_ttfb_metrics()
        await self.push_frame(LLMTextFrame(text=text), FrameDirection.DOWNSTREAM)
        await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

    async def request_turn(
        self, message: str, *, kind: str = "user", reason: str = "", prefix: str = ""
    ) -> None:
        await self._run_turn(message, kind=kind, reason=reason, prefix=prefix)

    async def _run_turn(
        self, user_text: str, *, kind: str = "user", reason: str = "", prefix: str = ""
    ) -> None:
        self._seq += 1
        seq = self._seq
        self._active_seq = seq
        self._turns += 1
        logger.info(
            f"[voice_engine] turn seq={seq} kind={kind} sending {user_text[:200]!r}"
        )
        await self.start_ttfb_metrics()

        chat_task = self._track_background(
            self._chat(user_text, seq, kind, reason, prefix), f"voice_chat_seq{seq}"
        )
        self._track_background(
            self._finish_turn(seq, user_text, chat_task, kind), f"voice_finish_seq{seq}"
        )

    def _record_transcript(self, seq: int, user_text: str, bot_text: str, spoken: bool) -> None:
        if self._transcript_sink is None:
            return
        try:
            self._transcript_sink(seq, user_text, bot_text, spoken)
        except Exception:
            logger.exception("[voice_engine] could not record the transcript turn")

    async def _finish_turn(
        self, seq: int, user_text: str, chat_task: asyncio.Task, kind: str = "user"
    ) -> None:
        reply = await chat_task

        if kind in _SILENT_TURN_KINDS:
            if kind == "greeting" and isinstance(reply, pw_chat.PWChatReply) and reply.spoken_text.strip():
                self._record_transcript(seq, "", reply.spoken_text.strip(), True)
            if isinstance(reply, pw_chat.PWChatReply):
                logger.info(
                    f"[voice_engine] seq={seq} kind={kind} recorded with the chatbot — "
                    f"reply discarded, not spoken ({len(reply.spoken_text)}chars)"
                )
            else:
                logger.warning(f"[voice_engine] seq={seq} kind={kind} seed failed: {reply}")
            if self._active_seq == seq:
                self._active_seq = 0
            await self.stop_ttfb_metrics()
            return

        if seq < self._last_shown_seq:
            logger.info(
                f"[voice_engine] seq={seq} superseded by a newer result already shown — "
                "dropped in silence rather than delivered out of order"
            )
            if isinstance(reply, pw_chat.PWChatReply) and reply.action is not None:
                await self._ack_dropped(reply.action, "turn_superseded")
            return
        self._last_shown_seq = seq

        if not isinstance(reply, pw_chat.PWChatReply):
            await self._handle_failure(seq, reply)
            return

        recovered = (reply.diagnostics or {}).get("recovered")
        if recovered:
            self._consecutive_failures += 1
            logger.warning(
                f"[voice_engine] seq={seq} chatbot recovered from {recovered!r} "
                f"({self._consecutive_failures} degraded turns in a row)"
            )
            if (
                self._active_seq == seq
                and self._consecutive_failures >= config.PW_CHAT_MAX_CONSECUTIVE_FAILURES
            ):
                self._active_seq = 0
                await self.stop_ttfb_metrics()
                await self._close_for_brain_failure(seq, "returning empty replies")
                return
        else:
            self._consecutive_failures = 0
        self._chat_ms += reply.latency_ms
        self._note_usage(reply)

        spoken = self._active_seq == seq and not self._user_speaking
        self._record_transcript(seq, user_text, reply.spoken_text, spoken)
        if spoken or seq >= self._seq:
            await self._surface.results(
                seq,
                reply.response_html,
                user_text,
                spoken=spoken,
                result_id=reply.result_id,
            )
        else:
            logger.info(
                f"[voice_engine] seq={seq} results not shown — turn {self._seq} is already "
                "answering the same question"
            )
            await self._surface.empty(seq)

        if reply.handoff_agent or reply.handoff_main_menu:
            await self._surface.handoff(
                seq, agent=reply.handoff_agent, main_menu=reply.handoff_main_menu
            )

        action = reply.action
        if action is None and reply.handoff_agent and usecases.is_phone(self._user_type):
            action = pw_chat.VoiceAction(
                action_id=f"{self._turn_id(seq)}:transfer_to_agent",
                type="transfer_to_agent",
                params={"reason": "handoffToCustomerAgent"},
                execute_after_speech=True,
                turn_id=self._turn_id(seq),
            )
            logger.info(
                f"[voice_engine] seq={seq} handoffToCustomerAgent treated as a transfer request"
            )

        if not spoken:
            await self.stop_ttfb_metrics()
            if action is not None:
                logger.info(
                    f"[voice_engine] seq={seq} abandoned — action {action.action_id!r} "
                    "dropped with the turn, never executed"
                )
                await self._ack_dropped(action, "turn_abandoned")
            return

        self._active_seq = 0

        if action is not None and not action.execute_after_speech:
            await self._dispatch(action, seq)

        await self._speak_reply(reply, seq)

        if action is not None and action.execute_after_speech:
            await self._dispatch(action, seq)

    async def _dispatch(self, action, seq: int) -> None:
        if self._on_actions is None:
            logger.warning(
                f"[voice_engine] no action executor wired — {action.type} ignored on seq={seq}"
            )
            return
        try:
            await self._on_actions(action, seq)
        except Exception:
            logger.exception(f"[voice_engine] action {action.action_id!r} failed")

    async def _ack_dropped(self, action, detail: str) -> None:
        self._pending_ack = {
            "action_id": action.action_id,
            "type": action.type,
            "status": "dropped",
            "detail": detail,
        }

    async def _handle_failure(self, seq: int, reply) -> None:
        reason = str(reply) if reply is not None else "the chatbot call did not complete"
        self._consecutive_failures += 1
        logger.warning(
            f"[voice_engine] turn seq={seq} failed ({self._consecutive_failures} in a row): "
            f"{reason}"
        )
        if self._active_seq == seq or seq >= self._seq:
            await self._surface.error(seq, reason)
        else:
            await self._surface.empty(seq)

        if self._active_seq != seq:
            await self.stop_ttfb_metrics()
            return

        self._active_seq = 0
        await self.stop_ttfb_metrics()

        language = self.language
        if self._consecutive_failures >= config.PW_CHAT_MAX_CONSECUTIVE_FAILURES:
            await self._close_for_brain_failure(seq, "unavailable")
            return

        pool = voice_lines.FAILURE_LINES[voice_lines.language_key(language)]
        await self._speak(self._pool.pick(pool))

    async def _close_for_brain_failure(self, seq: int, detail: str) -> None:
        logger.error(
            f"[voice_engine] {self._consecutive_failures} bad turns in a row "
            f"({detail}) — closing the call with a static line"
        )
        await self._speak(voice_lines.closing_line(self.language))
        if self._on_actions is None:
            return
        await self._dispatch(
            pw_chat.VoiceAction(
                action_id=f"{self._turn_id(seq)}:end_call",
                type="end_call",
                params={
                    "reason": "brain_unavailable",
                    "disposition": {
                        "outcome": "other",
                        "notes": f"chatbot {detail} for consecutive turns",
                    },
                },
                execute_after_speech=True,
                turn_id=self._turn_id(seq),
            ),
            seq,
        )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            self._set_user_speaking(True)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._set_user_speaking(False)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterruptionFrame):
            self._set_user_speaking(True)
            if self._active_seq:
                logger.info(
                    f"[voice_engine] seq={self._active_seq} abandoned — customer spoke over it"
                )
                await self._surface.empty(self._active_seq)
                self._active_seq = 0
            await self._drop_children()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMContextFrame):
            messages = frame.context.get_messages()
            if len(messages) <= self._sent_at_length:
                logger.debug("[voice_engine] context frame with nothing new — ignored")
                return

            newest = next(
                (self._content_of(m) for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            user_text = "" if newest.startswith("[SYSTEM") else self._pending_user_text(messages)
            if not user_text:
                logger.info("[voice_engine] nothing from the customer to send — turn skipped")
                self._sent_at_length = len(messages)
                return
            self._sent_at_length = len(messages)
            await self._run_turn(user_text)
            return

        await self.push_frame(frame, direction)

    async def cleanup(self):
        if self._leaks:
            logger.warning(
                f"[voice_engine] {self._leaks} leaked-text guardrail hits on this session — "
                "the chatbot may be emitting tool syntax or stage notes"
            )
        if self._turns:
            logger.info(
                f"[voice_engine] session done turns={self._turns} "
                f"avg_chat_ms={self._chat_ms // self._turns}"
            )
        await self._drop_children()
        for task in list(self._background):
            await self._settle(task)
        self._background.clear()
        await super().cleanup()
