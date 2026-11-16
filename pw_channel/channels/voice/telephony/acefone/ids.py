import re

DELIMITER = "|"
_UNIQUEID = re.compile(r"\d+\.\d+$")


def encode_custom_identifier(reference_id: str, name: str = "") -> str:
    return f"{reference_id}{DELIMITER}{name}" if name else reference_id


def decode_custom_identifier(value: str) -> tuple[str, str]:
    reference_id, _, name = value.partition(DELIMITER)
    return reference_id, name


def call_id_of(call_sid: str) -> str:
    match = _UNIQUEID.search(call_sid or "")
    return match.group(0) if match else (call_sid or "")
