import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass

from pipecat.frames.frames import (
    AggregatedTextFrame,
    EndTaskFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_text_processor import LLMTextProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_transport import BaseTransport

from pw_channel import config
from pw_channel.channels.voice.audio.ambience_mixer import AmbienceMixerProcessor
from pw_channel.channels.voice.audio.output_gain import OutputGainProcessor
from pw_channel.channels.voice.metrics.latency import LatencyObserver
from pw_channel.channels.voice.pipeline.actions import VoiceActionExecutor
from pw_channel.channels.voice.pipeline.session import CallSession
from pw_channel.channels.voice.processors import voice_lines
from pw_channel.channels.voice.processors.action_gate import ActionGateProcessor
from pw_channel.channels.voice.processors.guardrails import GuardrailFilter, SpokenTextSanitizer
from pw_channel.channels.voice.processors.result_surface import ResultSurface
from pw_channel.channels.voice.processors.audio_rechunker import AudioRechunkerProcessor
from pw_channel.channels.voice.processors.stt_connect_gate import STTConnectGateProcessor
from pw_channel.channels.voice.processors.voice_engine import VoiceEngineProcessor
from pw_channel.channels.voice.stt.factory import (
    build_stt_service,
    resolve_stt_params,
    uses_external_turns,
)
from pw_channel.channels.voice.tts.factory import build_tts_service
from pw_channel.channels.voice.vad.factory import build_vad_analyzer
from pw_channel.channels.voice import usecases
from pw_channel.channels.voice.calls import transcripts as transcript_recorder

logger = logging.getLogger(__name__)


@dataclass
class _RepromptState:

    consecutive: int = 0
    pending: bool = False


_PUNCT_RULE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RULE = re.compile(r"\s+")


def _normalize_spoken(text: str) -> str:
    return _WHITESPACE_RULE.sub(" ", _PUNCT_RULE.sub("", text)).strip().lower()


_DUPLICATE_OVERLAP_THRESHOLD = 0.85


def _is_near_duplicate(current: str, previous: str) -> bool:
    if not current or not previous:
        return False
    if current == previous:
        return True
    current_words = set(current.split())
    previous_words = set(previous.split())
    if len(current_words) < 4 or len(previous_words) < 4:
        return False
    shared = len(current_words & previous_words)
    return shared / max(len(current_words), len(previous_words)) >= _DUPLICATE_OVERLAP_THRESHOLD


_SIGNOFF_RULE = re.compile(
    r"दिन शुभ हो|यात्रा शुभ हो|trip शुभ हो|शुभ दिन|"
    r"have a (?:great|good|nice) (?:day|trip|journey)|"
    r"safe travels|enjoy your trip",
    re.IGNORECASE,
)


class _DuplicateSpeechFilter(FrameProcessor):

    _RECENT_WINDOW = 6

    def __init__(self, *, on_duplicate=None, **kwargs):
        super().__init__(**kwargs)
        self._on_duplicate = on_duplicate
        self._recent: deque[str] = deque(maxlen=self._RECENT_WINDOW)
        self._signoff_spoken = False
        self._reply_first = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._reply_first = True
        elif isinstance(frame, LLMFullResponseEndFrame):
            self._reply_first = False

        if isinstance(frame, AggregatedTextFrame) and not getattr(frame, "skip_tts", False):
            normalized = _normalize_spoken(frame.text)
            first = self._reply_first
            self._reply_first = False
            if normalized:
                is_signoff = bool(_SIGNOFF_RULE.search(frame.text))
                if not first and any(_is_near_duplicate(normalized, seen) for seen in self._recent):
                    frame.skip_tts = True
                    if self._on_duplicate is not None:
                        await self._on_duplicate(frame.text)
                elif is_signoff and self._signoff_spoken:
                    frame.skip_tts = True
                    if self._on_duplicate is not None:
                        await self._on_duplicate(frame.text)
                else:
                    if is_signoff:
                        self._signoff_spoken = True
                    self._recent.append(normalized)

        await self.push_frame(frame, direction)


def _file_call_metrics(observer, call_context, session_row_id, usecase, tts_overrides, stt_params) -> None:
    from pw_channel.db import call_sessions
    from pw_channel.db import call_records

    overrides = tts_overrides or {}
    provider = str(overrides.get("provider") or config.TTS_PROVIDER).lower()
    from pw_channel.channels.voice.tts.factory import provider as tts_provider

    default_voice = tts_provider(provider).default_voice()
    llm = (usecase or {}).get("llm") or {}
    providers = {
        "stt": {"provider": stt_params.get("provider"), "model": stt_params.get("model")},
        "llm": {"provider": llm.get("provider") or "default", "model": llm.get("model") or ""},
        "tts": {"provider": provider, "voice": overrides.get("voice") or default_voice},
        "channel": call_context.channel,
        "agent": (usecase or {}).get("slug", ""),
    }
    try:
        call_records.record_metrics(
            metrics=observer.snapshot(providers),
            session_row_id=session_row_id,
            reference_id=call_context.reference_id or "",
        )
    except Exception:
        logger.exception("[metrics] could not file the call metrics")

async def _run_call_duration_timer(
    task: PipelineTask, session: CallSession, engine: VoiceEngineProcessor, channel: str
) -> None:
    warning_at = max(config.MAX_CALL_DURATION_SECS - config.CALL_WRAP_UP_WARNING_SECS, 0)

    await asyncio.sleep(warning_at)
    logger.info(f"[{channel}] call approaching time limit, asking the brain to wrap up")
    session.wrap_up_reason = "time_limit"
    session.wrap_up_started_event.set()
    session.force_close_event.set()
    try:
        await engine.request_turn(
            "", kind="wrap_up", reason="time_limit"
        )
    except Exception:
        logger.exception(f"[{channel}] wrap-up turn failed, closing on the hard limit only")

    await asyncio.sleep(config.MAX_CALL_DURATION_SECS - warning_at)
    logger.info(f"[{channel}] call reached hard time limit, ending call")
    await task.queue_frame(EndTaskFrame(reason="max call duration reached"), FrameDirection.UPSTREAM)


async def _run_call_end_watchdog(
    task: PipelineTask, session: CallSession, channel: str, activity: asyncio.Event
) -> None:
    await session.wrap_up_started_event.wait()

    while True:
        activity.clear()
        done, _ = await asyncio.wait(
            [
                asyncio.create_task(session.call_ended_event.wait()),
                asyncio.create_task(activity.wait()),
            ],
            timeout=config.CALL_END_WATCHDOG_SECS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in done:
            t.cancel()

        if session.call_ended_event.is_set():
            return

        if activity.is_set():
            logger.info(
                f"[{channel}] customer still talking after wrap-up — end-call "
                f"grace period restarted"
            )
            continue

        logger.warning(
            f"[{channel}] the call did not end within "
            f"{config.CALL_END_WATCHDOG_SECS}s of the customer falling silent — "
            "forcing call end"
        )
        await task.queue_frame(
            EndTaskFrame(reason="end-of-call watchdog timeout"), FrameDirection.UPSTREAM
        )
        return


async def run_voice_pipeline(
    transport: BaseTransport,
    call_context,
    *,
    audio_in_sample_rate: int,
    audio_out_sample_rate: int,
    user_type: str,
    chat_session_id: str,
    surface: ResultSurface | None = None,
    post_stt_processors: list[FrameProcessor] | None = None,
    post_llm_processors: list[FrameProcessor] | None = None,
    enforce_max_duration: bool = True,
    auto_end_session: bool = True,
    transfer=None,
    tts_overrides: dict | None = None,
    session_row_id: int | None = None,
) -> None:

    usecase = await usecases.fetch(user_type)
    own_line = usecases.transfer_number(user_type)
    if transfer is not None and own_line and own_line != transfer.destination:
        logger.info(f"[{call_context.channel}] agent {user_type!r} transfers to its own line {own_line}")
        transfer.destination = own_line
        from pw_channel.db import call_sessions

        call_sessions.update(session_row_id, did=own_line)
    if usecase is not None:
        tts_overrides = {**usecases.tts_overrides(user_type), **(tts_overrides or {})} or None
        call_context.language = usecases.default_language(user_type) or call_context.language
        logger.info(
            f"[{call_context.channel}] use case {user_type!r} v{usecase.get('version')} "
            f"({usecase.get('status')}) — {usecase.get('name')}"
        )
    else:
        logger.info(f"[{call_context.channel}] {user_type!r} is not a Studio use case — pipeline defaults")

    stt = build_stt_service(call_context.channel)
    stt_params = resolve_stt_params(call_context.channel)
    external_turns = uses_external_turns(call_context.channel)
    tts = build_tts_service(tts_overrides)
    vad_analyzer = None if external_turns else build_vad_analyzer(call_context.channel)

    session = CallSession(
        call_context=call_context,
        vad_analyzer=vad_analyzer,
        user_type=user_type,
        tts=tts,
        transfer=transfer,
        max_call_duration_secs=(
            (usecases.max_call_duration(user_type) or config.MAX_CALL_DURATION_SECS)
            if enforce_max_duration
            else None
        ),
    )

    task_ref: dict = {}
    action_gate = ActionGateProcessor()

    engine = VoiceEngineProcessor(
        session_id=chat_session_id,
        user_type=user_type,
        context_provider=session.chat_context,
        surface=surface,
        language_state=session.language_state,
        transcript_sink=transcript_recorder.recorder_for(session_row_id),
    )

    executor = VoiceActionExecutor(
        engine=engine,
        gate=action_gate,
        session=session,
        call_context=call_context,
        task_ref=task_ref,
        tts=tts,
        transfer=transfer,
    )
    engine._on_actions = executor
    session.capabilities = executor.capabilities

    logger.info(
        f"[{call_context.channel}] brain=pw-llm-layer user_type={user_type} "
        f"session={chat_session_id} capabilities={session.capabilities}"
    )
    if transfer is not None:
        logger.info(
            f"[{call_context.channel}] call transfer armed -> {transfer.destination} "
            f"(call_id={transfer.call_id!r} ref_id={transfer.ref_id!r})"
        )

    async def _on_sanitized_text(original: str, cleaned: str) -> None:
        logger.warning(
            f"[{call_context.channel}] stripped invisible/stray characters before TTS: "
            f"{original!r} -> {cleaned!r}"
        )

    async def _on_leaked_text(leaked_text: str, _looks_like_tool_call: bool) -> None:
        engine.note_leak()
        logger.warning(f"[{call_context.channel}] leaked text muted: {leaked_text!r}")

    async def _on_duplicate_speech(text: str) -> None:
        logger.warning(
            f"[{call_context.channel}] suppressed duplicate line before TTS: {text!r}"
        )
        _rollback_reprompt("line suppressed as a duplicate")

    user_aggregator = session.user_aggregator()

    stt_ready_event = getattr(stt, "_connection_ready", None)
    stt_gate = STTConnectGateProcessor(stt_ready_event) if stt_ready_event is not None else None

    rechunker = (
        AudioRechunkerProcessor(target_ms=config.FLUX_INPUT_CHUNK_MS)
        if external_turns and config.FLUX_INPUT_CHUNK_MS
        else None
    )

    pipeline_steps = [
        transport.input(),
        *([rechunker] if rechunker is not None else []),
        *([stt_gate] if stt_gate is not None else []),
        stt,
        *(post_stt_processors or []),
        user_aggregator,
        engine,
        action_gate,
        *(post_llm_processors or []),
    ]

    pipeline_steps += [
        LLMTextProcessor(),
        SpokenTextSanitizer(on_sanitized=_on_sanitized_text),
        GuardrailFilter(
            on_leaked_text=_on_leaked_text,
            banned_phrases=usecases.banned_phrases(user_type),
        ),
        _DuplicateSpeechFilter(on_duplicate=_on_duplicate_speech),
        tts,
    ]

    if config.BOT_OUTPUT_GAIN_DB:
        pipeline_steps.append(
            OutputGainProcessor(gain_db=config.BOT_OUTPUT_GAIN_DB)
        )
    if config.ENABLE_BACKGROUND_AMBIENCE:
        pipeline_steps.append(
            AmbienceMixerProcessor(level_db=config.BACKGROUND_AMBIENCE_LEVEL_DB)
        )
    pipeline_steps += [
        transport.output(),
        session.assistant_aggregator(),
    ]

    pipeline = Pipeline(pipeline_steps)

    latency_observer = LatencyObserver(
        call_id=call_context.reference_id or "unknown",
        user_aggregator=user_aggregator,
        engine=engine,
        on_turn=surface.latency if surface is not None else None,
        stt_provider=stt_params["provider"],
        stt_model=stt_params["model"],
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=audio_in_sample_rate,
            audio_out_sample_rate=audio_out_sample_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[latency_observer],
    )
    engine._usage_sink = latency_observer
    task_ref["task"] = task

    duration_timer_task = None
    customer_activity = asyncio.Event()
    watchdog_task = (
        asyncio.create_task(
            _run_call_end_watchdog(task, session, call_context.channel, customer_activity)
        )
        if auto_end_session
        else None
    )
    if watchdog_task is None:
        logger.info(
            f"[{call_context.channel}] no end-of-session watchdog on this channel — "
            "the session ends when the client hangs up or disconnects"
        )

    reprompt_state = _RepromptState()

    async def _maybe_reprompt(reason: str, kind: str) -> None:
        if session.wrap_up_started_event.is_set() or session.call_ended_event.is_set():
            return
        if getattr(engine, "_user_speaking", False):
            logger.info(f"[{call_context.channel}] {reason} — customer is still speaking, no re-prompt")
            return
        if not auto_end_session:
            logger.info(
                f"[{call_context.channel}] {reason} — leaving the session open, no nudge "
                "(the visitor may simply be reading the results on screen)"
            )
            return
        reprompt_state.consecutive += 1
        if reprompt_state.consecutive > config.MAX_CONSECUTIVE_REPROMPTS:
            logger.info(
                f"[{call_context.channel}] {reason} again "
                f"({reprompt_state.consecutive}) — customer has gone, closing "
                "the call"
            )
            reprompt_state.pending = False
            session.wrap_up_reason = "no_response"
            session.wrap_up_started_event.set()
            session.force_close_event.set()
            await task.queue_frames(
                [
                    TTSSpeakFrame(
                        text=voice_lines.closing_line(session.language_state.current),
                        append_to_context=False,
                    )
                ]
            )
            return
        logger.info(
            f"[{call_context.channel}] {reason} — re-prompting "
            f"({reprompt_state.consecutive}/{config.MAX_CONSECUTIVE_REPROMPTS}, "
            f"variant={kind})"
        )
        reprompt_state.pending = True
        line = voice_lines.reprompt_line(
            kind, reprompt_state.consecutive, session.language_state.current
        )
        await task.queue_frames(
            [TTSSpeakFrame(text=line, append_to_context=False)]
        )

    def _rollback_reprompt(cause: str) -> None:
        if not reprompt_state.pending:
            return
        reprompt_state.pending = False
        if reprompt_state.consecutive > 0:
            reprompt_state.consecutive -= 1
        logger.info(
            f"[{call_context.channel}] re-prompt never reached the customer "
            f"({cause}) — attempt returned, now at {reprompt_state.consecutive}"
        )

    @user_aggregator.event_handler("on_user_turn_started")
    async def on_user_turn_started(_aggregator, _strategy):
        customer_activity.set()

    @user_aggregator.event_handler("on_user_turn_stop_timeout")
    async def on_user_turn_stop_timeout(_aggregator):
        await _maybe_reprompt(
            f"user turn produced no transcript within "
            f"{config.USER_TURN_STOP_TIMEOUT_SECS}s",
            "no_transcript",
        )

    @user_aggregator.event_handler("on_user_turn_idle")
    async def on_user_turn_idle(_aggregator):
        await _maybe_reprompt(
            f"customer silent for {config.USER_IDLE_TIMEOUT_SECS}s after the bot "
            "finished speaking",
            "idle",
        )

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(_aggregator, strategy, _params):
        if strategy is not None:
            reprompt_state.consecutive = 0
            reprompt_state.pending = False
            customer_activity.set()
            session.note_user_turn()

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        nonlocal duration_timer_task
        logger.info(f"[{call_context.channel}] client connected, triggering greeting")
        latency_observer.mark_call_started()
        session.started_at = asyncio.get_running_loop().time()

        greeting_frame = session.opening_line_frame()
        if greeting_frame is not None:
            await task.queue_frames([greeting_frame])
            await engine.request_turn(
                "",
                kind="greeting",
                reason="connected",
                prefix=greeting_frame.text,
            )
        else:
            await engine.request_turn("", kind="user", reason="connected")

        if enforce_max_duration:
            duration_timer_task = asyncio.create_task(
                _run_call_duration_timer(task, session, engine, call_context.channel)
            )
        else:
            logger.info(
                f"[{call_context.channel}] no max-duration timer on this channel — "
                "the session ends when the client hangs up or disconnects"
            )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info(f"[{call_context.channel}] client disconnected, ending call")
        await task.cancel()

    @task.event_handler("on_pipeline_error")
    async def on_pipeline_error(_task, frame):
        if frame.fatal:
            return
        logger.warning(f"[{call_context.channel}] recovering from pipeline error: {frame.error}")

    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()
        if duration_timer_task is not None:
            duration_timer_task.cancel()

    latency_observer.log_call_latency()
    await asyncio.to_thread(
        _file_call_metrics, latency_observer, call_context, session_row_id, usecase, tts_overrides, stt_params
    )
    from pw_channel.channels.voice import post_call

    asyncio.create_task(post_call.send_minutes(
        chat_session_id=chat_session_id, user_type=user_type, call_context=call_context,
        user_turns=session.turn_index,
    ))
