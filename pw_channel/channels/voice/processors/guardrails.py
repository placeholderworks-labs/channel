import logging
import re

from pipecat.frames.frames import AggregatedTextFrame, Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)


LEAKED_TOOL_CALL_RULE = re.compile(
    r"\[\s*(?:[a-zA-Z_]+\s*[:=]\s*)?[a-zA-Z]+_[a-zA-Z0-9_]*\s*(\(.*?\))?\s*\]",
    re.DOTALL,
)

_VOICE_TOOL_NAMES = (
    r"voice_cart_details|voice_apply_discount|voice_offer_booking_link"
    r"|voice_share_booking_link|voice_log_disposition|voice_end_call"
    r"|voice_switch_language|voice_transfer_to_agent|voice_record_lead|pw_knowledge_base"
)

LEAKED_TOOL_NAME_RULE = re.compile(
    r"(?:\[|\b)(?:call|tool|tool_call|function|calls|invoke)\s*[:=]\s*"
    r"(?:" + _VOICE_TOOL_NAMES + r")\b",
    re.IGNORECASE,
)

LEAKED_JSON_ARGS_RULE = re.compile(
    r"\{\s*\"[a-zA-Z_][a-zA-Z0-9_]*\"\s*:.*?\}", re.DOTALL
)

LEAKED_STAGE_NOTE_RULE = re.compile(
    r"\[\s*[a-zA-Z_]+(?:\s+[a-zA-Z_]+){1,}\s*\]"
    r"|\(\s*[a-zA-Z_]+(?:\s+[a-zA-Z_]+){1,}\s*\)"
    r"|<[a-zA-Z][a-zA-Z0-9_-]*(?:[\s-][a-zA-Z0-9_-]+)*>"
)

UNFILLED_PLACEHOLDER_RULE = re.compile(r"\{\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\}")

LEAKED_REASONING_RULE = re.compile(
    r"\b(?:the assistant|the system (?:says|expects|wants)"
    r"|the final (?:answer|output|turn)"
    r"|spoken (?:text|line)|closing_line_spoken"
    r"|according to (?:the )?guidelines|the guidelines"
    r"|the tool call|the tool\b)"
    r"|\b(?:" + _VOICE_TOOL_NAMES + r")\b",
    re.IGNORECASE,
)

GUARDRAIL_RULES = [
    LEAKED_TOOL_CALL_RULE,
    LEAKED_TOOL_NAME_RULE,
    LEAKED_JSON_ARGS_RULE,
    LEAKED_STAGE_NOTE_RULE,
    LEAKED_REASONING_RULE,
    UNFILLED_PLACEHOLDER_RULE,
]


TOOL_CALL_LEAK_RULES = [
    LEAKED_TOOL_CALL_RULE,
    LEAKED_TOOL_NAME_RULE,
    LEAKED_JSON_ARGS_RULE,
]


INVISIBLE_CHAR_RULE = re.compile(
    "[​‌‍⁠﻿­᠎]"
)

RFC3339_TIMESTAMP_RULE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"
)


SPEAKABLE_CHAR_RULE = re.compile(r"\w", re.UNICODE)

CURRENCY_SYMBOL_RULE = re.compile(r"\s*(?:₹|\bRs\.?|\bINR\b|\$)\s*")

def _spell_digits_for_hindi(text: str) -> str:
    from pw_channel import config

    if config.BOT_LANGUAGE != "hindi" or not any(ch.isdigit() for ch in text):
        return text

    from pw_channel.channels.voice.text.hindi_numbers import spell_out_digits

    return spell_out_digits(text)


class SpokenTextSanitizer(FrameProcessor):

    def __init__(self, *, on_sanitized=None, **kwargs):
        super().__init__(**kwargs)
        self._on_sanitized = on_sanitized

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, AggregatedTextFrame) and frame.text:
            cleaned = INVISIBLE_CHAR_RULE.sub("", frame.text)
            cleaned = RFC3339_TIMESTAMP_RULE.sub("", cleaned)
            cleaned = CURRENCY_SYMBOL_RULE.sub(" ", cleaned).strip()
            cleaned = _spell_digits_for_hindi(cleaned)
            if cleaned != frame.text:
                original = frame.text
                frame.text = cleaned
                if self._on_sanitized is not None:
                    await self._on_sanitized(original, cleaned)

            if not SPEAKABLE_CHAR_RULE.search(frame.text):
                frame.skip_tts = True

        await self.push_frame(frame, direction)


_SENTENCE_END = re.compile(r"(?<=[।.!?])\s+")
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def drop_placeholder_clauses(text: str) -> str:
    kept = []
    for sentence in _SENTENCE_END.split(text or ""):
        if not UNFILLED_PLACEHOLDER_RULE.search(sentence):
            kept.append(sentence)
            continue
        clauses = [c for c in re.split(r"\s*,\s*", sentence) if c and not UNFILLED_PLACEHOLDER_RULE.search(c)]
        joined = ", ".join(clauses).strip()
        if joined:
            if joined[-1] not in "।.!?":
                joined += "।" if _DEVANAGARI.search(joined) else "."
            kept.append(joined)
    out = " ".join(k for k in kept if k).strip()
    return out if SPEAKABLE_CHAR_RULE.search(out) else ""


class GuardrailFilter(FrameProcessor):

    def __init__(self, *, rules=None, on_leaked_text=None, banned_phrases=(), **kwargs):
        super().__init__(**kwargs)
        self._rules = list(rules if rules is not None else GUARDRAIL_RULES)
        if banned_phrases:
            self._rules.append(
                re.compile("|".join(re.escape(p) for p in banned_phrases), re.IGNORECASE)
            )
        self._on_leaked_text = on_leaked_text

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if (
            isinstance(frame, AggregatedTextFrame)
            and UNFILLED_PLACEHOLDER_RULE.search(frame.text)
            and not any(rule.search(frame.text) for rule in self._rules if rule is not UNFILLED_PLACEHOLDER_RULE)
        ):
            trimmed = drop_placeholder_clauses(frame.text)
            if trimmed:
                logger.warning(f"[guardrail] unfilled placeholder dropped, rest spoken: {frame.text!r} -> {trimmed!r}")
                frame.text = trimmed

        if isinstance(frame, AggregatedTextFrame) and any(
            rule.search(frame.text) for rule in self._rules
        ):
            frame.skip_tts = True
            if self._on_leaked_text is not None:
                looks_like_tool_call = any(
                    rule.search(frame.text) for rule in TOOL_CALL_LEAK_RULES
                )
                await self._on_leaked_text(frame.text, looks_like_tool_call)

        await self.push_frame(frame, direction)
