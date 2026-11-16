from __future__ import annotations

import asyncio
import json
import re
import logging
import secrets
import time

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from pw_channel import config
from pw_channel.auth.guards import check, resolve_token
from pw_channel.auth.sessions import InvalidSession
from pw_channel.db.core import DatabaseUnavailable
from pw_channel.observability import log_file, follow_lines, log_event, tail_lines
from pw_sdk.utils.auth import bearer as parse_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])

MAX_LINES = 5000

HEARTBEAT_SECS = 15.0


def _presented_token(authorization: str, token: str) -> str:
    if authorization.lower().startswith("bearer "):
        return parse_bearer(authorization)
    return (token or authorization).strip()


def _authorize(authorization: str = "", token: str = "") -> str:
    presented = _presented_token(authorization, token)
    if not presented:
        raise HTTPException(
            status_code=401,
            detail="Missing token. Send Authorization: Bearer <INTERNAL_LOG_TOKEN>.",
        )

    expected = config.INTERNAL_LOG_TOKEN
    if expected:
        if secrets.compare_digest(presented, expected):
            return "internal-token"
    try:
        user = resolve_token(presented)
    except InvalidSession:
        user = None
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=f"could not check your session: {e}")
    if user is not None:
        check(user, "logs.view")
        return user.email

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_LOG_TOKEN is not set on this server, so log access is "
            "disabled. Set it and restart.",
        )
    raise HTTPException(status_code=401, detail="That token is not valid.")


def _parse(line: str) -> dict:
    try:
        parsed = json.loads(line)
        return parsed if isinstance(parsed, dict) else {"msg": line, "level": "INFO"}
    except ValueError:
        return {"msg": line, "level": "INFO", "event": "unparsed"}


@router.get("/logs")
def read_logs(
    lines: int = Query(default=200, ge=1, le=MAX_LINES),
    level: str | None = Query(default=None, description="Only this level or worse"),
    contains: str | None = Query(default=None, description="Substring filter"),
    authorization: str = Header(default=""),
    token: str = Query(default=""),
):
    _authorize(authorization, token)

    raw = tail_lines(log_file(), lines)
    records = [_parse(line) for line in raw]

    if level:
        wanted = level.upper()
        ranking = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        floor = ranking.get(wanted, 0)
        records = [r for r in records if ranking.get(str(r.get("level", "")).upper(), 20) >= floor]

    if contains:
        needle = contains.lower()
        records = [r for r in records if needle in json.dumps(r).lower()]

    return {
        "file": str(log_file()),
        "count": len(records),
        "lines": records,
    }


def _log_files() -> list:
    from pathlib import Path

    base = Path(log_file())
    backups = sorted(base.parent.glob(base.name + ".*"), key=lambda p: p.stat().st_mtime)
    return [p for p in backups if p.suffix.lstrip(".").isdigit()] + ([base] if base.exists() else [])


def _call_records():
    for path in _log_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"call_id"' not in line:
                    continue
                record = _parse(line.strip())
                if record.get("call_id"):
                    yield record


_REF = re.compile(r"ref_id['\"]?\s*[=:]\s*['\"]?([0-9a-f]{8}-[0-9a-f-]{27})")
_MENTIONED_CALL = re.compile(r"'call_id':\s*'([^']+)'")


def _call_groups() -> tuple[dict[str, str], dict[str, list[dict]]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    records: dict[str, list[dict]] = {}
    for r in _call_records():
        cid = r["call_id"]
        records.setdefault(cid, []).append(r)
        find(cid)
        text = str(r.get("msg", ""))
        refs = set(_REF.findall(text))
        if r.get("ref_id"):
            refs.add(str(r["ref_id"]))
        for ref in refs:
            union(cid, f"ref:{ref}")
        for other in _MENTIONED_CALL.findall(text):
            union(cid, other)

    ids = list(records)
    for short in ids:
        for long in ids:
            if long != short and long.endswith("-" + short):
                union(short, long)

    groups: dict[str, list[dict]] = {}
    for cid, lines in records.items():
        groups.setdefault(find(cid), []).extend(lines)
    owner = {cid: find(cid) for cid in records}
    return owner, groups


def _main_id(lines: list[dict]) -> str:
    counts: dict[str, int] = {}
    for r in lines:
        counts[r["call_id"]] = counts.get(r["call_id"], 0) + 1
    return max(counts, key=counts.get)


@router.get("/logs/calls")
def logged_calls(
    limit: int = Query(default=200, ge=1, le=1000),
    authorization: str = Header(default=""),
    token: str = Query(default=""),
):
    _authorize(authorization, token)
    _, groups = _call_groups()
    out = []
    for lines in groups.values():
        lines.sort(key=lambda r: r.get("ts", ""))
        out.append({
            "id": _main_id(lines),
            "channel": next((r.get("channel") for r in lines if r.get("channel")), ""),
            "first": lines[0].get("ts", ""),
            "last": lines[-1].get("ts", ""),
            "count": len(lines),
            "errors": sum(1 for r in lines if str(r.get("level", "")).upper() in ("ERROR", "CRITICAL")),
        })
    out.sort(key=lambda c: c["last"], reverse=True)
    return {"calls": out[:limit]}


@router.get("/logs/calls/{call_id}")
def call_log(
    call_id: str,
    authorization: str = Header(default=""),
    token: str = Query(default=""),
):
    _authorize(authorization, token)
    owner, groups = _call_groups()
    lines = sorted(groups.get(owner.get(call_id, ""), []), key=lambda r: r.get("ts", ""))
    ids = sorted({r["call_id"] for r in lines})
    return {"callId": call_id, "ids": ids, "count": len(lines), "lines": lines[-MAX_LINES:]}


@router.get("/logs/stream")
async def stream_logs(
    request: Request,
    lines: int = Query(default=100, ge=0, le=MAX_LINES),
    authorization: str = Header(default=""),
    token: str = Query(default=""),
):
    who = _authorize(authorization, token)

    async def events():
        yield "retry: 3000\n\n"

        for line in tail_lines(log_file(), lines):
            yield f"event: log\ndata: {line}\n\n"

        yield f"event: ready\ndata: {json.dumps({'file': str(log_file())})}\n\n"

        last_beat = time.monotonic()
        follower = follow_lines(log_file(), from_end=True)
        try:
            async for line in follower:
                if line is not None:
                    yield f"event: log\ndata: {line}\n\n"
                    continue

                if await request.is_disconnected():
                    break

                now = time.monotonic()
                if now - last_beat >= HEARTBEAT_SECS:
                    yield ": keep-alive\n\n"
                    last_beat = now
        except asyncio.CancelledError:
            raise
        finally:
            await follower.aclose()
            log_event("logs.stream.closed", viewer=who)

    log_event("logs.stream.opened", viewer=who, tail=lines)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
