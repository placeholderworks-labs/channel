import pytest
from fastapi.testclient import TestClient

from pw_channel.intake import adapters, intakes, service
from pw_channel.orchestrator import service as journeys
from pw_channel.orchestrator.template import load_templates
from pw_sdk import config as client_config
from pw_channel.db.core import connection
from tests.fakes import DemoCartAdapter, install_fakes

TOKEN = "demo-intake-token"


@pytest.fixture
def client(db, monkeypatch):
    install_fakes()
    adapters.register("demo.cart", DemoCartAdapter())
    monkeypatch.setenv("DEMO_TOKEN", TOKEN)
    intakes.sync_from_config({
        "demo_cart": {"adapter": "demo.cart", "journey": "single_call", "agent": "callvoice", "token_env": "DEMO_TOKEN"},
        "demo_events": {"adapter": "demo.cart", "token_env": "DEMO_TOKEN"},
        "demo_fields": {"adapter": "builtin.fields", "journey": "single_call", "token_env": "DEMO_TOKEN",
                        "fields": [{"key": "city", "label": "City", "type": "text", "required": True}]},
    })
    journeys.use_templates(load_templates({}, {"voice", "whatsapp", "email"}))
    from pw_channel.app import create_app

    app = create_app(client_config.ClientConfig())
    yield TestClient(app)
    journeys.use_templates(None)


def post(client, path, body, token=TOKEN):
    return client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})


def test_records_flow_through_adapter_into_a_journey(client):
    response = post(client, "/api/intake/demo_cart/records", [
        {"cart_id": "C-1", "name": "Asha", "mobile": "+919812345678", "total": 15400},
        {"cart_id": "C-2", "name": "Ravi", "mobile": "12345", "total": 10},
    ])
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["accepted"] == 1 and body["rejected"] == 1
    first, second = body["results"]
    assert first["status"] == "scheduled" and first["journey_id"]
    assert second["status"] == "rejected" and second["errors"][0]["field"] == "customer.phone"
    with connection() as conn:
        event = conn.execute("SELECT * FROM ingestion_events WHERE reference_id = 'C-1'").fetchone()
        stored = conn.execute("SELECT canonical FROM records WHERE reference_id = 'C-1'").fetchone()
    assert event["adapter"] == "demo.cart" and event["adapter_version"] == "2.1.0" and event["schema_version"] == "1"
    assert event["payload"]["cart_id"] == "C-1" and event["canonical"]["customer"]["phone"] == "+919812345678"
    assert stored["canonical"]["cart"]["total"] == 15400


def test_auth_and_body_errors(client):
    assert post(client, "/api/intake/demo_cart/records", {"cart_id": "x"}, token="wrong").status_code == 401
    assert post(client, "/api/intake/missing/records", {}).status_code == 404
    response = client.post("/api/intake/demo_cart/records", content=b"not json", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 422 and "not valid JSON" in response.text


def test_adapter_crash_and_timeout_reject_without_breaking_server(client, monkeypatch):
    response = post(client, "/api/intake/demo_cart/records", [{"cart_id": "A", "mobile": "+919812345678", "boom": True}])
    assert response.status_code == 422 and "adapter failed" in response.json()["results"][0]["errors"][0]["error"]
    monkeypatch.setattr(service, "TRANSFORM_TIMEOUT_SECS", 0.2)
    response = post(client, "/api/intake/demo_cart/records", {"hang": True, "cart_id": "B", "mobile": "+919812345678"})
    assert response.status_code == 422 and response.json()["results"][0]["errors"][0]["error"] == "adapter timed out"
    assert client.get("/healthz").status_code == 200


def test_builtin_fields_adapter_and_legacy_path(client):
    response = post(client, "/api/qms/demo_fields/calls", {"customer_name": "Asha", "phone_number": "9812345678", "city": "Goa"})
    assert response.status_code == 202, response.text
    result = response.json()["results"][0]
    assert result["status"] == "scheduled" and result["reference_id"].startswith("DF-")
    with connection() as conn:
        canonical = conn.execute("SELECT canonical FROM records").fetchone()["canonical"]
    assert canonical["customer"]["phone"] == "+919812345678"
    assert canonical["facts"] == [{"key": "city", "label": "City", "value": "Goa", "speakable": True}]
    missing = post(client, "/api/intake/demo_fields/records", {"customer_name": "A", "phone_number": "9812345678"})
    assert missing.status_code == 422 and "city missing" in missing.text


def test_events_endpoint_records_outcomes(client):
    post(client, "/api/intake/demo_cart/records", {"cart_id": "C-9", "name": "Asha", "mobile": "+919812345678"})
    event = {"event_id": "E-1", "reference_id": "C-9", "kind": "booking.confirmed", "occurred_at": "2026-11-20T10:00:00+05:30"}
    response = post(client, "/api/intake/demo_events/events", [event, {"event_id": "E-2"}])
    assert response.status_code == 202, response.text
    results = response.json()["results"]
    assert results[0]["applied"] is True and results[1]["status"] == "rejected"
    journeys.process_events()
    with connection() as conn:
        status = conn.execute("SELECT status FROM journeys").fetchone()["status"]
    assert status == "converted"


def test_adapter_report_lists_builtins():
    report = adapters.report()
    assert "builtin.canonical" in report["loaded"] and "builtin.fields" in report["loaded"]
