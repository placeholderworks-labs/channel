import base64
import json
import os
import pathlib
import secrets
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ["DASHBOARD_API_ENCRYPTION"] = "required"

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient

from pw_channel.auth import transport_crypto as tc

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


app = FastAPI()
app.add_middleware(tc.PayloadEncryptionMiddleware)
app.include_router(tc.router)


@app.post("/api/admin/echo")
def echo(payload: dict = Body(...)):
    return {"got": payload}


@app.get("/api/admin/ping")
def ping():
    return {"pong": True}


def handshake(client):
    own = ec.generate_private_key(ec.SECP256R1())
    pub = own.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    r = client.post("/api/admin/session-key", json={"publicKey": base64.b64encode(pub).decode()})
    j = r.json()
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(j["publicKey"]))
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(j["salt"]), info=tc.INFO).derive(own.exchange(ec.ECDH(), peer))
    return j["kid"], AESGCM(raw)


def seal(aes, method, path, body, ts=None, iv=None):
    iv = iv or secrets.token_bytes(12)
    inner = json.dumps({"ts": ts or int(time.time() * 1000), "body": body}).encode()
    return {"iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(aes.encrypt(iv, inner, f"{method} {path}".encode())).decode()}


def open_(aes, method, path, payload):
    return json.loads(aes.decrypt(base64.b64decode(payload["iv"]), base64.b64decode(payload["ct"]), f"{method} {path}".encode()))


client = TestClient(app)
kid, aes = handshake(client)
check("handshake returns a key id", bool(kid))

H = {"X-Enc-Kid": kid}
r = client.post("/api/admin/echo", json=seal(aes, "POST", "/api/admin/echo", {"a": 1}), headers=H)
check("an encrypted request reaches the route", r.status_code == 200, r.text[:120])
check("and the response is ciphertext", r.headers.get("x-enc") == "1" and "got" not in r.text)
check("which decrypts to the route's answer", open_(aes, "POST", "/api/admin/echo", r.json()) == {"got": {"a": 1}})

r = client.get("/api/admin/ping", headers=H)
check("a GET's response is encrypted too", open_(aes, "GET", "/api/admin/ping", r.json()) == {"pong": True})

r = client.post("/api/admin/echo", json={"a": 1})
check("plain JSON is refused", r.status_code == 400 and "encrypted" in r.text, r.text)
r = client.get("/api/admin/ping", headers={"X-Enc-Kid": "nope"})
check("an unknown key is 409 so the console re-keys", r.status_code == 409)

iv = secrets.token_bytes(12)
first = client.post("/api/admin/echo", json=seal(aes, "POST", "/api/admin/echo", {"x": 1}, iv=iv), headers=H)
again = client.post("/api/admin/echo", json=seal(aes, "POST", "/api/admin/echo", {"x": 1}, iv=iv), headers=H)
check("a replayed request is refused", first.status_code == 200 and again.status_code == 400, again.text)

r = client.post("/api/admin/echo", json=seal(aes, "POST", "/api/admin/other", {"x": 1}), headers=H)
check("a body sealed for another path is refused", r.status_code == 400)
r = client.post("/api/admin/echo", json=seal(aes, "POST", "/api/admin/echo", {"x": 1}, ts=int(time.time() * 1000) - 10 * 60 * 1000), headers=H)
check("an old request is refused", r.status_code == 400 and "old" in r.text)

print(f"\n{'=' * 60}\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
