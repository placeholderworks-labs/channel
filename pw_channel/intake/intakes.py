import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from pw_channel import config
from pw_channel.db.core import connection, is_configured

logger = logging.getLogger(__name__)

ABANDONED_CART = "abandoned_cart"
FIELD_TYPES = ("text", "number", "integer", "date", "datetime", "enum", "phone", "email", "url", "boolean")

BASE_FIELDS = [
    {"key": "reference_id", "label": "Reference id", "type": "text", "required": False, "base": True, "generated": True,
     "description": "Optional. Generated when left out and returned in the response; send your own to match records later.",
     "example": "AC-261013-7F3A2C"},
    {"key": "customer_name", "label": "Customer name", "type": "text", "required": True, "base": True,
     "description": "Used in the greeting.", "example": "Rahul Sharma"},
    {"key": "phone_number", "label": "Phone number", "type": "phone", "required": True, "base": True,
     "description": "Mobile number; stored in E.164 using the client's default country.", "example": "9876543210"},
]
SYSTEM_FIELDS = [
    {"key": "scheduled_at", "label": "Call at", "type": "datetime", "required": False, "base": True,
     "description": "ISO 8601 time to call, up to 7 days ahead. Empty calls after the intake's delay.", "example": "2026-10-14T18:30:00+05:30"},
    {"key": "language", "label": "Language", "type": "enum", "required": False, "base": True, "options": ["hindi", "english"],
     "description": "Language to open the call in. Empty uses the agent's default.", "example": "hindi"},
]

LEAD_QUALIFICATION = "lead_qualification"
LEAD_AGENT = "lead_qualification"
SERVICES = ["voice_agent", "whatsapp_chatbot", "website_bot", "email_automation", "workforce_automation",
            "chatgpt_app", "ai_native_app", "easyshorts", "evals_qa", "other"]

LEAD_FIELDS = [
    {"key": "company_name", "label": "Company", "type": "text", "required": True, "example": "Acme Realty"},
    {"key": "email", "label": "Email", "type": "email", "required": False, "example": "rahul@acmerealty.in"},
    {"key": "service_interest", "label": "Service of interest", "type": "enum", "required": True,
     "options": SERVICES, "example": "whatsapp_chatbot"},
    {"key": "requirement", "label": "What they wrote", "type": "text", "required": False,
     "description": "The message or requirement from the enquiry form.",
     "example": "Want a WhatsApp bot that answers flat enquiries and updates our CRM"},
    {"key": "industry", "label": "Industry", "type": "text", "required": False, "example": "Real estate"},
    {"key": "company_size", "label": "Company size", "type": "enum", "required": False,
     "options": ["1-10", "11-50", "51-200", "201-1000", "1000+"], "example": "11-50"},
    {"key": "budget_range", "label": "Budget", "type": "enum", "required": False,
     "options": ["under_2l", "2l_5l", "5l_15l", "above_15l", "not_sure"], "example": "2l_5l"},
    {"key": "timeline", "label": "Timeline", "type": "enum", "required": False,
     "options": ["asap", "1_3_months", "3_6_months", "exploring"], "example": "1_3_months"},
    {"key": "lead_source", "label": "Lead source", "type": "enum", "required": False,
     "options": ["website_form", "whatsapp", "linkedin", "referral", "campaign", "other"], "example": "website_form"},
    {"key": "city", "label": "City", "type": "text", "required": False, "example": "Gurgaon"},
]

_COLUMNS = (
    "id, name, description, agent, channel, kind, enabled, fields, token_hash, token_hint, "
    "delay_secs, dedupe_window_secs, call_hours_start, call_hours_end, release_after, builtin, created_at, updated_at, updated_by, "
    "adapter, adapter_config, journey"
)
_cache: dict[str, dict] = {}
_cache_at = 0.0
CACHE_SECS = 10.0


def _hash(token: str) -> str:
    from pw_channel.auth.sessions import _signing_key

    return hmac.new(_signing_key(), f"qms:{token}".encode(), hashlib.sha256).hexdigest()


def new_token() -> str:
    return "qms_" + secrets.token_urlsafe(30)


def _view(row: dict) -> dict:
    iso = lambda v: v.isoformat() if v else None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "agent": row["agent"],
        "channel": row["channel"],
        "kind": row["kind"],
        "enabled": row["enabled"],
        "fields": row["fields"] or [],
        "tokenSet": bool(row["token_hash"]) or (row["id"] == ABANDONED_CART and bool(config.INGESTION_API_TOKEN)),
        "tokenHint": row["token_hint"],
        "delaySecs": row["delay_secs"],
        "dedupeWindowSecs": row["dedupe_window_secs"],
        "callHoursStart": row.get("call_hours_start") or "",
        "callHoursEnd": row.get("call_hours_end") or "",
        "releaseAfter": iso(row.get("release_after")),
        "builtin": row["builtin"],
        "adapter": row.get("adapter") or "builtin.fields",
        "adapterConfig": row.get("adapter_config") or {},
        "journey": row.get("journey") or "",
        "createdAt": iso(row["created_at"]),
        "updatedAt": iso(row["updated_at"]),
        "updatedBy": row["updated_by"],
    }


