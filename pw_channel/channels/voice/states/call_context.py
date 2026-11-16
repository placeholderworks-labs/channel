from dataclasses import dataclass, field

from pw_channel import config


@dataclass
class CallContext:

    reference_id: str = ""
    booking_reference_id: str = ""
    customer_name: str = ""
    cart_summary: str = ""
    phone_number: str = ""
    language: str = field(default_factory=lambda: config.DEFAULT_LANGUAGE)
    channel: str = "unknown"
