import json
import logging

from fastapi.websockets import WebSocketState
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from pw_channel import config
from pw_channel.channels.voice.processors.devanagari import to_devanagari
from pw_channel.channels.voice.processors.guardrails import GUARDRAIL_RULES, INVISIBLE_CHAR_RULE

logger = logging.getLogger(__name__)


class TranscriptRelayProcessor(FrameProcessor):
    def __init__(
        self,
        websocket,
        *,
        relay_user: bool = True,
        relay_bot: bool = True,
        relay_text: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._websocket = websocket
        self._relay_user = relay_user
        self._relay_bot = relay_bot
        self._relay_text = relay_text
        self._turn = 0
        self._turn_open = False
        self._turn_had_text = False
        self._turn_buffer = ""
        self._pending = ""
        self._devanagari = config.BOT_LANGUAGE == "hindi"

    def _display(self, text: str) -> str:
        return to_devanagari(text) if self._devanagari else text

    def _pending_delta(self, text: str) -> str:
        if not self._devanagari:
            return text

        buffered = self._pending + text
        split = len(buffered)
        while split > 0 and buffered[split - 1].isascii() and buffered[split - 1].isalpha():
            split -= 1

        self._pending = buffered[split:]
        return self._display(buffered[:split])

    def _flush_pending(self) -> str:
        text = self._display(self._pending)
        self._pending = ""
        return text

    async def _send(self, payload: dict) -> None:
        if self._websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await self._websocket.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"[website] transcript relay send failed: {e.__class__.__name__} ({e})")

    async def _close_turn(self) -> None:
        if self._turn_open and self._turn_had_text:
            tail = self._flush_pending()
            if tail:
                await self._send(
                    {"type": "bot_delta", "turn": self._turn, "text": tail}
                )
            await self._send({"type": "bot_final", "turn": self._turn})
        self._turn_open = False
        self._turn_had_text = False
        self._turn_buffer = ""
        self._pending = ""

    def _leaks(self) -> bool:
        return any(rule.search(self._turn_buffer) for rule in GUARDRAIL_RULES)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if self._relay_user:
            if not self._relay_text and isinstance(
                frame, (InterimTranscriptionFrame, TranscriptionFrame)
            ):
                pass
            elif isinstance(frame, InterimTranscriptionFrame):
                if frame.text.strip():
                    await self._send(
                        {"type": "user_interim", "text": self._display(frame.text)}
                    )
            elif isinstance(frame, TranscriptionFrame):
                if frame.text.strip():
                    await self._send(
                        {"type": "user_final", "text": self._display(frame.text)}
                    )
            elif isinstance(frame, UserStartedSpeakingFrame):
                await self._send({"type": "user_started_speaking"})
            elif isinstance(frame, UserStoppedSpeakingFrame):
                await self._send({"type": "user_stopped_speaking"})

        if self._relay_bot:
            if not self._relay_text and isinstance(
                frame,
                (
                    LLMFullResponseStartFrame,
                    LLMFullResponseEndFrame,
                    LLMTextFrame,
                    TTSSpeakFrame,
                ),
            ):
                pass
            elif isinstance(frame, LLMFullResponseStartFrame):
                self._turn += 1
                self._turn_open = True
                self._turn_had_text = False
            elif isinstance(frame, LLMTextFrame):
                if self._turn_open and frame.text:
                    was_clean = not self._leaks()
                    self._turn_buffer += frame.text
                    if was_clean and self._leaks():
                        await self._send({"type": "bot_retract", "turn": self._turn})
                        self._turn_had_text = False
                    elif was_clean:
                        text = INVISIBLE_CHAR_RULE.sub("", frame.text)
                        if text:
                            self._turn_had_text = True
                            await self._send(
                                {
                                    "type": "bot_delta",
                                    "turn": self._turn,
                                    "text": self._pending_delta(text),
                                }
                            )
            elif isinstance(frame, TTSSpeakFrame):
                if frame.text.strip():
                    await self._close_turn()
                    self._turn += 1
                    await self._send(
                        {
                            "type": "bot_delta",
                            "turn": self._turn,
                            "text": self._display(frame.text),
                        }
                    )
                    await self._send({"type": "bot_final", "turn": self._turn})

            elif isinstance(frame, LLMFullResponseEndFrame):
                await self._close_turn()
            elif isinstance(frame, InterruptionFrame):
                await self._close_turn()
                await self._send({"type": "interruption"})
            elif isinstance(frame, BotStartedSpeakingFrame):
                await self._send({"type": "bot_started_speaking"})
            elif isinstance(frame, BotStoppedSpeakingFrame):
                await self._send({"type": "bot_stopped_speaking"})

        await self.push_frame(frame, direction)