def ensure_builtin() -> None:
    if not is_configured():
        return
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO qms_intakes (id, name, description, agent, channel, kind, fields, delay_secs,
                                     dedupe_window_secs, builtin, updated_by, adapter, journey)
            VALUES (%s, %s, %s, %s, 'journey', 'custom', '[]', NULL, %s, TRUE, 'system', 'builtin.canonical', 'single_call')
            ON CONFLICT (id) DO UPDATE SET adapter = 'builtin.canonical', fields = '[]',
                   journey = CASE WHEN qms_intakes.journey = '' THEN 'single_call' ELSE qms_intakes.journey END
            """,
            (ABANDONED_CART, "Standard records API",
             "Records already in the standard customer record format, for example from a client-run adapter service.",
             config.INGESTION_AGENT or "callvoice", config.INGESTION_DEDUPE_WINDOW_SECS),
        )
        conn.execute(
            """
            INSERT INTO qms_intakes (id, name, description, agent, channel, kind, fields, delay_secs,
                                     dedupe_window_secs, builtin, updated_by, adapter, journey)
            VALUES (%s, %s, %s, %s, 'journey', 'custom', %s, NULL, %s, TRUE, 'system', 'builtin.fields', 'single_call')
            ON CONFLICT (id) DO NOTHING
            """,
            (LEAD_QUALIFICATION, "Lead qualification API",
             "New leads from the website, WhatsApp or campaigns, called by the lead qualification agent.",
             LEAD_AGENT, json.dumps(LEAD_FIELDS), config.INGESTION_DEDUPE_WINDOW_SECS),
        )
    invalidate()


def sync_from_config(intakes_config: dict, token_lookup=None) -> list[str]:
    import os

    if not is_configured():
        return []
    synced = []
    with connection() as conn:
        for intake_id, spec in intakes_config.items():
            data = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)
            hours = data.get("contact_hours") or ("", "")
            conn.execute(
                """
                INSERT INTO qms_intakes (id, name, description, agent, channel, kind, fields, enabled, adapter,
                                         adapter_config, journey, call_hours_start, call_hours_end, builtin, updated_by)
                VALUES (%s, %s, %s, %s, 'journey', 'custom', %s, %s, %s, %s, %s, %s, %s, FALSE, 'pw.toml')
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, agent = EXCLUDED.agent, enabled = EXCLUDED.enabled,
                       adapter = EXCLUDED.adapter, adapter_config = EXCLUDED.adapter_config, journey = EXCLUDED.journey,
                       call_hours_start = EXCLUDED.call_hours_start, call_hours_end = EXCLUDED.call_hours_end,
                       fields = CASE WHEN EXCLUDED.fields = '[]'::jsonb THEN qms_intakes.fields ELSE EXCLUDED.fields END,
                       updated_by = 'pw.toml', updated_at = now()
                """,
                (intake_id, data.get("name") or intake_id.replace("_", " ").title(), data.get("description") or "",
                 data.get("agent") or "", json.dumps(data.get("fields") or []), bool(data.get("enabled", True)),
                 data.get("adapter") or "builtin.fields", json.dumps(data.get("adapter_config") or {}),
                 data.get("journey") or "", hours[0] or "", hours[1] or ""),
            )
            token = os.getenv(data["token_env"], "") if data.get("token_env") else ""
            if token:
                conn.execute(
                    "UPDATE qms_intakes SET token_hash = %s, token_hint = %s WHERE id = %s",
                    (_hash(token), token[-4:], intake_id),
                )
            synced.append(intake_id)
    invalidate()
    return synced


def invalidate() -> None:
    global _cache_at
    _cache_at = 0.0


def _load() -> dict[str, dict]:
    global _cache, _cache_at
    if time.monotonic() - _cache_at < CACHE_SECS:
        return _cache
    if not is_configured():
        _cache = {ABANDONED_CART: _memory_builtin()}
    else:
        with connection() as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM qms_intakes ORDER BY builtin DESC, name").fetchall()
        _cache = {r["id"]: {**_view(r), "_token_hash": r["token_hash"]} for r in rows}
        if ABANDONED_CART not in _cache:
            _cache[ABANDONED_CART] = _memory_builtin()
    _cache_at = time.monotonic()
    return _cache


def _memory_builtin() -> dict:
    return {
        "id": ABANDONED_CART, "name": "Standard records API",
        "description": "Records already in the standard customer record format.",
        "agent": config.INGESTION_AGENT or "callvoice", "channel": "journey",
        "kind": "custom", "enabled": True, "fields": [], "tokenSet": bool(config.INGESTION_API_TOKEN),
        "tokenHint": "", "delaySecs": None, "dedupeWindowSecs": None, "callHoursStart": "", "callHoursEnd": "",
        "releaseAfter": None, "builtin": True, "adapter": "builtin.canonical", "adapterConfig": {},
        "journey": "single_call", "createdAt": None, "updatedAt": None, "updatedBy": "", "_token_hash": "",
    }


def _has_token(intake: dict) -> bool:
    return bool(intake.get("_token_hash")) or (intake["id"] == ABANDONED_CART and bool(config.INGESTION_API_TOKEN))


def public(intake: dict) -> dict:
    return {**{k: v for k, v in intake.items() if not k.startswith("_")}, "tokenSet": _has_token(intake)}


def list_intakes() -> list[dict]:
    return [public(i) for i in _load().values()]


def get(intake_id: str) -> dict | None:
    found = _load().get(intake_id)
    return public(found) if found else None


def for_agent(agent: str) -> list[dict]:
    return [public(i) for i in _load().values() if agent and i["agent"] == agent]


def new_reference(intake_id: str) -> str:
    initials = "".join(part[0] for part in intake_id.split("_") if part).upper()[:4] or "QMS"
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    return f"{initials}-{today}-{secrets.token_hex(3).upper()}"


def all_fields(intake: dict) -> list[dict]:
    own = [f for f in intake.get("fields") or [] if f.get("key") not in {b["key"] for b in BASE_FIELDS + SYSTEM_FIELDS}]
    return BASE_FIELDS + own + SYSTEM_FIELDS


def token_matches(intake_id: str, presented: str) -> bool:
    found = _load().get(intake_id)
    if not found or not presented:
        return False
    if found["_token_hash"]:
        return hmac.compare_digest(found["_token_hash"], _hash(presented))
    if intake_id == ABANDONED_CART and config.INGESTION_API_TOKEN:
        return hmac.compare_digest(presented, config.INGESTION_API_TOKEN)
    return False


def save(intake: dict, *, actor: str, create: bool) -> dict:
    values = (
        intake["name"], intake.get("description", ""), intake.get("channel") or "acefone",
        bool(intake.get("enabled", True)), json.dumps(intake.get("fields") or []), actor,
    )
    with connection() as conn:
        if create:
            conn.execute(
                """
                INSERT INTO qms_intakes (name, description, channel, enabled, fields, updated_by, id, kind, agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'custom', '')
                """,
                (*values, intake["id"]),
            )
        else:
            conn.execute(
                """
                UPDATE qms_intakes SET name = %s, description = %s, channel = %s, enabled = %s,
                       fields = %s, updated_by = %s, updated_at = now()
                WHERE id = %s
                """,
                (*values, intake["id"]),
            )
    invalidate()
    return get(intake["id"])


KEEP = object()
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def connect(intake_id: str, *, agent: str, trigger: dict, actor: str, release_after=KEEP) -> dict:
    with connection() as conn:
        conn.execute(
            """
            UPDATE qms_intakes SET agent = %s, delay_secs = %s, dedupe_window_secs = %s,
                   call_hours_start = %s, call_hours_end = %s, updated_by = %s, updated_at = now()
            WHERE id = %s
            """,
            (agent, trigger.get("delaySecs"), trigger.get("dedupeWindowSecs"),
             trigger.get("callHoursStart") or "", trigger.get("callHoursEnd") or "", actor, intake_id),
        )
        if release_after is not KEEP:
            conn.execute("UPDATE qms_intakes SET release_after = %s WHERE id = %s", (release_after, intake_id))
    invalidate()
    return get(intake_id)


def rotate_token(intake_id: str, *, actor: str) -> str:
    token = new_token()
    with connection() as conn:
        conn.execute(
            "UPDATE qms_intakes SET token_hash = %s, token_hint = %s, updated_by = %s, updated_at = now() WHERE id = %s",
            (_hash(token), token[-4:], actor, intake_id),
        )
    invalidate()
    return token


def delete(intake_id: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM qms_intakes WHERE id = %s AND NOT builtin", (intake_id,))
    invalidate()


def label_of(intake_id: str) -> str:
    found = _load().get(intake_id)
    return found["name"] if found else intake_id


def describe_record(intake: dict | None, record: dict[str, Any]) -> list[dict]:
    fields = all_fields(intake) if intake else []
    labels = {f["key"]: f.get("label") or f["key"] for f in fields}
    order = [f["key"] for f in fields]
    keys = [k for k in order if k in record] + [k for k in record if k not in labels]
    out = []
    for key in keys:
        value = record.get(key)
        if value in (None, "") or key in ("scheduled_at",):
            continue
        out.append({"key": key, "label": labels.get(key, key.replace("_", " ")), "value": value})
    return out
