import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from pw_channel.auth import SessionUser
from pw_channel.db import brain_history
from pw_channel.db import call_data
from pw_channel.db.brain_history import BrainUnavailable
from pw_channel.db.call_data import UnknownTable
from pw_channel.db.core import DatabaseUnavailable, is_configured, redacted_url
from pw_channel.auth.guards import require

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/data", tags=["dashboard"])

NO_DB = (
    "DATABASE_URL is not set for this container, so no call data is being stored. "
    "Point it at Postgres and restart to see rows here."
)

REMOTE = brain_history.TABLE


class PurgeRequest(BaseModel):
    olderThanDays: int = Field(default=0, ge=0, le=3650)


def _guard() -> None:
    if not is_configured():
        raise HTTPException(status_code=409, detail=NO_DB)


def _known(name: str) -> str:
    if name == REMOTE:
        return name
    try:
        call_data.spec(name)
    except UnknownTable as e:
        raise HTTPException(status_code=404, detail=str(e))
    return name


def _remote_down(e: BrainUnavailable) -> HTTPException:
    return HTTPException(status_code=502, detail=str(e))


@router.get("")
async def tables(_: SessionUser = Depends(require("data.view"))):
    cards = []
    error = ""
    if is_configured():
        try:
            cards = await run_in_threadpool(call_data.overview)
        except DatabaseUnavailable as e:
            error = str(e)
    else:
        error = NO_DB

    if brain_history.enabled():
        try:
            cards.append(await brain_history.summary())
        except BrainUnavailable as e:
            cards.append(brain_history.unreachable_card(str(e)))

    return {"tables": cards, "database": redacted_url(), "error": error}


@router.get("/{table}")
async def table_rows(
    table: str,
    limit: int = 50,
    offset: int = 0,
    q: str = "",
    _: SessionUser = Depends(require("data.view")),
):
    if _known(table) == REMOTE:
        try:
            return await brain_history.read(limit=limit, offset=offset, term=q)
        except BrainUnavailable as e:
            raise _remote_down(e)

    _guard()
    try:
        return await run_in_threadpool(
            call_data.read, table, limit=limit, offset=offset, term=q
        )
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/{table}/{row_id}")
async def table_row(table: str, row_id: int, _: SessionUser = Depends(require("data.view"))):
    if _known(table) == REMOTE:
        try:
            return await brain_history.row(row_id)
        except BrainUnavailable as e:
            raise _remote_down(e)

    _guard()
    try:
        found = await run_in_threadpool(call_data.row, table, row_id)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if found is None:
        raise HTTPException(status_code=404, detail=f"no row {row_id} in {table}")
    return {"table": table, "row": found}


@router.delete("/{table}/{row_id}")
async def delete_table_row(table: str, row_id: int, user: SessionUser = Depends(require("data.delete"))):
    if _known(table) == REMOTE:
        try:
            result = await brain_history.delete_row(row_id)
        except BrainUnavailable as e:
            raise _remote_down(e)
        logger.info(f"[data] {user.email} deleted {REMOTE} row {row_id}")
        return result

    _guard()
    try:
        result = await run_in_threadpool(call_data.delete_row, table, row_id)
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not result["deleted"]:
        raise HTTPException(status_code=404, detail=f"no row {row_id} in {table}")

    logger.info(f"[data] {user.email} deleted {table} row {row_id}")
    extra = ", ".join(f"{count} {name}" for name, count in result["cascaded"].items())
    return {
        **result,
        "message": f"Row {row_id} deleted from {table}"
        + (f", and {extra} went with it." if extra else "."),
    }


@router.post("/purge")
async def purge_everything(req: PurgeRequest, user: SessionUser = Depends(require("data.delete"))):
    _guard()
    try:
        removed = await run_in_threadpool(
            call_data.purge_all, older_than_days=req.olderThanDays
        )
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    note = ""
    if brain_history.enabled():
        try:
            result = await brain_history.purge(older_than_days=req.olderThanDays)
            removed[REMOTE] = result.get("removed", 0)
        except BrainUnavailable as e:
            note = f" {REMOTE} was left alone ({e})"

    total = sum(removed.values())
    scope = f"older than {req.olderThanDays} days" if req.olderThanDays else "in every voice table"
    logger.warning(f"[data] {user.email} purged all call data ({scope}): {removed}")
    return {
        "removed": removed,
        "total": total,
        "message": f"{total} row(s) deleted {scope}." + note,
    }


@router.post("/{table}/purge")
async def purge_table(table: str, req: PurgeRequest, user: SessionUser = Depends(require("data.delete"))):
    if _known(table) == REMOTE:
        try:
            result = await brain_history.purge(older_than_days=req.olderThanDays)
        except BrainUnavailable as e:
            raise _remote_down(e)
        logger.warning(f"[data] {user.email} purged {REMOTE}: {result.get('removed')} row(s)")
        return result

    _guard()
    try:
        removed = await run_in_threadpool(
            call_data.purge, table, older_than_days=req.olderThanDays
        )
    except DatabaseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    scope = f" older than {req.olderThanDays} days" if req.olderThanDays else ""
    logger.warning(f"[data] {user.email} purged {table}{scope}: {removed} row(s)")
    return {
        "table": table,
        "removed": removed,
        "message": f"{removed} row(s) deleted from {table}{scope}.",
    }
