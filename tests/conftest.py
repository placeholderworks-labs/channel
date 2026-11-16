import os

import pytest

os.environ["USE_DB"] = "false"
os.environ["DASHBOARD_API_ENCRYPTION"] = "off"
os.environ["DATABASE_URL"] = ""
os.environ.setdefault("PW_CHAT_API_TOKEN", "test-token")
os.environ["ENABLED_CHANNELS"] = "voice,whatsapp,email"
os.environ["MAX_CONTACTS_PER_DAY"] = "0"
os.environ["CLIENT_TIMEZONE"] = "Asia/Kolkata"
os.environ["CLIENT_COUNTRY"] = "IN"

TABLES = (
    "journey_events", "task_deps", "journey_tasks", "journeys", "records", "outcome_events",
    "ingestion_events", "contact_blocks", "message_log", "qms_intakes",
)


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    pgserver = pytest.importorskip("pgserver")
    import psycopg

    server = pgserver.get_server(str(tmp_path_factory.mktemp("pg")), cleanup_mode="stop")
    base = server.get_uri()
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS pw_channel_test")
        conn.execute("CREATE DATABASE pw_channel_test")
    url = base.replace("/postgres?", "/pw_channel_test?")
    os.environ["DATABASE_URL"] = url
    from pw_channel.db.core import init_database

    init_database()
    os.environ["DATABASE_URL"] = ""
    yield url
    server.cleanup()


@pytest.fixture
def db(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from pw_channel.db.core import connection

    with connection() as conn:
        conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
    from pw_channel.intake import intakes

    intakes.invalidate()
    yield pg_url
    intakes.invalidate()
