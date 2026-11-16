import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from pw_channel.intake import intakes
from pw_channel.orchestrator import store
from pw_channel.policy.dnd import checker
from pw_sdk.utils.time import next_allowed, zone
from pw_sdk import CustomerRecord

CONSENT_FIELD = {"voice": "call", "whatsapp": "whatsapp", "email": "email"}
CONTACT_HOURS_CHANNELS = {"voice"}


@dataclass
class Decision:
    action: str
    reason: str = ""
    run_at: datetime | None = None


def _hours(intake_id: str, channel: str) -> tuple[str | None, str | None]:
    intake = intakes.get(intake_id) or {}
    start, end = intake.get("callHoursStart") or "", intake.get("callHoursEnd") or ""
    if not (start and end) and channel in CONTACT_HOURS_CHANNELS:
        start, end = os.getenv("CONTACT_HOURS_START", ""), os.getenv("CONTACT_HOURS_END", "")
    if not (start and end) and channel not in CONTACT_HOURS_CHANNELS:
        start, end = os.getenv("MESSAGE_HOURS_START", ""), os.getenv("MESSAGE_HOURS_END", "")
    return start or None, end or None


def _start_of_day(now: datetime, tz_name: str) -> datetime:
    local = now.astimezone(zone(tz_name))
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


async def gate(task: store.TaskRow, record: CustomerRecord, now: datetime) -> Decision:
    tz_name = os.getenv("CLIENT_TIMEZONE", "Asia/Kolkata")
    blocked = await asyncio.to_thread(store.blocked_channels, task.lead_key)
    if task.channel in blocked:
        return Decision("skip", f"customer opted out of {task.channel}")
    if not record.customer.consent.allows(CONSENT_FIELD.get(task.channel, task.channel)):
        return Decision("skip", f"no consent for {task.channel}")
    if task.channel == "voice":
        if not record.customer.phone:
            return Decision("skip", "no phone number")
        if await checker().is_blocked(record.customer.phone):
            return Decision("skip", "number is on the DND list")
    if task.channel == "whatsapp" and not record.customer.phone:
        return Decision("skip", "no phone number")
    if task.channel == "email" and not record.customer.email:
        return Decision("skip", "no email address")

    start, end = _hours(task.intake, task.channel)
    allowed = next_allowed(now, start, end, tz_name)
    if allowed > now:
        return Decision("defer", f"outside contact hours {start}-{end}", allowed)

    cap = int(os.getenv("MAX_CONTACTS_PER_DAY", "6") or 0)
    if cap:
        day_start = _start_of_day(now, tz_name)
        used = await asyncio.to_thread(store.contacts_today, task.lead_key, day_start)
        if used >= cap:
            tomorrow = day_start + timedelta(days=1)
            return Decision("defer", f"daily contact limit of {cap} reached", next_allowed(tomorrow, start, end, tz_name))
    return Decision("run")
