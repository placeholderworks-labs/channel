import asyncio
import os
import pathlib
import sys

os.environ["PW_CHAT_API_URL"] = "http://127.0.0.1:8411/api/pw-ai-service/chat"
os.environ["PW_CHAT_API_TOKEN"] = "testtoken"
os.environ["ENABLE_CALL_TRANSFER"] = "true"
os.environ["CALL_TRANSFER_NUMBER"] = "01143131313"
os.environ["ACEFONE_AUTH_TOKEN"] = "dummy"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pw_channel import config
from pw_channel.channels.voice.pipeline.actions import VoiceActionExecutor
from pw_channel.channels.voice.states.call_context import CallContext
from pw_channel.channels.voice.states.call_transfer import TransferHandle
from pw_channel.channels.voice.states.language import LanguageState
from pw_channel.channels.voice import brain as pw_chat

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


class FakeSession:
    def __init__(self):
        self.call_ended_event = asyncio.Event()
        self.wrap_up_started_event = asyncio.Event()
        self.force_close_event = asyncio.Event()
        self.disposition_logged = asyncio.Event()
        self.language_state = LanguageState(current="hindi")


class FakeEngine:
    def __init__(self):
        self.acks = []
        self.spoken = []
        self.name = "FakeEngine#0"

    def set_action_ack(self, ack):
        self.acks.append(ack)

    async def speak_line(self, text):
        self.spoken.append(text)


class FakeTask:
    def __init__(self):
        self.frames = []

    async def queue_frame(self, frame, direction=None):
        self.frames.append(frame)


class FakeGate:

    def __init__(self, *, interrupt=False, drain=True):
        self.generation = 0
        self.interrupts = 0
        self._interrupt = interrupt
        self._drain = drain

    async def wait_for_drain(self, snapshot, timeout):
        self.generation += 1
        if self._interrupt:
            self.interrupts += 1
        return self._drain


def build(*, transfer=True, gate=None, session=None):
    session = session or FakeSession()
    engine = FakeEngine()
    task = FakeTask()
    handle = (
        TransferHandle(
            call_id="1788861971.645032",
            ref_id="af-9c1e2b",
            destination="01143131313",
            on_transferred=lambda: transferred_flag.append(True),
        )
        if transfer
        else None
    )
    executor = VoiceActionExecutor(
        engine=engine,
        gate=gate or FakeGate(),
        session=session,
        call_context=CallContext(
            reference_id="SRV-1", booking_reference_id="CART-77123",
            phone_number="918595864036", channel="acefone", language="hi",
        ),
        task_ref={"task": task},
        tts=None,
        transfer=handle,
    )
    return executor, engine, task, session, handle


transferred_flag = []


