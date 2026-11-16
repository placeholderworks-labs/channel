from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pw_sdk.contracts.runtime import RuntimeContext
from pw_sdk.utils import phone
from pw_sdk import CustomerRecord


@dataclass
class CallTarget:
    record: CustomerRecord
    intake: str = ""
    agent: str = ""
    journey_id: int | None = None
    task_id: int | None = None
    received_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def reference_id(self) -> str:
        return self.record.ref.reference_id

    @property
    def phone_number(self) -> str:
        return self.record.customer.phone or ""

    @property
    def national_number(self) -> str:
        return phone.national(self.phone_number, phone.country_of(self.phone_number) or "IN")

    @property
    def customer_name(self) -> str:
        return self.record.customer.name

    @property
    def email(self) -> str:
        return self.record.customer.email or ""

    @property
    def language(self) -> str:
        return self.record.customer.language or ""

    @property
    def summary(self) -> str:
        return self.record.spoken_summary()

    @property
    def facts(self) -> list[dict]:
        return [fact.model_dump() for fact in self.record.facts]

    def has_details(self) -> bool:
        cart = self.record.cart
        return bool(self.summary or (cart and (cart.items or cart.total)) or self.record.facts)

    def runtime_fields(self) -> dict[str, Any]:
        fields = RuntimeContext.record_fields(self.record)
        fields["intake"] = self.intake
        return fields
