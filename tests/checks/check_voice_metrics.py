import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pw_channel.channels.voice.metrics.latency import LatencyObserver
from pw_channel.channels.voice.processors.voice_engine import VoiceEngineProcessor
from pw_channel.channels.voice.brain import PWChatReply

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


def reply(tokens=None, recovered=None):
    diagnostics = {}
    if tokens:
        diagnostics["tokens"] = tokens
    if recovered:
        diagnostics["recovered"] = recovered
    return PWChatReply(
        response_text="ok", response_html="", result_id="", spoken_text="ok",
        handoff_main_menu=False, handoff_agent=False, latency_ms=10,
        diagnostics=diagnostics,
    )


async def main():
    print("\n1. the usage sink does not collide with pipecat's own metrics")
    engine = VoiceEngineProcessor(session_id="s", user_type="webvoice")
    engine._usage_sink = LatencyObserver(call_id="t")
    check(
        "pipecat's _metrics is untouched",
        type(engine._metrics).__name__ == "FrameProcessorMetrics",
        type(engine._metrics).__name__,
    )
    try:
        await engine.start_ttfb_metrics()
        await engine.stop_ttfb_metrics()
        check("start/stop_ttfb_metrics still work", True)
    except AttributeError as e:
        check("start/stop_ttfb_metrics still work", False, str(e))

    check("the engine reports metrics at all", engine.can_generate_metrics())

    print("\n2. tokens reach the observer, per turn and per call")
    observer = LatencyObserver(call_id="call-1")
    engine._usage_sink = observer
    observer._current = observer._new_turn(0.18)

    engine._note_usage(reply({"input": 4210, "output": 88, "cached": 3900}))
    check("turn input", observer._current["llm_prompt_tokens"] == 4210)
    check("turn cached", observer._current["llm_cached_prompt_tokens"] == 3900)
    check("turn output", observer._current["llm_completion_tokens"] == 88)

    published = []
    observer._on_turn = published.append
    observer._current["llm_ttft_s"] = 1.3
    observer._current["tts_ttfc_s"] = 0.15
    observer._close_current_turn()

    check("a finished turn publishes once", len(published) == 1)
    row = published[0] if published else {}
    check("row carries the breakdown", row.get("llmMs") == 1300.0, str(row.get("llmMs")))
    check("row carries the tokens", row.get("totalTokens") == 4298, str(row.get("totalTokens")))
    check("row carries running call totals", row.get("call", {}).get("promptTokens") == 4210)

    print("\n2b. a turn with no ASR timing still publishes (Deepgram Flux)")
    flux_published = []
    flux_observer = LatencyObserver(call_id="call-flux", on_turn=flux_published.append)
    flux_observer._current = flux_observer._new_turn(None)
    flux_observer._current["llm_ttft_s"] = 1.1
    flux_observer._current["tts_ttfc_s"] = 0.2
    flux_observer._close_current_turn()

    check("a Flux turn is not discarded", len(flux_published) == 1)
    flux_row = flux_published[0] if flux_published else {}
    check("the STT leg reports as unmeasured", flux_row.get("sttMs") is None,
          str(flux_row.get("sttMs")))
    check("the total is the legs that exist",
          round(flux_row.get("totalMs", 0)) == 1300, str(flux_row.get("totalMs")))

    print("\n2c. the silence Murf pads onto a line lands in the total")
    from pipecat.metrics.metrics import TTFAMetricsData

    silent_observer = LatencyObserver(call_id="call-silence")
    silent_observer._current = silent_observer._new_turn(None)
    silent_observer._current["llm_ttft_s"] = 1.5
    silent_observer._current["tts_ttfc_s"] = 0.2
    silent_observer._close_current_turn()
    check("tts_ttfc alone undercounts", round(silent_observer._turns[-1]["total_ms"]) == 1700)

    silent_observer._record_leading_silence(
        TTFAMetricsData(processor="MurfTTSService#0", ttfa=0.51, ttfb=0.2, leading_silence=0.31)
    )
    check("the dead air is counted", round(silent_observer._turns[-1]["total_ms"]) == 2010,
          str(silent_observer._turns[-1]["total_ms"]))
    check("and recorded on the turn", silent_observer._turns[-1]["tts_silence_s"] == 0.31)

    silent_observer._record_leading_silence(
        TTFAMetricsData(processor="MurfTTSService#0", ttfa=0.9, ttfb=0.2, leading_silence=0.7)
    )
    check("a second report does not double-count",
          round(silent_observer._turns[-1]["total_ms"]) == 2010)

    print("\n3. a turn publishes as soon as TTS starts, not a turn late")
    observer2 = LatencyObserver(call_id="call-2", on_turn=lambda t: published.append(t))
    observer2._current = observer2._new_turn(0.2)
    observer2._current["llm_ttft_s"] = 1.0
    before = len(published)
    observer2._current["tts_ttfc_s"] = 0.1
    observer2._close_current_turn()
    check("closing publishes immediately", len(published) == before + 1)

    print("\n4. a reply the chatbot recovered from still counts as degraded")
    engine2 = VoiceEngineProcessor(session_id="s2", user_type="callvoice")
    engine2._usage_sink = LatencyObserver(call_id="call-3")
    engine2._note_usage(reply({"input": 10, "output": 2, "cached": 0}, recovered="empty_reply"))
    check("usage is still recorded on a recovered turn",
          engine2._usage_sink._call_llm_prompt_tokens == 10)

    print("\n5. no usage means no crash")
    engine3 = VoiceEngineProcessor(session_id="s3", user_type="webvoice")
    engine3._note_usage(reply())
    check("a reply with no tokens is ignored", True)
    engine3._usage_sink = LatencyObserver(call_id="call-4")
    engine3._note_usage(reply())
    check("an empty token dict is ignored",
          engine3._usage_sink._call_llm_prompt_tokens == 0)

    print("\n6. the bot never speaks while the customer's turn is open")
    eng = VoiceEngineProcessor(session_id="sess-abc123456789", user_type="webvoice")
    spoken_lines = []

    async def fake_speak_reply(r, seq):
        if not eng._may_speak("reply", seq):
            return
        spoken_lines.append(r.spoken_text)

    eng._speak_reply = fake_speak_reply
    eng._on_actions = None
    eng._surface.results = lambda *a, **k: asyncio.sleep(0)
    eng._surface.empty = lambda *a, **k: asyncio.sleep(0)
    eng.stop_ttfb_metrics = lambda: asyncio.sleep(0)

    eng._set_user_speaking(True)
    eng._seq = 17
    eng._active_seq = 17
    fut = asyncio.get_running_loop().create_future()
    fut.set_result(reply({"input": 1, "output": 1, "cached": 0}))
    await eng._finish_turn(17, "तो", fut)

    check("the reply is withheld mid-sentence", not spoken_lines, str(spoken_lines))

    eng._set_user_speaking(False)
    eng._seq = 18
    eng._active_seq = 18
    fut2 = asyncio.get_running_loop().create_future()
    fut2.set_result(reply({"input": 1, "output": 1, "cached": 0}))
    await eng._finish_turn(18, "तो है, अब एक काम करो", fut2)
    check("the next turn speaks normally", spoken_lines == ["ok"], str(spoken_lines))

    print("\n7. a withheld turn does not fire its action")
    eng2 = VoiceEngineProcessor(session_id="s", user_type="callvoice")
    fired = []
    eng2._speak_reply = lambda r, s: asyncio.sleep(0)
    eng2._on_actions = lambda a, s: fired.append(a.type) or asyncio.sleep(0)
    eng2._surface.results = lambda *a, **k: asyncio.sleep(0)
    eng2._surface.empty = lambda *a, **k: asyncio.sleep(0)
    eng2.stop_ttfb_metrics = lambda: asyncio.sleep(0)

    from pw_channel.channels.voice.brain import VoiceAction
    action = VoiceAction(action_id="a1", type="transfer_to_agent", params={},
                         execute_after_speech=True, turn_id="t1")
    carrying = reply()
    object.__setattr__(carrying, "action", action)

    eng2._set_user_speaking(True)
    eng2._seq = 3
    eng2._active_seq = 3
    fut3 = asyncio.get_running_loop().create_future()
    fut3.set_result(carrying)
    await eng2._finish_turn(3, "transfer me", fut3)
    check("a transfer does not fire mid-sentence", not fired, str(fired))
    check("and it is acked back as dropped",
          eng2._pending_ack and eng2._pending_ack["status"] == "dropped",
          str(eng2._pending_ack))

    print("\n8. a stuck flag cannot mute the session forever")
    eng3 = VoiceEngineProcessor(session_id="s", user_type="webvoice")
    eng3._set_user_speaking(True)
    check("speech is withheld while they speak", not eng3._may_speak("x", 1))
    eng3._user_speaking_since = (
        asyncio.get_running_loop().time() - eng3._USER_SPEAKING_CEILING_SECS - 1
    )
    check("but a stale flag is released", eng3._may_speak("x", 1))
    check("and the flag is cleared", not eng3._user_speaking)

    print(f"\n{'=' * 58}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
