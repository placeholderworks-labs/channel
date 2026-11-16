import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from pw_sdk.utils import phone as phones
from pw_sdk.utils.convert import as_float
from pw_sdk.utils.time import IST, zone

MAX_TEXT = 500
MAX_SCHEDULE_AHEAD = timedelta(days=7)
CLOCK_SKEW = timedelta(minutes=2)


@dataclass
class FieldCheck:
    values: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    scheduled_at: datetime | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def _text(value) -> str:
    if value is None or isinstance(value, (dict, list, bool)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("none", "null", "nan", "undefined") else text


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _clean_number(number: float) -> float | int:
    return int(number) if float(number).is_integer() else round(number, 2)


def default_country() -> str:
    return os.getenv("CLIENT_COUNTRY", "IN").upper()


def allowed_countries() -> set[str]:
    raw = os.getenv("ALLOWED_COUNTRIES", "")
    return {item.strip().upper() for item in raw.split(",") if item.strip()} or {default_country()}


def local_zone():
    return zone(os.getenv("CLIENT_TIMEZONE", "Asia/Kolkata"))


def parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_zone())
    return parsed.astimezone(timezone.utc)


def check_phone(raw: str) -> tuple[str | None, str]:
    e164 = phones.to_e164(raw, default_country())
    if not e164:
        return None, "not a valid phone number"
    country = phones.country_of(e164)
    if country not in allowed_countries():
        return None, f"numbers from {country or 'this country'} are not allowed"
    if country == "IN" and not phones.is_indian_mobile(e164):
        return None, "not a valid Indian mobile number"
    return e164, ""


def check_schedule(when: datetime | None, now: datetime) -> str:
    if when is None:
        return ""
    if when < now - CLOCK_SKEW:
        return "is in the past"
    if when > now + MAX_SCHEDULE_AHEAD:
        return "is more than 7 days ahead"
    return ""


def validate_with_fields(record, fields: list[dict], *, received_at: datetime | None = None) -> FieldCheck:
    result = FieldCheck()
    now = received_at or datetime.now(timezone.utc)

    def fail(name: str, message: str) -> None:
        result.errors.append({"field": name, "error": message})

    if not isinstance(record, dict):
        fail("", "each record must be a JSON object")
        return result

    for spec in fields:
        key = spec["key"]
        raw = record.get(key)
        empty = raw is None or (isinstance(raw, str) and not raw.strip())
        cond = spec.get("required_if") or {}
        needed = spec.get("required") or (
            cond and str(record.get(cond.get("field"), "")).strip().lower() == str(cond.get("equals", "")).lower()
        )
        if empty:
            if needed:
                fail(key, "missing" + (f" (required when {cond['field']} is {cond['equals']})" if cond and not spec.get("required") else ""))
            continue
        kind = spec.get("type", "text")
        text = _text(raw)
        if kind in ("number", "integer"):
            number = as_float(raw)
            if number is None or (kind == "integer" and not float(number).is_integer()):
                fail(key, f"must be {'a whole number' if kind == 'integer' else 'a number'}")
                continue
            if spec.get("min") is not None and number < float(spec["min"]):
                fail(key, f"must be at least {spec['min']}")
                continue
            if spec.get("max") is not None and number > float(spec["max"]):
                fail(key, f"must be at most {spec['max']}")
                continue
            result.values[key] = int(number) if kind == "integer" else _clean_number(number)
        elif kind == "date":
            day = _date(text)
            if day is None:
                fail(key, "must be a date in YYYY-MM-DD format")
                continue
            if spec.get("future_only") and day < now.astimezone(local_zone()).date():
                fail(key, "is in the past")
                continue
            result.values[key] = day.isoformat()
        elif kind == "datetime":
            when = parse_timestamp(text)
            if when is None:
                fail(key, "must be an ISO 8601 timestamp, e.g. 2026-10-14T18:30:00+05:30")
                continue
            result.values[key] = when.isoformat()
        elif kind == "enum":
            options = [str(o) for o in spec.get("options") or []]
            match = next((o for o in options if o.lower() == text.lower()), None)
            if options and match is None:
                fail(key, "must be one of " + ", ".join(options))
                continue
            result.values[key] = match or text
        elif kind == "phone":
            e164, problem = check_phone(text)
            if not e164:
                fail(key, problem)
                continue
            result.values[key] = e164
        elif kind == "email":
            if "@" not in text or "." not in text.split("@")[-1]:
                fail(key, "must be an email address")
                continue
            result.values[key] = text.lower()
        elif kind == "url":
            if not text.startswith(("https://", "http://")):
                fail(key, "must be an http(s) URL")
                continue
            result.values[key] = text
        elif kind == "boolean":
            truth = str(raw).strip().lower()
            if truth not in ("true", "false", "1", "0", "yes", "no"):
                fail(key, "must be true or false")
                continue
            result.values[key] = truth in ("true", "1", "yes")
        else:
            if len(text) > MAX_TEXT:
                fail(key, f"longer than {MAX_TEXT} characters")
                continue
            result.values[key] = text

    scheduled_text = result.values.get("scheduled_at")
    if scheduled_text:
        scheduled = parse_timestamp(scheduled_text)
        problem = check_schedule(scheduled, now)
        if problem:
            fail("scheduled_at", problem)
        else:
            result.scheduled_at = scheduled
    return result


__all__ = ["IST", "FieldCheck", "check_phone", "check_schedule", "parse_timestamp", "validate_with_fields"]