async def main():
    print("\n1. pw_chat parses a real reply from the mock chatbot")
    reply = await pw_chat.chat(
        session_id="voice-918595864036",
        message="mujhe insaan se baat karni hai transfer",
        user_type="callvoice",
        turn_id="t-abc-0004",
        voice_context={"channel": "acefone", "capabilities": ["transfer_to_agent", "end_call"]},
    )
    check("action parsed", reply.action is not None)
    check("action type", reply.action and reply.action.type == "transfer_to_agent")
    check("action_id deterministic", reply.action and reply.action.action_id == "t-abc-0004:transfer_to_agent")
    check("spoken text non-empty", bool(reply.spoken_text))
    check("diagnostics carried", reply.diagnostics.get("llm_calls") == 1)

    print("\n2. unknown action type is dropped, not executed")
    weird = await pw_chat.chat(
        session_id="s", message="__weird", user_type="callvoice", turn_id="t-1",
        voice_context={"capabilities": []},
    )
    check("unknown action ignored", weird.action is None)

    print("\n3. tagged reply still yields speakable text (rollback path)")
    tagged = await pw_chat.chat(
        session_id="s", message="__tagged", user_type="callvoice", turn_id="t-2",
        voice_context={"capabilities": []},
    )
    check("FRIENDLY_TEXT extracted", "options" in tagged.spoken_text)
    check("no angle brackets left", "<" not in tagged.spoken_text, repr(tagged.spoken_text[:60]))

    print("\n4. blank response_text is treated as a failure")
    try:
        await pw_chat.chat(session_id="s", message="__blank", user_type="callvoice",
                            turn_id="t-3", voice_context={})
        check("blank rejected", False)
    except pw_chat.PWChatError as e:
        check("blank rejected", True, str(e))

    print("\n5. capabilities gate: transfer refused when the channel cannot")
    executor, engine, task, session, _ = build(transfer=False)
    act = pw_chat.VoiceAction(action_id="a1", type="transfer_to_agent", params={}, turn_id="t")
    await executor(act, 1)
    check("not_capable dropped", engine.acks[-1]["status"] == "dropped")
    check("reason is not_capable", engine.acks[-1]["detail"] == "not_capable")

    print("\n6. transfer executes after speech, then latches terminal")
    import pw_channel.channels.voice.pipeline.actions as actions_mod
    calls = []

    async def fake_transfer(*, call_id="", ref_id="", call_uuid="", destination):
        calls.append({
            "call_id": call_id, "ref_id": ref_id,
            "call_uuid": call_uuid, "intercom": destination,
        })
        return {"identifier": "ref_id", "value": ref_id, "intercom": destination}

    original = actions_mod.transfer_acefone_call
    actions_mod.transfer_acefone_call = fake_transfer
    try:
        executor, engine, task, session, handle = build()
        await executor(pw_chat.VoiceAction(action_id="a2", type="transfer_to_agent",
                                            params={"reason": "asked"}, turn_id="t"), 4)
        check("acefone called once", len(calls) == 1, str(calls))
        check("used call_id from the handle", calls and calls[0]["call_id"] == "1788861971.645032")
        check("ref_id from the handle too", calls and calls[0]["ref_id"] == "af-9c1e2b")
        check("destination from config, not the chatbot", calls and calls[0]["intercom"] == "01143131313")
        check("handle marked transferred", handle.transferred is True)
        check("on_transferred fired", bool(transferred_flag))
        check("call_ended_event set", session.call_ended_event.is_set())
        check("no EndTaskFrame pushed", len(task.frames) == 0, "customer belongs to customer care now")
        check("acked executed", engine.acks[-1]["status"] == "executed")

        print("\n7. a second terminal action is latched out")
        await executor(pw_chat.VoiceAction(action_id="a3", type="end_call", params={}, turn_id="t"), 5)
        check("end_call dropped after transfer", engine.acks[-1]["detail"] == "terminal_latched")

        print("\n8. duplicate action_id executes once (retry safety)")
        executor, engine, task, session, handle = build()
        calls.clear()
        dup = pw_chat.VoiceAction(action_id="same-id", type="transfer_to_agent", params={}, turn_id="t")
        await executor(dup, 4)
        await executor(dup, 4)
        check("acefone called once for a duplicate", len(calls) == 1, str(len(calls)))
        check("duplicate acked as executed", engine.acks[-1]["status"] == "executed")
    finally:
        actions_mod.transfer_acefone_call = original

    print("\n9. barge-in during the goodbye disarms end_call")
    executor, engine, task, session, _ = build(gate=FakeGate(interrupt=True))
    await executor(pw_chat.VoiceAction(action_id="a4", type="end_call",
                                        params={"reason": "done"}, turn_id="t"), 4)
    check("end_call dropped on barge-in", engine.acks[-1]["detail"] == "barge_in")
    check("no EndTaskFrame on barge-in", len(task.frames) == 0)
    check("wrap-up still armed for the watchdog", session.wrap_up_started_event.is_set())

    print("\n10. clean end_call pushes EndTaskFrame")
    executor, engine, task, session, _ = build()
    await executor(pw_chat.VoiceAction(action_id="a5", type="end_call",
                                        params={"reason": "call completed"}, turn_id="t"), 4)
    check("EndTaskFrame pushed", len(task.frames) == 1, type(task.frames[0]).__name__ if task.frames else "none")
    check("call_ended_event set", session.call_ended_event.is_set())

    print("\n11. stale turn is dropped")
    executor, engine, task, session, _ = build()
    await executor(pw_chat.VoiceAction(action_id="b1", type="log_disposition",
                                        params={"outcome": "other", "notes": "x"}, turn_id="t"), 7)
    await executor(pw_chat.VoiceAction(action_id="b2", type="log_disposition",
                                        params={"outcome": "other", "notes": "y"}, turn_id="t"), 3)
    check("older seq dropped", engine.acks[-1]["detail"] == "stale_turn")

    print("\n12. a transfer survives the bot leg closing mid-request")
    import pw_channel.channels.voice.pipeline.actions as actions_mod
    released = asyncio.Event()

    async def slow_transfer(*, call_id="", ref_id="", call_uuid="", destination):
        await released.wait()
        return {"identifier": "ref_id", "value": ref_id, "intercom": destination}

    original = actions_mod.transfer_acefone_call
    actions_mod.transfer_acefone_call = slow_transfer
    try:
        executor, engine, task, session, handle = build()
        act = pw_chat.VoiceAction(action_id="d1", type="transfer_to_agent",
                                   params={}, turn_id="t")
        running = asyncio.ensure_future(executor(act, 4))
        await asyncio.sleep(0)
        running.cancel()
        try:
            await running
        except asyncio.CancelledError:
            pass
        check("the executor really was cancelled", running.cancelled())
        check("handle not yet transferred", handle.transferred is False)

        released.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if handle.transferred:
                break
        check("Acefone's answer still landed", handle.transferred is True,
              "the request outlived the pipeline instead of vanishing")
    finally:
        actions_mod.transfer_acefone_call = original

    print("\n13. identifiers are tried ref_id first")
    from pw_channel.channels.voice.telephony.acefone import transfer as ct
    seen = []

    class _Resp:
        is_success = False
        status_code = 422
        text = ""

        def json(self):
            return {"success": False, "message": "Invalid Call ID."}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            seen.append(next(k for k in ("ref_id", "call_id", "uuid") if k in json))
            return _Resp()

    original_client = ct.httpx.AsyncClient
    ct.httpx.AsyncClient = lambda **kw: _Client()
    try:
        try:
            await ct.transfer_acefone_call(
                call_id="1788861971.645032", ref_id="af-9c1e2b",
                call_uuid="01a0-aaaa", destination="01143131313",
            )
        except ct.CallTransferError:
            pass
        check("ref_id is tried first", seen[:1] == ["ref_id"], str(seen))
        check("all three identifiers are tried", seen == ["ref_id", "call_id", "uuid"], str(seen))

        seen.clear()
        try:
            await ct.transfer_acefone_call(
                call_id="same", ref_id="same", destination="01143131313"
            )
        except ct.CallTransferError:
            pass
        check("a repeated value is not retried", len(seen) == 1, str(seen))
    finally:
        ct.httpx.AsyncClient = original_client

    print("\n14. actions can be switched off entirely")
    config.PW_CHAT_ACTIONS_ENABLED = False
    executor, engine, task, session, _ = build()
    await executor(pw_chat.VoiceAction(action_id="c1", type="end_call", params={}, turn_id="t"), 1)
    check("nothing executed", len(task.frames) == 0 and not engine.acks)
    config.PW_CHAT_ACTIONS_ENABLED = True

    await pw_chat.close_client()
    print(f"\n{'='*60}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
