import base64
import json
import os
import secrets
import threading
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

PREFIX = "/api/admin"
HANDSHAKE_PATH = f"{PREFIX}/session-key"
KEY_TTL_SECS = 12 * 3600
MAX_KEYS = 5000
MAX_SKEW_MS = 5 * 60 * 1000
INFO = b"pw-voice-studio/v1"

router = APIRouter(prefix=PREFIX, tags=["dashboard"])


class _Key:
    __slots__ = ("aes", "expires_at", "seen")

    def __init__(self, raw: bytes):
        self.aes = AESGCM(raw)
        self.expires_at = time.time() + KEY_TTL_SECS
        self.seen: dict[bytes, float] = {}


_keys: dict[str, _Key] = {}
_lock = threading.Lock()


def required() -> bool:
    return os.getenv("DASHBOARD_API_ENCRYPTION", "required").strip().lower() not in ("off", "false", "0")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text)


class HandshakeRequest(BaseModel):
    publicKey: str


@router.post("/session-key")
def session_key(req: HandshakeRequest):
    try:
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64(req.publicKey))
    except Exception:
        raise HTTPException(status_code=400, detail="publicKey must be a base64 uncompressed P-256 point")

    own = ec.generate_private_key(ec.SECP256R1())
    salt = secrets.token_bytes(16)
    shared = own.exchange(ec.ECDH(), peer)
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO).derive(shared)
    kid = secrets.token_urlsafe(18)

    now = time.time()
    with _lock:
        for stale in [k for k, v in _keys.items() if v.expires_at < now]:
            _keys.pop(stale, None)
        while len(_keys) >= MAX_KEYS:
            _keys.pop(next(iter(_keys)))
        _keys[kid] = _Key(raw)

    public = own.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return {"kid": kid, "publicKey": _b64(public), "salt": _b64(salt), "expiresIn": KEY_TTL_SECS}


def _key(kid: str) -> _Key | None:
    with _lock:
        key = _keys.get(kid)
        if key is None or key.expires_at < time.time():
            _keys.pop(kid, None)
            return None
        return key


def _fresh_iv(key: _Key, iv: bytes) -> bool:
    now = time.time()
    with _lock:
        for old in [v for v, t in key.seen.items() if now - t > MAX_SKEW_MS / 1000]:
            key.seen.pop(old, None)
        if iv in key.seen:
            return False
        key.seen[iv] = now
        return True


def _aad(method: str, path: str) -> bytes:
    return f"{method.upper()} {path}".encode()


def _plain_error(status: int, detail: str) -> tuple[int, list, bytes]:
    body = json.dumps({"detail": detail}).encode()
    return status, [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())], body


class PayloadEncryptionMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not path.startswith(PREFIX)
            or path == HANDSHAKE_PATH
            or scope.get("method") == "OPTIONS"
        ):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        kid = headers.get(b"x-enc-kid", b"").decode()
        if not kid:
            if required():
                return await self._reply(send, *_plain_error(400, "the console API only accepts encrypted requests"))
            return await self.app(scope, receive, send)

        key = _key(kid)
        if key is None:
            return await self._reply(send, *_plain_error(409, "encryption key expired"))

        aad = _aad(scope["method"], path)
        raw = b""
        more = True
        while more:
            message = await receive()
            raw += message.get("body", b"")
            more = message.get("more_body", False)

        plain = b""
        if raw:
            try:
                envelope = json.loads(raw)
                iv = _unb64(envelope["iv"])
                if not _fresh_iv(key, iv):
                    return await self._reply(send, *_plain_error(400, "this request was already used"))
                inner = json.loads(key.aes.decrypt(iv, _unb64(envelope["ct"]), aad))
            except Exception:
                return await self._reply(send, *_plain_error(400, "the request could not be decrypted"))
            if abs(time.time() * 1000 - float(inner.get("ts", 0))) > MAX_SKEW_MS:
                return await self._reply(send, *_plain_error(400, "the request is too old; check the device clock"))
            body = inner.get("body")
            plain = b"" if body is None else json.dumps(body).encode()

        new_headers = [(k, v) for k, v in scope["headers"] if k not in (b"content-length", b"content-type")]
        if plain:
            new_headers += [(b"content-type", b"application/json"), (b"content-length", str(len(plain)).encode())]
        scope = dict(scope, headers=new_headers)

        delivered = False

        async def receive_plain():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": plain, "more_body": False}

        start: dict = {}
        chunks: list[bytes] = []

        async def send_encrypted(message):
            if message["type"] == "http.response.start":
                start.update(message)
                return
            if message["type"] != "http.response.body":
                return await send(message)
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            out_headers = [(k, v) for k, v in start.get("headers", []) if k != b"content-length"]
            content_type = dict(start.get("headers", [])).get(b"content-type", b"")
            if body and content_type.startswith(b"application/json"):
                iv = secrets.token_bytes(12)
                body = json.dumps({"iv": _b64(iv), "ct": _b64(key.aes.encrypt(iv, body, aad))}).encode()
                out_headers.append((b"x-enc", b"1"))
            out_headers.append((b"content-length", str(len(body)).encode()))
            await send({"type": "http.response.start", "status": start["status"], "headers": out_headers})
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive_plain, send_encrypted)

    @staticmethod
    async def _reply(send, status, headers, body):
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})
