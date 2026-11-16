import logging
import re
from pathlib import Path

from pw_channel.db.core import connection

logger = logging.getLogger(__name__)
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    namespace TEXT NOT NULL,
    version TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (namespace, version)
)
"""


def pending(directory: Path, applied: set[str]) -> list[Path]:
    files = sorted(path for path in directory.glob("*.sql") if _NAME.match(path.name))
    return [path for path in files if path.stem not in applied]


def migrate(namespace: str, directory: Path) -> list[str]:
    done: list[str] = []
    with connection() as conn:
        conn.execute(LEDGER)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"migrate:{namespace}",))
        rows = conn.execute("SELECT version FROM schema_migrations WHERE namespace = %s", (namespace,)).fetchall()
        applied = {row["version"] for row in rows}
        for path in pending(directory, applied):
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (namespace, version) VALUES (%s, %s)", (namespace, path.stem))
            done.append(path.stem)
            logger.info(f"[db] {namespace}: applied {path.name}")
    return done
