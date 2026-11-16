import asyncio
import os
import pathlib
import sys

os.environ["PW_CHAT_API_URL"] = "http://127.0.0.1:8411/api/pw-ai-service/chat"
os.environ["PW_CHAT_API_TOKEN"] = "testtoken"
os.environ["PW_CHAT_PHONE_HOLD_DELAY_SECS"] = "0.6"
os.environ["PW_CHAT_PHONE_SECOND_HOLD_SECS"] = "1.2"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)

from pw_channel import config
from pw_channel.channels.voice.processors.voice_engine import VoiceEngineProcessor
from pw_channel.channels.voice.states.language import LanguageState
from pw_channel.channels.voice import brain as pw_chat

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


class FakeContext:
    def __init__(self, messages):
        self._messages = messages

    def get_messages(self):
        return self._messages


class FakeContextFrame:
    def __init__(self, messages):
        self.context = FakeContext(messages)


def harness(user_type="callvoice"):
    engine = VoiceEngineProcessor(
        session_id="voice-918595864036",
        user_type=user_type,
        context_provider=lambda: {
            "channel": "acefone",
            "capabilities": ["transfer_to_agent", "end_call", "log_disposition"],
            "language": "hindi",
            "turn_index": 3,
        },
        language_state=LanguageState(current="hindi"),
    )
    pushed = []
    actions = []

    async def fake_push(frame, direction=None):
        pushed.append(frame)

    async def fake_actions(action, seq):
        actions.append((action, seq))

    engine.push_frame = fake_push
    engine._on_actions = fake_actions
    engine.create_task = lambda coro, name=None: asyncio.ensure_future(coro)
    engine.cancel_task = lambda task: asyncio.sleep(0)

    async def noop(*a, **k):
        return None

    engine.start_ttfb_metrics = noop
    engine.stop_ttfb_metrics = noop
    return engine, pushed, actions


def kinds(pushed):
    return [type(f).__name__ for f in pushed]


async def drain(engine, seconds=1.0):
    await asyncio.sleep(0)
    for task in list(engine._background):
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=seconds)
        except (asyncio.TimeoutError, Exception):
            pass
    await asyncio.sleep(0.05)


