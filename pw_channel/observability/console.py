from __future__ import annotations

import logging
import os
import re
import sys
from contextlib import asynccontextmanager

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"

BOOT_LOGGER = "pw.boot"

_MUTED = ("httpx", "httpcore")

_ACCESS_STATUS = re.compile(r'"\s+(\d{3})\s*$')


def supports_color(stream=None) -> bool:
    mode = os.getenv("LOG_COLOR", "auto").strip().lower()
    if mode in ("always", "1", "true", "yes"):
        return True
    if mode in ("never", "0", "false", "no") or os.getenv("NO_COLOR"):
        return False
    try:
        return bool((stream or sys.stdout).isatty())
    except Exception:
        return False


def _tint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


class ConsoleFormatter(logging.Formatter):

    _TINT = {
        logging.CRITICAL: RED,
        logging.ERROR: RED,
        logging.WARNING: YELLOW,
    }

    def __init__(self, color: bool) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        if record.name == BOOT_LOGGER:
            return record.getMessage()
        text = super().format(record)
        tint = self._TINT.get(record.levelno)
        return _tint(text, tint, self.color) if tint else text


class ConsoleFilter(logging.Filter):

    def __init__(self) -> None:
        super().__init__()
        self.booting = True

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == BOOT_LOGGER:
            return True
        if record.levelno >= logging.WARNING:
            return True
        if record.name.startswith(_MUTED):
            return False
        if record.name == "uvicorn.access":
            match = _ACCESS_STATUS.search(record.getMessage())
            if match and match.group(1)[0] in "23":
                return False
        return not self.booting


FILTER = ConsoleFilter()

_errors_seen = 0


class ErrorCounter(logging.Handler):

    def emit(self, record: logging.LogRecord) -> None:
        global _errors_seen
        if record.levelno >= logging.ERROR:
            _errors_seen += 1


class Row:
    def __init__(self, label: str, detail: str = "", status: str = "") -> None:
        self.label = label
        self.detail = detail
        self.status = status


_rows: list[Row] = []


def note(label: str, detail: str) -> None:
    _rows.append(Row(label, detail))


@asynccontextmanager
async def step(label: str, detail: str = ""):
    row = Row(label, detail)
    before = _errors_seen
    try:
        yield row
    except Exception as exc:
        row.status = "FAIL"
        row.detail = " — ".join(x for x in (row.detail, f"{type(exc).__name__}: {exc}") if x)
        _rows.append(row)
        raise
    else:
        row.status = "ok" if _errors_seen == before else "FAIL"
        _rows.append(row)


def report() -> None:
    log = logging.getLogger(BOOT_LOGGER)
    color = supports_color()
    width = max((len(row.label) for row in _rows), default=9)

    failed = [row.label for row in _rows if row.status == "FAIL"]
    head = _tint(f"{os.getenv('COMPANY_NAME', 'PlaceholderWorks')} {os.getenv('PW_SERVICE', 'service')}", BOLD, color)
    if failed:
        head += "  " + _tint(f"{len(failed)} check(s) failed", RED, color)

    log.info("")
    log.info(head)
    for row in _rows:
        plain = row.status or "·"
        code = {"ok": GREEN, "FAIL": RED}.get(row.status, DIM)
        mark = _tint(plain, code, color) + " " * max(0, 4 - len(plain))
        log.info(f"  {row.label:<{width}}  {mark}  {row.detail}")
    log.info("")

    FILTER.booting = False
    _rows.clear()
