import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import os

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pw_channel import config
from pw_channel.auth import SessionUser
from pw_channel.admin import routes as admin_routes
from pw_channel.admin import brain as brain_routes
from pw_channel.settings import registry
from pw_channel.settings.store import read_meta

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


ADMIN = SessionUser(id=1, email="ops@placeholderworks.com", name="Ops", role="admin")

CHATBOT_CATALOG = {
    "sections": [
        {
            "name": "Brain",
            "categories": [
                {
                    "name": "Retention",
                    "groups": [
                        {
                            "id": "brain_discount",
                            "title": "Retention discount",
                            "blurb": "",
                            "section": "Brain",
                            "category": "Retention",
                            "scope": "brain",
                            "settings": [],
                        }
                    ],
                }
            ],
            "groups": [],
        }
    ],
    "values": {"RETENTION_DISCOUNT_PERCENT": {"value": "5", "changedFromDefault": True}},
    "editable": True,
    "source": "database",
}


class Stub:

    def __init__(self, status=200, payload=None, boom=None):
        self.status, self.payload, self.boom = status, payload or {}, boom
        self.seen = []

    async def request(self, method, url, headers=None, **kwargs):
        self.seen.append((method, url, headers or {}, kwargs.get("json")))
        if self.boom:
            raise self.boom
        return httpx.Response(
            self.status, json=self.payload, request=httpx.Request(method, url)
        )


def client(stub):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return stub

        async def __aexit__(self, *a):
            return False

    brain_routes.httpx.AsyncClient = FakeClient

    app = FastAPI()
    app.include_router(admin_routes.router)
    app.include_router(brain_routes.router)
    app.dependency_overrides[admin_routes.current_user] = lambda: ADMIN
    return TestClient(app)


