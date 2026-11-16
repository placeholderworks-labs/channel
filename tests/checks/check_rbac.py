import os
import pathlib
import re
import sys
from contextlib import contextmanager

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ["DASHBOARD_API_ENCRYPTION"] = "off"
os.environ["USE_DB"] = "true"

import psycopg
from fastapi.testclient import TestClient

from pw_channel import config
from pw_channel.db.core import connection, database_url, init_database

PASS, FAIL = [], []
PREFIX = "zz-test-"
ROLE = "zz_test_role"
OUTBOX: list[dict] = []
MAIL = {"ok": True}


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")


def fake_send(to, subject, text, html_body):
    OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html_body})
    return (True, None) if MAIL["ok"] else (False, "SMTPException: test outage")


def reachable() -> bool:
    try:
        psycopg.connect(database_url(), connect_timeout=5).close()
        return True
    except Exception:
        return False


def cleanup():
    from pw_channel.auth import roles
    from pw_channel.auth import users

    with connection() as conn:
        conn.execute("DELETE FROM dashboard_users WHERE email LIKE %s", (PREFIX + "%",))
        conn.execute("DELETE FROM roles WHERE name LIKE %s", ("zz_test%",))
        conn.execute("DELETE FROM qms_intakes WHERE id LIKE %s", ("zz_test%",))
        conn.execute("DELETE FROM access_requests WHERE email LIKE %s", (PREFIX + "%",))
    roles.invalidate()
    users.forget()


def make_user(role: str, tag: str):
    from pw_channel.auth import SessionUser, hash_password, issue_token

    email = f"{PREFIX}{tag}@example.com"
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO dashboard_users (email, name, password_hash, role)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (email, tag, hash_password("zz-test-password"), role),
        ).fetchone()
    user = SessionUser(id=row["id"], email=email, name=tag, role=role)
    return user, {"Authorization": f"Bearer {issue_token(user)[0]}"}


@contextmanager
def one_transaction():
    from pw_channel.auth import users

    conn = psycopg.connect(database_url(), row_factory=psycopg.rows.dict_row)
    original = users.connection

    @contextmanager
    def shared(**_):
        yield conn

    users.connection = shared
    try:
        yield conn
    finally:
        users.connection = original
        conn.rollback()
        conn.close()
        users.forget()


