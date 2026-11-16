import json
import logging
import threading

from pw_channel.core.target import CallTarget
from pw_channel.db.core import connection, is_configured
from pw_sdk.utils import phone
from pw_sdk import CustomerRecord

logger = logging.getLogger(__name__)

_memory: dict[str, dict] = {}
_lock = threading.Lock()
_MEMORY_LIMIT = 5000


def lead_key(record: CustomerRecord) -> str:
    if record.customer.phone:
        return f"phone:{record.customer.phone}"
    return f"email:{record.customer.email or ''}"


def _row_to_target(row: dict) -> CallTarget:
    canonical = row["canonical"] if isinstance(row["canonical"], dict) else json.loads(row["canonical"])
    return CallTarget(
        record=CustomerRecord.model_validate(canonical),
        intake=row.get("intake") or "",
        agent=row.get("agent") or "",
        journey_id=row.get("journey_id"),
    )


def save(target: CallTarget) -> int:
    record = target.record
    values = {
        "reference_id": record.ref.reference_id,
        "intake": target.intake,
        "agent": target.agent,
        "lead_key": lead_key(record),
        "phone": record.customer.phone or "",
        "email": record.customer.email or "",
        "canonical": record.model_dump(mode="json"),
    }
    if not is_configured():
        with _lock:
            if len(_memory) >= _MEMORY_LIMIT:
                _memory.pop(next(iter(_memory)))
            _memory[values["reference_id"].lower()] = {**values, "id": len(_memory) + 1, "journey_id": target.journey_id}
            return _memory[values["reference_id"].lower()]["id"]
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO records (reference_id, intake, agent, lead_key, phone, email, canonical)
            VALUES (%(reference_id)s, %(intake)s, %(agent)s, %(lead_key)s, %(phone)s, %(email)s, %(canonical)s)
            ON CONFLICT (reference_id) DO UPDATE SET
                intake = EXCLUDED.intake, agent = EXCLUDED.agent, lead_key = EXCLUDED.lead_key,
                phone = EXCLUDED.phone, email = EXCLUDED.email, canonical = EXCLUDED.canonical, updated_at = now()
            RETURNING id
            """,
            {**values, "canonical": json.dumps(values["canonical"])},
        ).fetchone()
    return row["id"]


def attach_journey(reference_id: str, journey_id: int) -> None:
    if not is_configured():
        with _lock:
            if reference_id.lower() in _memory:
                _memory[reference_id.lower()]["journey_id"] = journey_id
        return
    with connection() as conn:
        conn.execute("UPDATE records SET journey_id = %s, updated_at = now() WHERE reference_id = %s", (journey_id, reference_id))


def get(reference_id: str = "", phone_number: str = "") -> CallTarget | None:
    ref = (reference_id or "").strip()
    last10 = phone.last10(phone_number)
    if not is_configured():
        with _lock:
            if ref and ref.lower() in _memory:
                return _row_to_target(_memory[ref.lower()])
            if len(last10) == 10:
                for row in reversed(list(_memory.values())):
                    if phone.last10(row["phone"]) == last10:
                        return _row_to_target(row)
        return None
    with connection() as conn:
        if ref:
            row = conn.execute("SELECT * FROM records WHERE reference_id = %s", (ref,)).fetchone()
            if row:
                return _row_to_target(row)
        if len(last10) == 10:
            row = conn.execute(
                "SELECT * FROM records WHERE right(phone, 10) = %s ORDER BY updated_at DESC LIMIT 1", (last10,)
            ).fetchone()
            if row:
                return _row_to_target(row)
    return None


def clear_memory() -> None:
    with _lock:
        _memory.clear()
