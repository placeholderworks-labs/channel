import secrets
from datetime import datetime

from pw_channel.intake.validation import validate_with_fields
from pw_sdk import Adapter, CustomerRecord, RejectItem, map_batch

BASE_KEYS = {"reference_id", "customer_name", "phone_number", "email", "language", "scheduled_at", "campaign_id"}
LANGUAGES = {"hi": "hindi", "hindi": "hindi", "en": "english", "english": "english"}


def new_reference(intake_id: str, now: datetime) -> str:
    initials = "".join(part[0] for part in intake_id.split("_") if part).upper()[:4] or "REC"
    return f"{initials}-{now:%y%m%d}-{secrets.token_hex(3).upper()}"


class FieldsAdapter(Adapter):
    name = "builtin.fields"
    version = "1.0.0"

    def transform_records(self, payload, ctx):
        fields = ctx.config.get("fields") or []
        labels = {spec["key"]: spec.get("label") or spec["key"] for spec in fields}

        def build(raw, index):
            if isinstance(raw, dict) and not str(raw.get("reference_id") or "").strip():
                raw = {**raw, "reference_id": new_reference(ctx.intake_id, ctx.received_at)}
            checked = validate_with_fields(raw, fields, received_at=ctx.received_at)
            if not checked.ok:
                first = checked.errors[0]
                raise RejectItem("; ".join(f"{e['field'] or 'record'} {e['error']}" for e in checked.errors), first["field"])
            values = checked.values
            facts = [
                {"key": key, "label": labels.get(key, key.replace("_", " ")), "value": str(value)}
                for key, value in values.items()
                if key not in BASE_KEYS and value not in (None, "")
            ]
            return CustomerRecord.model_validate({
                "ref": {"reference_id": values["reference_id"], "campaign_id": values.get("campaign_id"),
                        "occurred_at": ctx.received_at},
                "customer": {
                    "name": values.get("customer_name", ""),
                    "phone": values.get("phone_number"),
                    "email": values.get("email"),
                    "language": LANGUAGES.get(str(values.get("language", "")).lower()),
                },
                "summary": str(values.get("summary") or values.get("requirement") or "")[:500],
                "facts": facts,
                "schedule": {"scheduled_at": checked.scheduled_at},
            })

        return map_batch(payload, build)