def main():
    print("\n1. the settings URL is the chat URL's sibling, never a second knob")
    check(
        "derived from PW_CHAT_API_URL",
        config.PW_CHAT_SETTINGS_URL == config.PW_CHAT_API_URL.rsplit("/", 1)[0] + "/settings",
        config.PW_CHAT_SETTINGS_URL,
    )
    check(
        "and it is not something anyone can set separately",
        "PW_CHAT_SETTINGS_URL" not in registry.SETTINGS,
    )

    print("\n2. the brain's catalog is passed through, still tagged as the brain's")
    stub = Stub(payload=CHATBOT_CATALOG)
    r = client(stub).get("/api/admin/brain/settings")
    body = r.json()
    check("200", r.status_code == 200, r.text[:200])
    check("carries the chatbot's sections", body["sections"][0]["name"] == "Brain")
    check(
        "groups stay scoped to the brain, so writes route back to it",
        body["sections"][0]["categories"][0]["groups"][0]["scope"] == "brain",
    )
    check("drift survives the hop", body["values"]["RETENTION_DISCOUNT_PERCENT"]["changedFromDefault"])
    check("says where it read from", body["url"] == config.PW_CHAT_SETTINGS_URL)

    method, url, headers, _ = stub.seen[0]
    check("asked the chatbot over GET", method == "GET" and url.endswith("/voice/settings"), url)
    check(
        "authenticated with the token the pipeline already uses",
        headers.get("X-Api-Token") == config.PW_CHAT_API_TOKEN,
    )

    print("\n3. a save is forwarded verbatim")
    stub = Stub(payload={"saved": ["RETENTION_DISCOUNT_PERCENT"], "message": "Applied 1 change."})
    r = client(stub).put(
        "/api/admin/brain/settings",
        json={"values": {"RETENTION_DISCOUNT_PERCENT": "6"}, "apply": True},
    )
    check("200", r.status_code == 200, r.text[:200])
    check("reports what was saved", r.json()["saved"] == ["RETENTION_DISCOUNT_PERCENT"])
    check(
        "and sent exactly what the operator typed",
        stub.seen[0][3] == {"values": {"RETENTION_DISCOUNT_PERCENT": "6"}},
        str(stub.seen[0][3]),
    )

    print("\n4. the chatbot's own rejection reaches the operator, not a generic 500")
    stub = Stub(status=400, payload={"detail": "Discount cannot be above 50"})
    r = client(stub).put("/api/admin/brain/settings", json={"values": {"X": "1"}})
    check("the status is preserved", r.status_code == 400, str(r.status_code))
    check("so is the reason", "above 50" in r.json()["detail"], r.json()["detail"])

    print("\n5. a chatbot that is down is a clear message, not an empty screen")
    stub = Stub(boom=httpx.ConnectError("connection refused"))
    r = client(stub).get("/api/admin/brain/settings")
    check("502", r.status_code == 502, str(r.status_code))
    check("names what to check", "PW_CHAT_API_URL" in r.json()["detail"], r.json()["detail"])

    print("\n6. reset deletes one row per key")
    stub = Stub(payload={"cleared": True})
    r = client(stub).post(
        "/api/admin/brain/settings/reset",
        json={"keys": ["RETENTION_DISCOUNT_PERCENT", "VOICE_LLM_TEMPERATURE"]},
    )
    check("200", r.status_code == 200, r.text[:200])
    check("both came back", r.json()["reset"] == ["RETENTION_DISCOUNT_PERCENT", "VOICE_LLM_TEMPERATURE"])
    check("one DELETE each", [s[0] for s in stub.seen] == ["DELETE", "DELETE"], str([s[0] for s in stub.seen]))
    check(
        "addressed by key",
        stub.seen[0][1].endswith("/settings/RETENTION_DISCOUNT_PERCENT"),
        stub.seen[0][1],
    )

    stub = Stub(payload={"cleared": False})
    r = client(stub).post("/api/admin/brain/settings/reset", json={"keys": ["VOICE_LLM_MODEL"]})
    check(
        "a key that was never stored is not claimed as reset",
        r.json()["reset"] == [] and "already on their defaults" in r.json()["message"],
        r.json()["message"],
    )

    print("\n7. the pipeline's own reset refuses a key it does not know")
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[admin_routes.current_user] = lambda: ADMIN
    r = TestClient(app).post("/api/admin/settings/reset", json={"keys": ["NOT_A_SETTING"]})
    check(
        "400 or 409, never a silent success",
        r.status_code in (400, 409),
        str(r.status_code),
    )

    print("\n8. the pipeline's own payload carries what the screen needs to explain itself")
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[admin_routes.current_user] = lambda: ADMIN
    r = TestClient(app).get("/api/admin/settings")
    if r.status_code != 200:
        check("settings payload", False, f"{r.status_code} — is Postgres up? {r.text[:120]}")
    else:
        body = r.json()
        vals = body["values"]
        check("every setting has a row", len(vals) == len(registry.SETTINGS), str(len(vals)))
        missing = [
            k for k, v in vals.items()
            if "changedFromDefault" not in v or "source" not in v or "inheritedValue" not in v
        ]
        check(
            "each one says where it came from and what it falls back to",
            not missing,
            str(missing[:4]),
        )
        check(
            "a per-channel override shows the global it inherits",
            vals["VAD_STOP_SECS_WEBSITE"]["inheritedValue"] == vals["VAD_STOP_SECS"]["value"],
            f'{vals["VAD_STOP_SECS_WEBSITE"]["inheritedValue"]!r} vs '
            f'{vals["VAD_STOP_SECS"]["value"]!r}',
        )
        check(
            "a secret still never leaves the process",
            vals["MURF_API_KEY"]["value"] == "" and vals["MURF_API_KEY"]["defaultValue"] is None,
        )
        check(
            "but the screen can still say a secret is drifting",
            isinstance(vals["MURF_API_KEY"]["changedFromDefault"], bool),
        )
        stored = read_meta()
        wrong = []
        for key, view in vals.items():
            setting = registry.SETTINGS[key]
            if key not in stored:
                if view["changedFromDefault"]:
                    wrong.append(f"{key}: flagged with no stored row")
                continue
            really = (stored[key]["value"] or "").strip() != (setting.default or "").strip()
            if really != view["changedFromDefault"]:
                wrong.append(f"{key}: flag={view['changedFromDefault']} actual={really}")
        check(
            "the difference flag matches the values it claims to compare",
            not wrong,
            str(wrong[:4]),
        )

        drifting = [k for k, v in vals.items() if v["changedFromDefault"]]
        check(
            "a non-secret difference shows both sides so it can be judged",
            all(
                vals[k]["defaultValue"] is not None
                for k in drifting
                if not registry.SETTINGS[k].secret
            ),
            str([
                k for k in drifting
                if vals[k]["defaultValue"] is None
                and not registry.SETTINGS[k].secret
            ]) or "",
        )
        print(f"       ({len(drifting)} value(s) currently differ from their fallback)")

    print("\n9. Murf offers exactly the three voices, and .env picks one of them")
    voice = registry.SETTINGS["MURF_TTS_VOICE"]
    check("it is a dropdown", voice.type == "select", voice.type)
    check("three voices", voice.options == ("Anisha", "Ayushi", "Pooja"), str(voice.options))
    env = dict(
        line.split("=", 1)
        for line in (pathlib.Path(__file__).resolve().parents[2] / ".env")
        .read_text(encoding="utf-8")
        .splitlines()
        if "=" in line and not line.startswith("#")
    )
    check(
        "the configured voice is one of them",
        env.get("MURF_TTS_VOICE", voice.default) in voice.options,
        env.get("MURF_TTS_VOICE", ""),
    )

    print(f"\n{'=' * 58}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


sys.exit(main())
