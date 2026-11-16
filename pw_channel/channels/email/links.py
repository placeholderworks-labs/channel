import base64
import hashlib
import hmac
import json
import os


def _secret() -> bytes:
    return (os.getenv("EMAIL_LINK_SECRET") or os.getenv("DASHBOARD_SESSION_SECRET") or "pw-email-links").encode()


def sign(data: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
    mac = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{body}.{mac}"


def read(token: str) -> dict | None:
    body, _, mac = token.partition(".")
    if not body or not hmac.compare_digest(mac, hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:24]):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None


def public_base() -> str:
    return (os.getenv("CHANNEL_PUBLIC_URL") or os.getenv("PUBLIC_BASE_URL") or "http://localhost:8420").rstrip("/")


def tracked(url: str, lead_key: str, task_id: int) -> str:
    return f"{public_base()}/api/channel/email/click/{sign({'u': url, 'l': lead_key, 't': task_id})}"


def unsubscribe(lead_key: str) -> str:
    return f"{public_base()}/api/channel/email/unsubscribe/{sign({'l': lead_key})}"
