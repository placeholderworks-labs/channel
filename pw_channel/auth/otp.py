import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass

from pw_channel.auth.sessions import _signing_key
from pw_channel.db.core import connection, is_configured

CODE_TTL_SECS = 300
MAX_ATTEMPTS = 5
RESEND_AFTER_SECS = 30
MAX_RESENDS = 3


class OtpError(Exception):
    pass


@dataclass
class Challenge:
    id: str
    user_id: int
    code_hash: str
    expires_at: float
    attempts: int = 0
    resends: int = 0
    sent_at: float = 0.0


_memory: dict[str, Challenge] = {}
_lock = threading.Lock()


def _hash(challenge_id: str, code: str) -> str:
    return hmac.new(_signing_key(), f"otp:{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _load(challenge_id: str) -> Challenge | None:
    if not is_configured():
        with _lock:
            return _memory.get(challenge_id)
    with connection() as conn:
        row = conn.execute(
            "SELECT id, user_id, code_hash, extract(epoch FROM expires_at) AS exp, attempts, resends, "
            "extract(epoch FROM sent_at) AS sent FROM login_challenges WHERE id = %s",
            (challenge_id,),
        ).fetchone()
    if not row:
        return None
    return Challenge(row["id"], row["user_id"], row["code_hash"], float(row["exp"]),
                     row["attempts"], row["resends"], float(row["sent"]))


def _save(c: Challenge) -> None:
    if not is_configured():
        with _lock:
            _memory[c.id] = c
            for key in [k for k, v in _memory.items() if v.expires_at < time.time()]:
                _memory.pop(key, None)
        return
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO login_challenges (id, user_id, code_hash, expires_at, attempts, resends, sent_at)
            VALUES (%s, %s, %s, to_timestamp(%s), %s, %s, to_timestamp(%s))
            ON CONFLICT (id) DO UPDATE SET code_hash = EXCLUDED.code_hash, expires_at = EXCLUDED.expires_at,
                attempts = EXCLUDED.attempts, resends = EXCLUDED.resends, sent_at = EXCLUDED.sent_at
            """,
            (c.id, c.user_id, c.code_hash, c.expires_at, c.attempts, c.resends, c.sent_at),
        )
        conn.execute("DELETE FROM login_challenges WHERE expires_at < now() - interval '1 day'")


def _drop(challenge_id: str) -> None:
    if not is_configured():
        with _lock:
            _memory.pop(challenge_id, None)
        return
    with connection() as conn:
        conn.execute("DELETE FROM login_challenges WHERE id = %s", (challenge_id,))


def start(user_id: int) -> tuple[str, str]:
    challenge_id = secrets.token_urlsafe(24)
    code = _new_code()
    now = time.time()
    _save(Challenge(challenge_id, user_id, _hash(challenge_id, code), now + CODE_TTL_SECS, sent_at=now))
    return challenge_id, code


def resend(challenge_id: str) -> tuple[int, str]:
    c = _load(challenge_id)
    now = time.time()
    if c is None or c.expires_at < now:
        raise OtpError("this sign-in has expired. Start again with your password")
    if c.resends >= MAX_RESENDS:
        raise OtpError("too many codes sent. Start again with your password")
    wait = RESEND_AFTER_SECS - (now - c.sent_at)
    if wait > 0:
        raise OtpError(f"wait {int(wait) + 1}s before asking for another code")
    code = _new_code()
    c.code_hash, c.expires_at, c.attempts, c.sent_at = _hash(challenge_id, code), now + CODE_TTL_SECS, 0, now
    c.resends += 1
    _save(c)
    return c.user_id, code


def cancel(challenge_id: str) -> None:
    _drop(challenge_id)


def verify(challenge_id: str, code: str) -> int:
    c = _load(challenge_id or "")
    if c is None or c.expires_at < time.time():
        raise OtpError("this code has expired. Start again with your password")
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if hmac.compare_digest(c.code_hash, _hash(c.id, code)):
        _drop(c.id)
        return c.user_id
    c.attempts += 1
    if c.attempts >= MAX_ATTEMPTS:
        _drop(c.id)
        raise OtpError("too many wrong codes. Start again with your password")
    _save(c)
    left = MAX_ATTEMPTS - c.attempts
    raise OtpError(f"that code is not right. {left} attempt{'s' if left != 1 else ''} left")
