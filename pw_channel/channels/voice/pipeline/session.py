import asyncio
import logging

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.vad_analyzer import VADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_start import ExternalUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from pw_channel import config
from pw_channel.channels.voice.prompts.loader import load_greeting_line, tts_profile
from pw_channel.channels.voice.states.call_context import CallContext
from pw_channel.channels.voice.states.call_transfer import TransferHandle
from pw_channel.channels.voice.states.language import LanguageState
from pw_channel.core import records
from pw_sdk.contracts.runtime import RuntimeContext
from pw_channel.channels.voice import usecases

logger = logging.getLogger(__name__)

_SHORT_LANGUAGES = {"hi": "hindi", "en": "english"}

def _full_language(value: str) -> str:
    key = (value or "").strip().lower()
    key = _SHORT_LANGUAGES.get(key, key)
    return key if key in config.LANGUAGES else config.BOT_LANGUAGE


def _user_aggregator_params(vad_analyzer: VADAnalyzer | None) -> LLMUserAggregatorParams:
    if vad_analyzer is None:
        return LLMUserAggregatorParams(
            user_turn_stop_timeout=config.USER_TURN_STOP_TIMEOUT_SECS,
            user_idle_timeout=config.USER_IDLE_TIMEOUT_SECS,
            user_turn_strategies=UserTurnStrategies(
                start=[ExternalUserTurnStartStrategy()],
                stop=[
                    ExternalUserTurnStopStrategy(
                        timeout=config.FLUX_TURN_AGGREGATION_MS / 1000
                    )
                ],
            ),
        )

    return LLMUserAggregatorParams(
        vad_analyzer=vad_analyzer,
        user_turn_stop_timeout=config.USER_TURN_STOP_TIMEOUT_SECS,
        user_idle_timeout=config.USER_IDLE_TIMEOUT_SECS,
        user_turn_strategies=UserTurnStrategies(
            start=[
                MinWordsUserTurnStartStrategy(
                    min_words=config.MIN_WORDS_TO_INTERRUPT
                )
            ],
            stop=[
                TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=LocalSmartTurnAnalyzerV3(
                        params=SmartTurnParams(
                            stop_secs=config.SMART_TURN_STOP_SECS,
                            pre_speech_ms=config.SMART_TURN_PRE_SPEECH_MS,
                            max_duration_secs=config.SMART_TURN_MAX_DURATION_SECS,
                        ),
                    )
                )
            ]
        ),
    )


class CallSession:
    def __init__(
        self,
        call_context: CallContext,
        vad_analyzer: VADAnalyzer | None,
        *,
        user_type: str,
        tts=None,
        transfer: TransferHandle | None = None,
        max_call_duration_secs: int | None = None,
    ):
        self.call_context = call_context
        self.user_type = user_type
        self.transfer = transfer
        self.max_call_duration_secs = max_call_duration_secs

        self.call_ended_event = asyncio.Event()
        self.wrap_up_started_event = asyncio.Event()
        self.force_close_event = asyncio.Event()
        self.disposition_logged = asyncio.Event()
        self.wrap_up_reason = ""
        self.language_state = LanguageState(current=_full_language(call_context.language))

        self.turn_index = 0
        self.started_at = 0.0
        self.capabilities: list = []

        self.cart = self._resolve_cart()

        self.context = LLMContext(messages=[])
        self.context_aggregator = LLMContextAggregatorPair(
            self.context, user_params=_user_aggregator_params(vad_analyzer)
        )

    def _resolve_cart(self):
        if not usecases.is_phone(self.user_type) and not self.call_context.booking_reference_id:
            return None
        target = records.get(
            reference_id=self.call_context.booking_reference_id,
            phone_number=self.call_context.phone_number,
        )
        if target is None:
            logger.warning(
                f"[session] no record found for reference_id={self.call_context.booking_reference_id!r} "
                f"phone={self.call_context.phone_number!r}"
            )
            return None
        if not self.call_context.customer_name and target.customer_name:
            self.call_context.customer_name = target.customer_name
        if not self.call_context.booking_reference_id:
            self.call_context.booking_reference_id = target.reference_id
        if not self.call_context.phone_number and target.phone_number:
            self.call_context.phone_number = target.phone_number
        if not self.call_context.cart_summary:
            self.call_context.cart_summary = target.summary
        if target.has_details():
            logger.info(f"[session] matched record {target.reference_id} with {len(target.facts)} fact(s)")
        else:
            logger.warning(f"[session] record {target.reference_id} carries no cart, summary or facts")
        return target

    def note_user_turn(self) -> None:
        self.turn_index += 1

    def seconds_remaining(self) -> int | None:
        if not self.max_call_duration_secs or not self.started_at:
            return None
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self.started_at
        return max(0, int(self.max_call_duration_secs - elapsed))

    def chat_context(self) -> dict:
        context = self.call_context
        fields = self.cart.runtime_fields() if self.cart is not None else {}
        runtime = RuntimeContext(**{
            **fields,
            "channel": context.channel,
            "call_id": self.transfer.call_id if self.transfer else context.reference_id,
            "call_ref": self.transfer.ref_id if self.transfer else "",
            "customer_name": context.customer_name or fields.get("customer_name", ""),
            "phone_number": context.phone_number or fields.get("phone_number", ""),
            "reference_id": context.booking_reference_id or fields.get("reference_id", ""),
            "cart_summary": context.cart_summary or fields.get("cart_summary", ""),
            "language": self.language_state.current,
            "tts_profile": tts_profile(usecases.tts_overrides(self.user_type).get("provider", "")),
            "is_phone_call": usecases.is_phone(self.user_type) and context.channel != "website",
            "max_call_duration_secs": self.max_call_duration_secs,
            "seconds_remaining": self.seconds_remaining(),
            "turn_index": self.turn_index,
            "wrap_up_reason": self.wrap_up_reason,
            "capabilities": list(self.capabilities),
        })
        return runtime.model_dump(mode="json")

    def user_aggregator(self):
        return self.context_aggregator.user()

    def assistant_aggregator(self):
        return self.context_aggregator.assistant()

    def opening_line_frame(self):
        cart = self._resolve_cart()
        greeting = load_greeting_line(
            self.user_type,
            customer_name=self.call_context.customer_name or "",
            language=self.language_state.current,
            facts=getattr(cart, "facts", None) or [],
            cart_summary=self.call_context.cart_summary or "",
            channel=self.call_context.channel or "",
        )
        if greeting:
            logger.info(f"[session] greeting spoken from template ({len(greeting)} chars): {greeting!r}")
            return TTSSpeakFrame(text=greeting)

        logger.warning(
            "[session] no greeting template resolved — the chatbot will be asked for the "
            "opening line instead"
        )
        return None
