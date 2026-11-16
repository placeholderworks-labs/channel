import json
import os
import pathlib
import sys

os.environ.setdefault("PW_CHAT_API_TOKEN", "testtoken")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pw_channel.channels.voice.telephony.acefone import webhook as wh
from pw_channel.channels.voice.states import call_lifecycle as lc

PASS, FAIL = [], []


def check(label, ok):
    (PASS if ok else FAIL).append(label)
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")


AGENT_ANSWERED_PAYLOAD = {
    "uuid": "abc-uuid-111",
    "call_to_number": "01143131329",
    "caller_id_number": "918065936515",
    "start_stamp": "2026-09-15 14:20:01",
    "answer_agent_number": "01143131329",
    "call_id": "1789455999.7788",
    "billing_circle": "Delhi",
    "call_status": "answered",
    "direction": "outbound",
    "customer_no_with_prefix ": "+918595864036",
    "ref_id": "01a0a3db-b982-7207-9262-c57bfdc9db9a",
}

HANGUP_PAYLOAD = {
    "uuid": "abc-uuid-111",
    "call_to_number": "01143131329",
    "start_stamp": "2026-09-15 14:20:01",
    "answer_stamp": "2026-09-15 14:20:09",
    "end_stamp": "2026-09-15 14:24:19",
    "billsec": "250",
    "digits_dialed": "$digits_dialed",
    "direction": "outbound",
    "duration": "258",
    "answered_agent_number": "01143131329",
    "missed_agent": "",
    "recording_url": "https://rec.acefone.in/abc.mp3",
    "call_status": "answered",
    "call_id": "1789455999.7788",
    "hangup_cause_description": "Normal Clearing",
    "hangup_cause_code": "16",
    "customer_no_with_prefix ": "+918595864036",
    "ref_id": "01a0a3db-b982-7207-9262-c57bfdc9db9a",
}


print("\n1. the two configured Acefone templates are told apart")
answered = wh.parse(AGENT_ANSWERED_PAYLOAD)
hangup = wh.parse(HANGUP_PAYLOAD)
check("answered-by-agent recognised", answered["kind"] == wh.AGENT_ANSWERED)
check("hangup recognised", hangup["kind"] == wh.HANGUP)

print("\n2. correlation ids are read from both")
check("ref_id on answered", answered["ref_id"] == "01a0a3db-b982-7207-9262-c57bfdc9db9a")
check("ref_id on hangup", hangup["ref_id"] == "01a0a3db-b982-7207-9262-c57bfdc9db9a")
check("call_id read", answered["call_id"] == "1789455999.7788")
check("uuid read separately", answered["uuid"] == "abc-uuid-111")

print("\n3. the trailing-space key in the supplied template is still read")
check("customer number found", answered["customer_number"] == "+918595864036")

print("\n4. an unsubstituted $variable is empty, not the literal")
check("digits_dialed not leaked", "$" not in json.dumps(hangup["body"]))
check("missing value reads empty", wh.parse({"ref_id": "$ref_id"})["ref_id"] == "")

print("\n5. hangup detail is extracted")
check("duration from billsec", hangup["duration_secs"] == 250.0)
check("recording url", hangup["recording_url"].endswith("abc.mp3"))
check("hangup cause", hangup["hangup_cause"] == "Normal Clearing")
check("agent number", hangup["agent_number"] == "01143131329")

print("\n6. an explicit event field wins over the shape")
tagged = wh.parse({**HANGUP_PAYLOAD, "event": "agent_answered"})
check("declared event trusted", tagged["kind"] == wh.AGENT_ANSWERED)

print("\n7. an unrecognised delivery is not guessed at")
check("unknown stays unknown", wh.parse({"foo": "bar"})["kind"] == wh.UNKNOWN)
check("empty body is unknown", wh.parse(None)["kind"] == wh.UNKNOWN)

print("\n8. event keys are unique per event but stable on replay")
check("replay produces same key", wh.parse(HANGUP_PAYLOAD)["event_key"] == hangup["event_key"])
check("two events differ", answered["event_key"] != hangup["event_key"])

