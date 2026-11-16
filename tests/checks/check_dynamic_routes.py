import os
import pathlib
import sys

os.environ["USE_DB"] = "false"
os.environ["DATABASE_URL"] = ""

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pw_channel.app import create_app

app = create_app()
from pw_channel import config
from pw_channel.channels.voice.routes import dynamic
from pw_channel.channels.voice.routes import ws as ws_routes

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


def tagged():
    return [
        getattr(r, "path", None)
        for r in app.router.routes
        if getattr(r, "name", "") == dynamic.ROUTE_TAG
    ]


def main_test():
    client = TestClient(app)

    print("\n1. every channel is registered, enabled or not")
    paths = tagged()
    for channel in ws_routes.channels():
        check(f"{channel} has a route", ws_routes.path_for(channel) in paths)
    check("no duplicate paths", len(paths) == len(set(paths)), str(paths))

    print("\n2. the enable flag is read at connect time, not at import")
    config.ENABLE_WEBSITE = False
    try:
        with client.websocket_connect(ws_routes.path_for("website")):
            check("a disabled channel refuses the socket", False, "it connected")
    except WebSocketDisconnect as e:
        check("a disabled channel refuses the socket", e.code == 1013, f"code={e.code}")
        check("and says why", e.reason == "channel disabled", repr(e.reason))

    print("\n3. an unknown path is refused differently from a disabled channel")
    try:
        with client.websocket_connect("/ws/not-a-channel"):
            check("unknown path refused", False, "it connected")
    except WebSocketDisconnect as e:
        check("unknown path refused", e.code == 1000, f"code={e.code}")
        check("and carries no reason, unlike a disabled channel", not e.reason, repr(e.reason))
    except Exception as e:
        check("unknown path refused", True, type(e).__name__)

    print("\n4. the ingestion switch is read per request")
    config.INGESTION_ENABLED = False
    r = client.post("/api/ingestion/calls", json={"phone_number": "9999999999"})
    check("disabled ingestion 503s", r.status_code == 503, str(r.status_code))
    check("and says why", "disabled" in r.text)

    config.INGESTION_ENABLED = True
    config.INGESTION_API_TOKEN = "t"
    r = client.post("/api/ingestion/calls", json={}, headers={"X-API-Key": "t"})
    check("enabling it needs no restart", r.status_code == 422, str(r.status_code))

    print("\n5. a path change rebuilds the table")
    before = tagged()
    config.ACEFONE_WS_PATH = "/ws/acefone-v2"
    config.ENABLE_WEBSITE = True
    config._notify_reload(
        {
            "ACEFONE_WS_PATH": ("/ws/acefone", "/ws/acefone-v2"),
            "ENABLE_WEBSITE": (False, True),
        }
    )
    after = tagged()
    check("the new path is live", "/ws/acefone-v2" in after)
    check("the old one is gone", "/ws/acefone" not in after)
    check("nothing was duplicated", len(after) == len(before), f"{len(before)} -> {len(after)}")
    check(
        "the channel that came on is active",
        ws_routes.path_for("website") in ws_routes.active_paths(),
    )

    print("\n6. there is no standalone voice page any more")
    r = TestClient(app, follow_redirects=False).get("/")
    check("/ redirects to the console", r.status_code in (301, 302, 307, 308), str(r.status_code))
    check("and points at the dashboard", r.headers.get("location") == "/dashboard",
          str(r.headers.get("location")))
    check(
        "no catch-all mount left to shadow a route",
        not any(getattr(r_, "name", "") == "static" for r_ in app.router.routes),
    )

    print("\n7. only genuinely restart-only settings are flagged")
    check(
        "channels and webhooks no longer need a restart",
        config.RESTART_REQUIRED_KEYS == frozenset({"HOST", "PORT", "LOG_LEVEL", "LOG_COLOR"}),
        str(sorted(config.RESTART_REQUIRED_KEYS)),
    )

    print(f"\n{'='*60}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


sys.exit(main_test())