def main_test():
    from pw_channel.channels.email import mailer

    mailer.send = fake_send

    import main
    from pw_channel.auth import roles
    from pw_channel.auth import users
    from pw_channel.auth.permissions import KEYS, Rejected

    init_database()
    roles.ensure_default_roles()
    cleanup()
    client = TestClient(main.app)

    sup, SUP = make_user("super_admin", "super")
    adm, ADM = make_user("admin", "admin")
    view, VIEW = make_user("viewer", "viewer")
    op, OP = make_user("operator", "operator")

    print("\n1. /me carries role, label and permissions")
    r = client.get("/api/admin/me", headers=VIEW)
    me = r.json()
    check("200", r.status_code == 200, r.text[:120])
    check(
        "every field the UI needs",
        set(me) == {"id", "email", "name", "role", "roleLabel", "permissions", "mustChangePassword", "orgId", "orgName", "agents"},
        str(sorted(me)),
    )
    check("viewer has 8 permissions", len(me["permissions"]) == 8, str(me["permissions"]))
    r = client.get("/api/admin/me", headers=SUP)
    check("super admin holds the whole catalog", set(r.json()["permissions"]) == KEYS)
    check("no token is 401", client.get("/api/admin/me").status_code == 401)

    print("\n2. a missing permission is a 403 that names it")
    r = client.put("/api/admin/settings", json={"values": {}}, headers=VIEW)
    check("viewer cannot edit settings", r.status_code == 403, str(r.status_code))
    check(
        "and is told which permission",
        r.json().get("detail") == "You need the 'Edit settings' permission",
        r.text,
    )
    check("viewer cannot see the team", client.get("/api/admin/users", headers=VIEW).status_code == 403)
    check("operator can see the team", client.get("/api/admin/users", headers=OP).status_code == 200)
    check(
        "operator cannot invite",
        client.post("/api/admin/users", json={"email": PREFIX + "x@example.com"}, headers=OP).status_code == 403,
    )
    check("viewer cannot place calls", client.post("/api/admin/calls", json={"channel": "acefone"}, headers=VIEW).status_code == 403)
    check("viewer cannot open the playground", client.get("/api/admin/playground", headers=VIEW).status_code == 403)
    check("viewer cannot delete data", client.delete("/api/admin/data/zz_none/1", headers=VIEW).status_code == 403)
    check("viewer cannot reveal secrets", client.get("/api/admin/settings/X/reveal", headers=VIEW).status_code == 403)
    check("viewer may read status", client.get("/api/admin/status", headers=VIEW).status_code == 200)
    check("admin cannot manage roles", client.post("/api/admin/roles", json={"name": "zz_test_x"}, headers=ADM).status_code == 403)

    print("\n3. super admin protections")
    r = client.patch(f"/api/admin/users/{sup.id}", json={"name": "nope"}, headers=ADM)
    check("admin cannot edit a super admin", r.status_code == 403, r.text)
    r = client.delete(f"/api/admin/users/{sup.id}", headers=ADM)
    check("admin cannot delete a super admin", r.status_code == 403, r.text)
    r = client.patch(f"/api/admin/users/{view.id}", json={"role": "super_admin"}, headers=ADM)
    check("admin cannot grant super admin", r.status_code == 403, r.text)
    r = client.post("/api/admin/users", json={"email": PREFIX + "s2@example.com", "role": "super_admin"}, headers=ADM)
    check("admin cannot invite a super admin", r.status_code == 403, r.text)
    r = client.put("/api/admin/roles/super_admin", json={"permissions": ["overview.view"]}, headers=SUP)
    check("the super_admin role is immutable", r.status_code == 403, r.text)
    check("even its label", client.put("/api/admin/roles/super_admin", json={"label": "x"}, headers=SUP).status_code == 403)
    check("nobody deletes their own account", client.delete(f"/api/admin/users/{sup.id}", headers=SUP).status_code == 403)
    check("nobody demotes themselves", client.patch(f"/api/admin/users/{adm.id}", json={"role": "viewer"}, headers=ADM).status_code == 403)
    check("nobody deactivates themselves", client.patch(f"/api/admin/users/{adm.id}", json={"isActive": False}, headers=ADM).status_code == 403)
    r = client.patch(f"/api/admin/users/{view.id}", json={"role": "operator", "name": "Viewer Two"}, headers=ADM)
    check("admin can change an operator-level user", r.status_code == 200 and r.json()["user"]["role"] == "operator", r.text)
    client.patch(f"/api/admin/users/{view.id}", json={"role": "viewer"}, headers=ADM)

    before = roles.all_roles()["admin"]["permissions"]
    r = client.put("/api/admin/roles/admin", json={"permissions": [k for k in before if k != "data.delete"]}, headers=SUP)
    check("super admin can narrow the admin role", r.status_code == 200 and "data.delete" not in r.json()["role"]["permissions"], r.text)
    r = client.delete("/api/admin/data/zz_none/1", headers=ADM)
    check("which bites immediately", r.status_code == 403, f"{r.status_code} {r.text[:80]}")
    client.put("/api/admin/roles/admin", json={"permissions": before}, headers=SUP)
    check("admin role restored", roles.all_roles()["admin"]["permissions"] == before)

    print("\n4. there is always an active super admin")
    sup2, _ = make_user("super_admin", "super2")
    with one_transaction() as conn:
        conn.execute(
            "UPDATE dashboard_users SET is_active = FALSE WHERE role = 'super_admin' AND email NOT LIKE %s",
            (PREFIX + "%",),
        )
        conn.execute("UPDATE dashboard_users SET is_active = FALSE WHERE id = %s", (sup2.id,))
        try:
            users.update_user(actor=sup2, user_id=sup.id, role="admin")
            check("demoting the last super admin is refused", False, "it went through")
        except Rejected as e:
            check("demoting the last super admin is refused", e.status_code == 409, e.detail)
        for label, call in (
            ("deactivating", lambda: users.update_user(actor=sup2, user_id=sup.id, is_active=False)),
            ("deleting", lambda: users.delete_user(actor=sup2, user_id=sup.id)),
        ):
            try:
                call()
                check(f"{label} the last super admin is refused", False, "it went through")
            except Rejected as e:
                check(f"{label} the last super admin is refused", e.status_code == 409, e.detail)
    r = client.patch(f"/api/admin/users/{sup2.id}", json={"role": "admin"}, headers=SUP)
    check("with another one active, demotion is fine", r.status_code == 200, r.text)

    print("\n5. role CRUD")
    body = {"name": ROLE, "label": "ZZ test", "description": "throwaway", "permissions": ["overview.view", "team.view"]}
    r = client.post("/api/admin/roles", json=body, headers=SUP)
    check("create is 201", r.status_code == 201, r.text)
    check("duplicate is 409", client.post("/api/admin/roles", json=body, headers=SUP).status_code == 409)
    check("bad slug is 400", client.post("/api/admin/roles", json={**body, "name": "Bad-Name"}, headers=SUP).status_code == 400)
    check("unknown permission is 400", client.post("/api/admin/roles", json={**body, "name": "zz_test_b", "permissions": ["nope.x"]}, headers=SUP).status_code == 400)
    r = client.get("/api/admin/roles", headers=VIEW)
    check("viewer cannot list roles", r.status_code == 403)
    r = client.get("/api/admin/roles", headers=OP)
    data = r.json()
    check("catalog has 19 permissions", len(data.get("catalog", [])) == 19)
    mine = next((x for x in data.get("roles", []) if x["name"] == ROLE), None)
    check("listed with its fields", mine is not None and {"label", "permissions", "isSystem", "userCount", "updatedAt", "updatedBy"} <= set(mine), str(mine))
    r = client.put(f"/api/admin/roles/{ROLE}", json={"label": "ZZ renamed", "permissions": ["overview.view"]}, headers=SUP)
    check("update", r.status_code == 200 and r.json()["role"]["label"] == "ZZ renamed", r.text)

    MAIL["ok"] = True
    r = client.post("/api/admin/users", json={"email": PREFIX + "holder@example.com", "role": ROLE, "sendInvite": False}, headers=SUP)
    holder = r.json()["user"]["id"]
    r = client.delete(f"/api/admin/roles/{ROLE}", headers=SUP)
    check("in-use delete is 409", r.status_code == 409, r.text)
    check("and says how many", "1 user" in r.json().get("detail", ""), r.text)
    check("system role delete is 409", client.delete("/api/admin/roles/admin", headers=SUP).status_code == 409)
    client.delete(f"/api/admin/users/{holder}", headers=SUP)
    check("unused delete is ok", client.delete(f"/api/admin/roles/{ROLE}", headers=SUP).status_code == 200)

    print("\n6. invite: temp password back only when the email didn't go")
    MAIL["ok"] = False
    OUTBOX.clear()
    r = client.post("/api/admin/users", json={"email": PREFIX.upper() + "Invitee@Example.com", "name": "Invitee", "role": "operator"}, headers=ADM)
    j = r.json()
    check("201", r.status_code == 201, r.text)
    check("email lowercased", j["user"]["email"] == PREFIX + "invitee@example.com", j["user"]["email"])
    check("emailed is false", j["emailed"] is False and j["emailError"], str(j))
    temp = j.get("tempPassword") or ""
    check("tempPassword is returned and strong", len(temp) >= 14, temp and f"{len(temp)} chars")
    check("must change password", j["user"]["mustChangePassword"] is True)
    check("invitedBy recorded", j["user"]["invitedBy"] == adm.email)
    check("a send was attempted", len(OUTBOX) == 1)
    check("duplicate email is 409", client.post("/api/admin/users", json={"email": PREFIX + "invitee@example.com"}, headers=ADM).status_code == 409)

    MAIL["ok"] = True
    OUTBOX.clear()
    r = client.post("/api/admin/users", json={"email": PREFIX + "mailed@example.com", "role": "viewer"}, headers=ADM)
    j = r.json()
    check("mailed invite hides the password", j["emailed"] is True and j["tempPassword"] is None, str(j))
    check("and the email carries URL and password", OUTBOX and mailer.dashboard_url() in OUTBOX[0]["text"] and "Temporary password" in OUTBOX[0]["text"])
    check("unknown role is 400", client.post("/api/admin/users", json={"email": PREFIX + "r@example.com", "role": "zz_nope"}, headers=ADM).status_code == 400)

    print("\n7. first sign-in needs the emailed code, then must_change_password is cleared")
    MAIL["ok"] = True
    OUTBOX.clear()
    r = client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": temp})
    step = r.json()
    check("password step asks for a code", r.status_code == 200 and step.get("otpRequired") is True and "token" not in step, r.text[:160])
    check("and emails it", len(OUTBOX) == 1 and OUTBOX[0]["to"] == PREFIX + "invitee@example.com")
    code = re.search(r"\b(\d{6})\b", OUTBOX[0]["text"]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    r = client.post("/api/admin/login/verify", json={"challenge": step["challenge"], "code": wrong})
    check("a wrong code is 401 and says how many tries are left", r.status_code == 401 and "left" in r.json()["detail"], r.text)
    r = client.post("/api/admin/login/resend", json={"challenge": step["challenge"]})
    check("resend is held back for a while", r.status_code == 429, r.text)
    r = client.post("/api/admin/login/verify", json={"challenge": step["challenge"], "code": code})
    check("the right code signs in", r.status_code == 200, r.text[:120])
    login = r.json()
    r = client.post("/api/admin/login/verify", json={"challenge": step["challenge"], "code": code})
    check("a code works once", r.status_code == 401)
    r2 = client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": temp}).json()
    for _ in range(5):
        last = client.post("/api/admin/login/verify", json={"challenge": r2["challenge"], "code": wrong})
    check("five wrong codes end the challenge", "Start again" in last.json()["detail"], last.text)
    MAIL["ok"] = False
    r = client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": temp})
    check("no session when the code cannot be emailed", r.status_code == 503 and "token" not in r.text, r.text[:160])
    check("login user says change it", login["user"].get("mustChangePassword") is True, str(login.get("user")))
    check("login user carries permissions", "calls.place" in login["user"].get("permissions", []))
    hdr = {"Authorization": f"Bearer {login['token']}"}
    r = client.post("/api/admin/password", json={"currentPassword": temp, "newPassword": "zz-test-new-pass"}, headers=hdr)
    check("change password", r.status_code == 200, r.text)
    check("flag cleared", client.get("/api/admin/me", headers=hdr).json()["mustChangePassword"] is False)

    print("\n8. admin reset-password")
    MAIL["ok"] = False
    invitee = next(u for u in users.list_users() if u["email"] == PREFIX + "invitee@example.com")
    r = client.post(f"/api/admin/users/{invitee['id']}/reset-password", headers=ADM)
    j = r.json()
    check("returns the temp password when mail fails", r.status_code == 200 and len(j.get("tempPassword") or "") >= 14, str(j)[:160])
    check("flag set again", j["user"]["mustChangePassword"] is True)
    check("old password stops working", client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": "zz-test-new-pass"}).status_code == 401)

    print("\n9. forgot password never says who exists")
    MAIL["ok"] = True
    OUTBOX.clear()
    r = client.post("/api/admin/password/forgot", json={"email": PREFIX + "nobody@example.com"})
    check("unknown email is 200 ok", r.status_code == 200 and r.json() == {"ok": True}, r.text)
    check("and sends nothing", not OUTBOX)
    r = client.post("/api/admin/password/forgot", json={"email": PREFIX + "INVITEE@example.com"})
    check("known email is 200 ok", r.status_code == 200 and r.json() == {"ok": True}, r.text)
    check("and mails a reset link", len(OUTBOX) == 1 and OUTBOX[0]["to"] == PREFIX + "invitee@example.com", str([m["to"] for m in OUTBOX]))
    link = re.search(r"(\S+/reset\?token=(\S+))", OUTBOX[0]["text"])
    check("the email carries a one-time link", bool(link), OUTBOX[0]["text"][:200])
    token = link.group(2) if link else ""
    r = client.post("/api/admin/password/forgot", json={"email": PREFIX + "invitee@example.com"})
    check("a second ask within a minute is still 200", r.status_code == 200)
    check("but sends nothing", len(OUTBOX) == 1, str(len(OUTBOX)))
    r = client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": j["tempPassword"]})
    check("asking for a reset does not lock the account out", r.status_code == 200, r.text[:120])
    r = client.post("/api/admin/password/reset", json={"token": token, "newPassword": "short"})
    check("a short new password is refused", r.status_code == 400)
    r = client.post("/api/admin/password/reset", json={"token": token, "newPassword": "zz-test-reset-pass"})
    check("the link sets the new password", r.status_code == 200, r.text)
    r = client.post("/api/admin/password/reset", json={"token": token, "newPassword": "zz-test-other-pass"})
    check("the link works once", r.status_code == 400 and "already used" in r.text, r.text)
    check("the old password stops working",
          client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": j["tempPassword"]}).status_code == 401)
    check("the new one passes the password step",
          client.post("/api/admin/login", json={"email": PREFIX + "invitee@example.com", "password": "zz-test-reset-pass"}).status_code == 200)
    r = client.post("/api/admin/password/reset", json={"token": "made-up", "newPassword": "zz-test-other-pass"})
    check("a made-up link is refused", r.status_code == 400)

    print("\n10. deactivation and unknown roles take effect at once")
    r = client.patch(f"/api/admin/users/{op.id}", json={"isActive": False}, headers=ADM)
    check("deactivate", r.status_code == 200 and r.json()["user"]["isActive"] is False, r.text)
    check("their token is now 401", client.get("/api/admin/me", headers=OP).status_code == 401)
    with connection() as conn:
        conn.execute("UPDATE dashboard_users SET role = 'zz_gone' WHERE id = %s", (view.id,))
    users.forget()
    r = client.get("/api/admin/me", headers=VIEW)
    check("a role that doesn't exist reads as viewer", r.status_code == 200 and r.json()["role"] == "viewer", r.text[:120])

    print("\n11. log access needs logs.view")
    r = client.get("/internal/logs?lines=1", headers=VIEW)
    check("viewer can read logs", r.status_code == 200, str(r.status_code))
    with connection() as conn:
        conn.execute(
            "INSERT INTO roles (name, label, permissions) VALUES ('zz_test_nologs', 'x', '[\"overview.view\"]')"
        )
    roles.invalidate()
    _, NOLOG = make_user("zz_test_nologs", "nologs")
    r = client.get("/internal/logs?lines=1", headers=NOLOG)
    check("a role without it is 403", r.status_code == 403, r.text[:120])

    print("\n12. QMS intakes: their own fields, token and agent")
    _, OP = make_user("operator", "qms-operator")
    intake = {
        "id": "zz_test_intake", "name": "zz test intake", "agent": "zz-test-agent",
        "fields": [
            {"key": "hotel_name", "type": "text", "required": True},
            {"key": "nights", "type": "integer", "required": True, "min": 1},
            {"key": "room", "type": "enum", "options": ["deluxe", "suite"]},
        ],
    }
    r = client.post("/api/admin/qms/intakes", json=intake, headers=VIEW)
    check("a viewer cannot create an intake", r.status_code == 403, r.text[:120])
    r = client.post("/api/admin/qms/intakes", json={**intake, "fields": [{"key": "phone_number"}]}, headers=ADM)
    check("a base field cannot be redefined", r.status_code == 422, r.text[:120])
    r = client.post("/api/admin/qms/intakes", json=intake, headers=ADM)
    body = r.json() if r.status_code == 201 else {}
    check("an admin creates one and gets its token once", r.status_code == 201 and body.get("token", "").startswith("qms_"), r.text[:160])
    view_ = body.get("intake") or {}
    keys = [f["key"] for f in view_.get("allFields", [])]
    check("its fields are the base ones plus its own",
          keys[:3] == ["reference_id", "customer_name", "phone_number"] and {"hotel_name", "nights", "room"} <= set(keys), str(keys))
    check("its endpoint is its own", view_.get("path") == "/api/qms/zz_test_intake/calls", str(view_.get("path")))
    check("the sample request carries its required fields",
          {"hotel_name", "nights"} <= set((view_.get("samplePayload") or {}).keys()), str(view_.get("samplePayload")))
    r = client.get("/api/admin/qms/for-agent/zz-test-agent", headers=OP)
    check("a new intake is connected to nobody", r.status_code == 200 and r.json()["intakes"] == [], r.text[:160])
    conn = {"agent": "zz-test-agent", "delaySecs": 300, "callHoursStart": "09:00", "callHoursEnd": "21:00"}
    r = client.put("/api/admin/qms/intakes/zz_test_intake/connection", json=conn, headers=VIEW)
    check("a viewer cannot connect an agent", r.status_code == 403, r.text[:120])
    r = client.put("/api/admin/qms/intakes/zz_test_intake/connection", json={**conn, "callHoursEnd": ""}, headers=ADM)
    check("half-set calling hours are refused", r.status_code == 422, r.text[:120])
    r = client.put("/api/admin/qms/intakes/zz_test_intake/connection", json={**conn, "callHoursStart": "9am"}, headers=ADM)
    check("calling hours must be HH:MM", r.status_code == 422, r.text[:120])
    r = client.put("/api/admin/qms/intakes/zz_test_intake/connection", json=conn, headers=ADM)
    check("an agent editor connects it with its timing",
          r.status_code == 200 and r.json()["agent"] == "zz-test-agent" and r.json()["delaySecs"] == 300 and r.json()["callHoursStart"] == "09:00",
          r.text[:200])
    r = client.put("/api/admin/qms/intakes/zz_test_intake/connection", json={**conn, "pending": "later"}, headers=ADM)
    check("pending must be call or hold", r.status_code == 422, r.text[:120])
    r = client.put("/api/admin/qms/intakes/zz_test_intake/connection", json={**conn, "pending": "call"}, headers=ADM)
    body = r.json() if r.status_code == 200 else {}
    check("choosing to call held records with the agent not live releases nothing yet",
          r.status_code == 200 and body["released"]["released"] == 0 and body["releaseAfter"], r.text[:200])
    r = client.get("/api/admin/qms/catalog", headers=VIEW)
    check("the catalog lists every intake for the agent tab", r.status_code == 200 and "zz_test_intake" in [i["id"] for i in r.json()["intakes"]], r.text[:120])
    r = client.get("/api/admin/qms/for-agent/zz-test-agent", headers=OP)
    check("the agent's tests see that intake", r.status_code == 200 and [i["id"] for i in r.json()["intakes"]] == ["zz_test_intake"], r.text[:160])
    r = client.post("/api/admin/test-records", json={"intake": "zz_test_intake", "record": {"customer_name": "Asha", "hotel_name": "Taj"}}, headers=OP)
    check("a test record missing a required field is refused", r.status_code == 422 and "nights" in r.text, r.text[:160])
    r = client.post("/api/admin/test-records", json={"intake": "zz_test_intake", "record": {"customer_name": "Asha", "hotel_name": "Taj", "nights": 2, "room": "Suite"}}, headers=OP)
    facts = {f["key"]: f["value"] for f in r.json().get("facts", [])} if r.status_code == 200 else {}
    check("a complete one is held under a TEST- reference with its facts",
          r.status_code == 200 and r.json()["testRecord"].startswith("TEST-") and facts.get("hotel_name") == "Taj" and facts.get("nights") == 2,
          r.text[:200])
    r = client.post("/api/qms/zz_test_intake/calls", json={}, headers={"X-API-Key": "wrong"})
    check("its endpoint refuses another token", r.status_code in (401, 503), str(r.status_code))
    r = client.delete("/api/admin/qms/intakes/abandoned_cart", headers=ADM)
    check("the built-in intake cannot be deleted", r.status_code == 409, r.text[:120])
    r = client.delete("/api/admin/qms/intakes/zz_test_intake", headers=ADM)
    check("a custom intake can be deleted", r.status_code == 204, r.text[:120])


    print("\n13. asking for access the role does not have")
    from pw_channel.auth import roles as _roles
    _, ASK = make_user("viewer", "asker")
    viewer_perms = _roles.permissions_for("viewer")
    lacking = "settings.edit" if "settings.edit" not in viewer_perms else "roles.manage"
    having = sorted(viewer_perms)[0]
    OUTBOX.clear()
    r = client.post("/api/admin/access-requests", json={"permission": lacking, "page": "Settings", "note": "need it"}, headers=ASK)
    req = r.json().get("request", {}) if r.status_code == 201 else {}
    check("any signed-in user can ask for a permission", r.status_code == 201 and req.get("status") == "pending", r.text[:160])
    check("admins are emailed about it", any("asked for" in m["subject"] for m in OUTBOX), str([m["subject"] for m in OUTBOX])[:160])
    r = client.post("/api/admin/access-requests", json={"permission": lacking}, headers=ASK)
    check("asking again returns the pending request", r.status_code == 201 and r.json()["alreadyPending"] and r.json()["request"]["id"] == req.get("id"), r.text[:160])
    r = client.post("/api/admin/access-requests", json={"permission": having}, headers=ASK)
    check("asking for one the role already has is refused", r.status_code == 409, r.text[:120])
    r = client.post("/api/admin/access-requests", json={"permission": "nope.nope"}, headers=ASK)
    check("an unknown permission is refused", r.status_code == 422, r.text[:120])
    r = client.get("/api/admin/access-requests/mine", headers=ASK)
    check("people see their own requests and the catalog",
          r.status_code == 200 and r.json()["requests"][0]["permission"] == lacking and len(r.json()["catalog"]) > 5, r.text[:160])
    r = client.get("/api/admin/access-requests", headers=ADM)
    check("the team sees pending requests", r.status_code == 200 and req.get("id") in [x["id"] for x in r.json()["requests"]], r.text[:160])
    r = client.post(f"/api/admin/access-requests/{req.get('id')}/resolve", json={"status": "granted"}, headers=ASK)
    check("only a team manager can close a request", r.status_code == 403, r.text[:120])
    OUTBOX.clear()
    r = client.post(f"/api/admin/access-requests/{req.get('id')}/resolve", json={"status": "granted"}, headers=ADM)
    check("a team manager marks it granted", r.status_code == 200 and r.json()["request"]["status"] == "granted", r.text[:160])
    check("and the person who asked is emailed", any("was granted" in m["subject"] for m in OUTBOX), str([m["subject"] for m in OUTBOX])[:160])
    r = client.post(f"/api/admin/access-requests/{req.get('id')}/resolve", json={"status": "dismissed"}, headers=ADM)
    check("a closed request cannot be closed again", r.status_code == 404, r.text[:120])


if __name__ == "__main__":
    if not reachable():
        print(f"SKIP — {database_url() or 'DATABASE_URL'} is not reachable")
        sys.exit(0)
    try:
        main_test()
    finally:
        cleanup()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
