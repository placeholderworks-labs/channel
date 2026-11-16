from typing import Any

AGENT_ANSWERED = "agent_answered"
HANGUP = "hangup"
UNKNOWN = "unknown"

_EVENT_NAMES = {
    "agent_answered": AGENT_ANSWERED,
    "answered": AGENT_ANSWERED,
    "call_answered": AGENT_ANSWERED,
    "hangup": HANGUP,
    "call_hangup": HANGUP,
    "completed": HANGUP,
}

_HANGUP_MARKERS = ("end_stamp", "billsec", "duration", "hangup_cause_code", "hangup_cause_key")
_AGENT_MARKERS = ("answer_agent_number", "answered_agent_number", "answer_stamp")


def clean(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in payload.items():
        name = str(key).strip()
        if not name:
            continue
        out[name] = _value(value)
    return out


def _value(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    text = str(value).strip()
    if not text or text.startswith("$"):
        return ""
    return text


def _first(body: dict[str, str], *names: str) -> str:
    for name in names:
        value = body.get(name)
        if value:
            return value
    return ""


def kind_of(body: dict[str, str]) -> str:
    declared = _EVENT_NAMES.get(_first(body, "event", "event_type", "trigger").lower())
    if declared:
        return declared
    if any(body.get(name) for name in _HANGUP_MARKERS):
        return HANGUP
    if any(body.get(name) for name in _AGENT_MARKERS):
        return AGENT_ANSWERED
    return UNKNOWN


def parse(payload: Any) -> dict[str, Any]:
    body = clean(payload)
    kind = kind_of(body)

    ref_id = _first(body, "ref_id", "refId", "reference_id")
    call_id = _first(body, "call_id", "callId")
    call_uuid = _first(body, "uuid", "call_uuid")
    agent_number = _first(body, "answer_agent_number", "answered_agent_number", "answered_agent")
    missed_agent = _first(body, "missed_agent")
    did = _first(body, "call_to_number", "did")
    customer = _first(
        body, "customer_no_with_prefix", "customer_number_with_prefix", "caller_id_number"
    )

    return {
        "kind": kind,
        "ref_id": ref_id,
        "call_id": call_id,
        "uuid": call_uuid,
        "agent_number": agent_number,
        "missed_agent": missed_agent,
        "did": did,
        "customer_number": customer,
        "direction": _first(body, "direction"),
        "call_status": _first(body, "call_status"),
        "recording_url": _first(body, "recording_url"),
        "duration_secs": _number(_first(body, "billsec", "duration")),
        "hangup_cause": _first(
            body, "hangup_cause_description", "hangup_cause_key", "reason_key"
        ),
        "event_key": event_key(kind, body, ref_id, call_id, call_uuid),
        "body": body,
    }


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def event_key(
    kind: str, body: dict[str, str], ref_id: str, call_id: str, call_uuid: str
) -> str:
    leg = call_uuid or call_id
    stamp = _first(body, "end_stamp", "answer_stamp", "start_stamp")
    return f"{kind}:{ref_id}:{leg}:{stamp}"
