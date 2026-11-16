import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from pw_channel import config
from pw_channel.intake import events as ingestion_events
from pw_channel.intake import intakes, service
from pw_sdk.utils.auth import bearer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intake", tags=["intake"])
legacy_router = APIRouter(tags=["intake"], include_in_schema=False)

RAW_PREVIEW = 4000


def authorise(intake_id: str, authorization: str | None, x_api_key: str | None) -> dict:
    intake = intakes.get(intake_id)
    if intake is None:
        raise HTTPException(status_code=404, detail=f"no intake {intake_id!r}")
    if not intake["tokenSet"]:
        raise HTTPException(status_code=503, detail="this intake has no API token yet")
    presented = bearer(authorization) if authorization else (x_api_key or "").strip()
    if not intakes.token_matches(intake_id, presented):
        logger.warning(f"[intake] {intake_id}: missing or invalid token")
        raise HTTPException(status_code=401, detail="invalid or missing API token")
    if not intake["enabled"]:
        raise HTTPException(status_code=503, detail=f"the {intake['name']} intake is switched off")
    return intake


async def read_body(request: Request, intake: dict) -> tuple[object | None, JSONResponse | None]:
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8")) if raw.strip() else None
    except (UnicodeDecodeError, ValueError):
        body, problem = None, "body is not valid JSON"
    else:
        if isinstance(body, (dict, list)) and body:
            problem = None
        elif body in ({}, []):
            problem = "body is empty; send a record or an array of records"
        else:
            problem = "body must be a JSON object or a non-empty array"
    if problem is None and isinstance(body, list) and len(body) > config.INGESTION_MAX_BATCH:
        problem = f"batch larger than {config.INGESTION_MAX_BATCH} records"
    if problem is None:
        return body, None
    client_ip = request.client.host if request.client else ""
    event_id = ingestion_events.create(
        source_ip=client_ip, status="rejected", reason=problem, errors=[{"field": "", "error": problem}],
        payload={"_raw_body": raw.decode("utf-8", "replace")[:RAW_PREVIEW]}, source=intake["id"], intake=intake["id"],
    )
    return None, JSONResponse(status_code=422, content={"accepted": 0, "rejected": 1, "results": [
        {"index": 0, "ingestion_id": event_id, "status": "rejected", "errors": [{"field": "", "error": problem}]}]})


async def deliver_records(request: Request, intake_id: str, authorization: str | None, x_api_key: str | None):
    if not config.INGESTION_ENABLED:
        raise HTTPException(status_code=503, detail="ingestion is disabled (INGESTION_ENABLED=false)")
    intake = authorise(intake_id, authorization, x_api_key)
    body, problem = await read_body(request, intake)
    if problem:
        return problem
    delivery = await service.ingest_records(intake, body, source_ip=request.client.host if request.client else "")
    return JSONResponse(status_code=delivery.status_code(), content=delivery.body())


@router.post("/{intake_id}/records")
async def post_records(intake_id: str, request: Request, authorization: str | None = Header(default=None),
                       x_api_key: str | None = Header(default=None)):
    return await deliver_records(request, intake_id, authorization, x_api_key)


@router.post("/{intake_id}/events")
async def post_events(intake_id: str, request: Request, authorization: str | None = Header(default=None),
                      x_api_key: str | None = Header(default=None)):
    intake = authorise(intake_id, authorization, x_api_key)
    body, problem = await read_body(request, intake)
    if problem:
        return problem
    delivery = await service.ingest_events(intake, body)
    return JSONResponse(status_code=delivery.status_code(), content=delivery.body())


@router.get("/{intake_id}/status")
async def intake_status(intake_id: str, authorization: str | None = Header(default=None),
                        x_api_key: str | None = Header(default=None)):
    intake = authorise(intake_id, authorization, x_api_key)
    return {
        "intake": intake["id"],
        "adapter": intake["adapter"],
        "journey": intake["journey"],
        "enabled": intake["enabled"],
        "counts": ingestion_events.counts(source=intake["id"]),
    }


@legacy_router.post("/api/qms/{intake_id}/calls")
async def legacy_qms(intake_id: str, request: Request, authorization: str | None = Header(default=None),
                     x_api_key: str | None = Header(default=None)):
    return await deliver_records(request, intake_id, authorization, x_api_key)


@legacy_router.post("/api/ingestion/calls")
async def legacy_ingestion(request: Request, authorization: str | None = Header(default=None),
                           x_api_key: str | None = Header(default=None)):
    return await deliver_records(request, intakes.ABANDONED_CART, authorization, x_api_key)
