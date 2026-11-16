from pw_channel.intake import intakes

ABANDONED_CART = intakes.ABANDONED_CART
PHONE_TEST = "phone_test"


def label(source: str) -> str:
    if source == PHONE_TEST:
        return "Phone test"
    return intakes.label_of(source) if source else "Unknown"


def labels() -> dict[str, str]:
    return {**{item["id"]: item["name"] for item in intakes.list_intakes()}, PHONE_TEST: "Phone test"}