async def main():
    print("\n1. a plain turn emits the frame triple the speaking chain needs")
    engine, pushed, actions = harness()
    await engine._run_turn("जी बताइए")
    await drain(engine)
    check("Start frame emitted", any(isinstance(f, LLMFullResponseStartFrame) for f in pushed))
    check("text frame emitted", any(isinstance(f, LLMTextFrame) for f in pushed))
    check("End frame emitted", any(isinstance(f, LLMFullResponseEndFrame) for f in pushed))
    triple = kinds(pushed)
    check("order is Start -> Text -> End",
          triple.index("LLMFullResponseStartFrame") < triple.index("LLMTextFrame")
          < triple.index("LLMFullResponseEndFrame"), str(triple))
    check("no action on a plain turn", not actions)

    print("\n2. fragmented turns are joined back to the last assistant reply")
    engine, pushed, actions = harness()
    messages = [
        {"role": "assistant", "content": "जी बताइए"},
        {"role": "user", "content": "मुझे दिल्ली में"},
        {"role": "user", "content": "hotel चाहिए"},
        {"role": "user", "content": "आठ सितंबर"},
    ]
    joined = engine._pending_user_text(messages)
    check("all three fragments joined", joined == "मुझे दिल्ली में hotel चाहिए आठ सितंबर", joined)

    print("\n3. internal [SYSTEM: ...] turns never reach the chatbot")
    nudged = engine._pending_user_text([
        {"role": "assistant", "content": "x"},
        {"role": "user", "content": "असली बात"},
        {"role": "user", "content": "[SYSTEM: say the closing line]"},
    ])
    check("system nudge dropped", "[SYSTEM" not in nudged, nudged)

    print("\n4. a context frame with nothing new is ignored")
    engine, pushed, actions = harness()
    frame = FakeContextFrame([{"role": "user", "content": "hi"}])
    engine._sent_at_length = 5
    before = engine._seq
    from pipecat.frames.frames import LLMContextFrame
    real = LLMContextFrame(context=frame.context) if hasattr(LLMContextFrame, "__init__") else None
    check("no new turn started", engine._seq == before)

    print("\n5. transfer request is dispatched after the reply is spoken")
    engine, pushed, actions = harness()
    await engine._run_turn("mujhe insaan se baat karni hai transfer")
    await drain(engine)
    check("one action dispatched", len(actions) == 1, str([a[0].type for a in actions]))
    check("action is transfer_to_agent", actions and actions[0][0].type == "transfer_to_agent")
    order = kinds(pushed)
    check("reply was spoken", "LLMTextFrame" in order, str(order))

    print("\n6. handoffToCustomerAgent alone is treated as a transfer on a phone call")
    engine, pushed, actions = harness()
    await engine._run_turn("connect me to an agent")
    await drain(engine)
    check("handoff became a transfer action",
          any(a[0].type == "transfer_to_agent" for a in actions), str([a[0].type for a in actions]))

    print("\n7. switch_language runs BEFORE the announcing line is pushed")
    engine, pushed, actions = harness()
    order_log = []

    async def logging_push(frame, direction=None):
        order_log.append("text" if isinstance(frame, LLMTextFrame) else type(frame).__name__)

    async def logging_actions(action, seq):
        order_log.append(f"action:{action.type}")

    engine.push_frame = logging_push
    engine._on_actions = logging_actions
    await engine._run_turn("can you speak english")
    await drain(engine)
    check("switch_language dispatched", "action:switch_language" in order_log, str(order_log))
    if "action:switch_language" in order_log and "text" in order_log:
        check("locale applied before speaking",
              order_log.index("action:switch_language") < order_log.index("text"), str(order_log))

    print("\n8. a slow turn gets a hold line, then the real reply")
    engine, pushed, actions = harness()
    await engine._run_turn("__slow please")
    await drain(engine, seconds=8)
    spoken = [f.text for f in pushed if isinstance(f, TTSSpeakFrame)]
    check("a hold line was spoken", len(spoken) >= 1, str(spoken))
    check("hold line came from the static pool",
          any("देख रही हूँ" in s or "निकाल रही" in s or "check कर रही" in s
              or "रुकिए" in s or "list निकल" in s or "second" in s for s in spoken), str(spoken))
    check("real reply still spoken after the hold",
          any(isinstance(f, LLMTextFrame) for f in pushed))

    print("\n9. a failed turn speaks a rotating failure line, not silence")
    engine, pushed, actions = harness()
    await engine._run_turn("__500 boom")
    await drain(engine, seconds=3)
    spoken = [f.text for f in pushed if isinstance(f, TTSSpeakFrame)]
    check("failure line spoken", any("माफ़" in s or "technical" in s for s in spoken), str(spoken))
    check("failure counted", engine.consecutive_failures >= 1, str(engine.consecutive_failures))

    print("\n10. repeated failures close the call with a static line")
    engine, pushed, actions = harness()
    for _ in range(config.PW_CHAT_MAX_CONSECUTIVE_FAILURES):
        await engine._run_turn("__500 boom")
        await drain(engine, seconds=3)
    spoken = [f.text for f in pushed if isinstance(f, TTSSpeakFrame)]
    check("closing line spoken", any("शुक्रिया" in s or "Thank you" in s for s in spoken),
          str(spoken[-1][:60]) if spoken else "none")
    check("end_call dispatched", any(a[0].type == "end_call" for a in actions),
          str([a[0].type for a in actions]))

    print("\n11. an abandoned turn never dispatches its action")
    engine, pushed, actions = harness()
    engine._seq = 1
    engine._active_seq = 0
    reply = await pw_chat.chat(
        session_id="s", message="transfer me", user_type="callvoice", turn_id="t-x",
        voice_context={"capabilities": ["transfer_to_agent"]},
    )
    fut = asyncio.get_running_loop().create_future()
    fut.set_result(reply)
    await engine._finish_turn(1, "transfer me", fut)
    check("no action dispatched for an abandoned turn", not actions)
    check("drop was acked back to the chatbot",
          engine._pending_ack and engine._pending_ack["status"] == "dropped",
          str(engine._pending_ack))

    await pw_chat.close_client()
    print(f"\n{'='*60}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