MISSED_PAYLOAD = {
    "uuid": "u-9",
    "call_to_number": "01143131329",
    "start_stamp": "2026-09-15 14:20:01",
    "answer_stamp": "",
    "end_stamp": "2026-09-15 14:20:45",
    "billsec": "0",
    "duration": "44",
    "answered_agent_number": "",
    "missed_agent": "01143131329",
    "call_connected": "0",
    "recording_url": "",
    "call_status": "missed",
    "call_id": "1789455999.7788",
    "agent_ring_time": "30",
    "hangup_cause_description": "No Answer",
    "hangup_cause_code": "19",
    "customer_no_with_prefix ": "+918595864036",
    "ref_id": "01a0a3db-b982-7207-9262-c57bfdc9db9a",
}

print("\n8b. the agent-missed template is read as a hangup")
missed = wh.parse(MISSED_PAYLOAD)
check("classified as hangup", missed["kind"] == wh.HANGUP)
check("provider cause read", missed["hangup_cause"] == "No Answer")
check("zero billsec", missed["duration_secs"] == 0.0)
check("no answering agent", missed["agent_number"] == "")
check("but we know who missed it", missed["missed_agent"] == "01143131329")

print("\n9. lifecycle ordering")
check("forward order", lc.rank(lc.INITIATED) < lc.rank(lc.RINGING) < lc.rank(lc.ACTIVE)
      < lc.rank(lc.TRANSFER_INITIATED) < lc.rank(lc.TRANSFERRED)
      < lc.rank(lc.ACTIVE_WITH_AGENT) < lc.rank(lc.ENDED))
check("unknown status ranks lowest", lc.rank("NONSENSE") == 0)

print("\n10. a transferred call is no longer the bot's to end")
check("active is still ours", not lc.handed_over(lc.ACTIVE))
check("transfer_initiated is not", lc.handed_over(lc.TRANSFER_INITIATED))
check("transferred is not", lc.handed_over(lc.TRANSFERRED))
check("with agent is not", lc.handed_over(lc.ACTIVE_WITH_AGENT))

print("\n11. live states are the ones the console shows")
check("ended is not live", not lc.is_live(lc.ENDED))
check("with agent is live", lc.is_live(lc.ACTIVE_WITH_AGENT))
check("ringing is not on the line yet", not lc.is_live(lc.RINGING))

print("\n12. an 'agent answered' webhook is not an agent unless we transferred")
from pw_channel.channels.voice.telephony.acefone import webhook_routes as whr

routed = []


class _FakeLifecycle:
    @staticmethod
    def agent_answered(session_id, *, agent_number=""):
        routed.append(("agent", agent_number))

    @staticmethod
    def customer_answered(session_id, *, customer_number=""):
        routed.append(("customer", customer_number))

    @staticmethod
    def ended(session_id, **kw):
        routed.append(("ended", kw.get("reason")))


_real_lifecycle = whr.call_lifecycle
whr.call_lifecycle = _FakeLifecycle
try:
    event = wh.parse(AGENT_ANSWERED_PAYLOAD)

    routed.clear()
    whr._apply(1, wh.AGENT_ANSWERED, event, lc.ACTIVE)
    check("mid-call it is the customer answering", routed == [("customer", event["customer_number"])])

    routed.clear()
    whr._apply(1, wh.AGENT_ANSWERED, event, lc.RINGING)
    check("before answer too", routed and routed[0][0] == "customer")

    for prior in (lc.TRANSFER_INITIATED, lc.TRANSFERRED):
        routed.clear()
        whr._apply(1, wh.AGENT_ANSWERED, event, prior)
        check(f"after {prior} it is a real agent", routed == [("agent", event["agent_number"])])

    check("a call we never saw starts with the bot", whr._status_for(wh.AGENT_ANSWERED) == lc.ACTIVE)
    check("a hangup we never saw is ended", whr._status_for(wh.HANGUP) == lc.ENDED)
