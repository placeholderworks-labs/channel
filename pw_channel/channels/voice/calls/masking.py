_VISIBLE_TAIL = 4
_VISIBLE_HEAD = 2


def mask_number(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    digits = [ch for ch in text if ch.isdigit()]
    if not digits:
        return text

    tail = _VISIBLE_TAIL if len(digits) >= 7 else max(len(digits) - 2, 0)
    head = _VISIBLE_HEAD if len(digits) >= _VISIBLE_HEAD + _VISIBLE_TAIL + 2 else 0
    keep_from = len(digits) - tail
    out, seen = [], 0
    for ch in text:
        if not ch.isdigit():
            out.append(ch)
            continue
        out.append(ch if seen < head or seen >= keep_from else "*")
        seen += 1
    return "".join(out)


def agent_view(call: dict) -> dict:
    return {
        "id": call["id"],
        "status": call["status"],
        "customerNumber": mask_number(call["customerNumber"]),
        "customerName": call["customerName"],
        "bookingReferenceId": call["bookingReferenceId"],
        "did": call["did"],
        "agentNumber": call["agentNumber"],
        "startedAt": call["startedAt"],
        "answeredAt": call["answeredAt"],
        "transferredAt": call["transferredAt"],
        "agentAnsweredAt": call["agentAnsweredAt"],
        "endedAt": call["endedAt"],
        "endedReason": call["endedReason"],
        "durationSecs": call["durationSecs"],
        "recordingUrl": call["recordingUrl"],
    }


def agent_views(calls: list[dict]) -> list[dict]:
    return [agent_view(call) for call in calls]


_PROVIDER_EVENT_LABELS = {
    "agent_answered": "Provider reported the leg answered",
    "hangup": "Provider reported the hangup",
}


def timeline(call: dict, events: list[dict] | None = None) -> list[dict]:
    steps = [
        ("Call started", call.get("startedAt"), "us"),
        ("Customer answered", call.get("answeredAt"), "us"),
        ("Transferred to " + (call.get("did") or "customer care"), call.get("transferredAt"), "us"),
        ("Agent picked up", call.get("agentAnsweredAt"), "us"),
    ]
    out = [
        {"at": at, "label": label, "source": source}
        for label, at, source in steps
        if at
    ]

    for event in events or []:
        label = _PROVIDER_EVENT_LABELS.get(event.get("kind"))
        if label and event.get("receivedAt"):
            out.append({"at": event["receivedAt"], "label": label, "source": "provider"})

    if call.get("endedAt"):
        reason = call.get("endedReason") or ""
        out.append({
            "at": call["endedAt"],
            "label": f"Call ended{f' — {reason}' if reason else ''}",
            "source": "us",
        })

    return sorted(out, key=lambda step: step["at"])
