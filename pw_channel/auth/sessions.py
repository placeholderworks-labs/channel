import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field

from pw_channel import config


class InvalidSession(Exception):
    pass


@dataclass(frozen=True)
class SessionUser:
    id: int
    email: str
    name: str
    role: str
    permissions: frozenset = field(default_factory=frozenset)
    must_change_password: bool = False
    org_id: int | None = None

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin")


def _signing_key() -> bytes:
    secret = config.DASHBOARD_SESSION_SECRET or f"placeholderworks-voice::{config.DATABASE_URL}"
    return hashlib.sha256(secret.encode()).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(user: SessionUser) -> tuple[str, int]:
    expires_at = int(time.time()) + max(1, config.DASHBOARD_SESSION_HOURS) * 3600
    payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "exp": expires_at,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}", expires_at


def read_token(token: str) -> SessionUser:
    if not token or "." not in token:
        raise InvalidSession("no session token")

    body, _, signature = token.rpartition(".")
    expected = _b64(hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise InvalidSession("session token is not valid")

    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        raise InvalidSession("session token is malformed")

    if payload.get("exp", 0) < time.time():
        raise InvalidSession("session has expired")

    return SessionUser(
        id=int(payload["sub"]),
        email=payload["email"],
        name=payload.get("name", ""),
        role=payload.get("role", "operator"),
    )