finally:
    whr.call_lifecycle = _real_lifecycle

print("\n13. the customer's number is masked before it leaves the server")
from pw_channel.channels.voice.calls import masking as call_masking

check("a mobile keeps only its last four", call_masking.mask_number("+918595864036") == "+91******4036")
check("an empty number stays empty", call_masking.mask_number("") == "")
check("a short value is not mostly revealed", call_masking.mask_number("1234") == "**34")

detail = call_masking.agent_view({
    "id": 7, "status": lc.ACTIVE_WITH_AGENT, "customerNumber": "+918595864036",
    "customerName": "Happy", "bookingReferenceId": "CART-1", "did": "01143131329",
    "agentNumber": "+911143131329", "startedAt": "s", "answeredAt": "a",
    "transferredAt": "t", "agentAnsweredAt": "aa", "endedAt": None, "endedReason": "",
    "durationSecs": 12.0, "recordingUrl": "",
    "refId": "leaky", "originalUuid": "leaky", "legHistory": [{"call_id": "leaky"}],
    "currentCallId": "leaky", "channel": "acefone", "callRecordId": 3,
})
check("the detail view masks the number", detail["customerNumber"] == "+91******4036")
check("it keeps what the agent needs", detail["bookingReferenceId"] == "CART-1" and detail["did"] == "01143131329")
check("and drops the provider plumbing",
      not {"refId", "originalUuid", "legHistory", "currentCallId", "callRecordId", "channel"} & set(detail))

print("\n14. a call carries the line it is headed for from the start")
from pw_channel import config as _cfg
from pw_channel.channels.voice.telephony.acefone.stream import _armed_did

_was = (_cfg.ENABLE_CALL_TRANSFER, _cfg.CALL_TRANSFER_NUMBER, _cfg.ACEFONE_AUTH_TOKEN)
try:
    _cfg.ENABLE_CALL_TRANSFER, _cfg.CALL_TRANSFER_NUMBER, _cfg.ACEFONE_AUTH_TOKEN = True, "01143131329", "tok"
    check("an armed call knows its line before any transfer", _armed_did() == "01143131329")
    _cfg.ENABLE_CALL_TRANSFER = False
    check("a call that cannot transfer stays off the agent's screen", _armed_did() == "")
    _cfg.ENABLE_CALL_TRANSFER, _cfg.CALL_TRANSFER_NUMBER = True, ""
    check("and so does one with no line configured", _armed_did() == "")
finally:
    _cfg.ENABLE_CALL_TRANSFER, _cfg.CALL_TRANSFER_NUMBER, _cfg.ACEFONE_AUTH_TOKEN = _was

print("\n15. the timeline shows our steps and the provider's, in order")
steps = call_masking.timeline(
    {
        "startedAt": "2026-09-16T12:00:00", "answeredAt": "2026-09-16T12:00:05",
        "transferredAt": "2026-09-16T12:02:00", "agentAnsweredAt": "2026-09-16T12:02:09",
        "endedAt": "2026-09-16T12:05:00", "endedReason": "Normal call clearing",
        "did": "01143131329",
    },
    [
        {"kind": "agent_answered", "receivedAt": "2026-09-16T12:00:07"},
        {"kind": "hangup", "receivedAt": "2026-09-16T12:05:01"},
    ],
)
labels = [s["label"] for s in steps]
check("it is in time order", [s["at"] for s in steps] == sorted(s["at"] for s in steps))
check("the handover names the line", "Transferred to 01143131329" in labels)
check("the provider's answer is there", "Provider reported the leg answered" in labels)
check("the provider's hangup is there", "Provider reported the hangup" in labels)
check("the end carries its reason", any("Normal call clearing" in l for l in labels))
check("provider rows are marked as theirs",
      sum(1 for s in steps if s["source"] == "provider") == 2)
check("a call with nothing yet has an empty timeline", call_masking.timeline({}, []) == [])

print(f"\n{'='*60}\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
