import logging
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
NAMESPACE = "channel"


class DatabaseUnavailable(RuntimeError):
    pass


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def is_configured() -> bool:
    return bool(database_url())


def require_url() -> str:
    url = database_url()
    if not url:
        raise DatabaseUnavailable("DATABASE_URL is not set, e.g. postgresql://user:pass@host:5432/pw_channel")
    return url


def redacted_url(url: str | None = None) -> str:
    url = database_url() if url is None else url
    if not url:
        return ""
    parts = urlparse(url)
    if parts.password:
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        parts = parts._replace(netloc=f"{parts.username}:***@{host}")
    return urlunparse(parts)


@contextmanager
def connection(*, autocommit: bool = False):
    url = require_url()
    try:
        conn = psycopg.connect(url, autocommit=autocommit, row_factory=dict_row, connect_timeout=10)
    except psycopg.Error as error:
        raise DatabaseUnavailable(str(error)) from error
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()


def ensure_database() -> None:
    url = require_url()
    parts = urlparse(url)
    name = (parts.path or "").lstrip("/")
    if not name:
        raise DatabaseUnavailable(f"DATABASE_URL has no database name: {redacted_url()}")
    try:
        psycopg.connect(url, connect_timeout=10).close()
        return
    except psycopg.OperationalError as error:
        if "does not exist" not in str(error):
            raise DatabaseUnavailable(str(error)) from error
    admin = urlunparse(parts._replace(path="/postgres"))
    logger.info(f"[db] database {name!r} missing, creating it")
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=10) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
    except psycopg.errors.DuplicateDatabase:
        pass
    except psycopg.Error as error:
        raise DatabaseUnavailable(f"could not create database {name!r}: {error}") from error


def init_database() -> list[str]:
    from pw_channel.db.migrate import migrate

    ensure_database()
    applied = migrate(NAMESPACE, MIGRATIONS)
    logger.info(f"[db] schema ready at {redacted_url()} ({len(applied)} migration(s) applied)")
    return applied
