import logging
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from pw_channel.channels.whatsapp.settings import settings
from pw_sdk.utils.auth import same_secret
from pw_channel.channels.whatsapp.campaigns.store import (
    campaign_store,
    CampaignConflictError,
    CampaignValidationError,
    CampaignStoreUnavailable,
    IMAGE_ROUTE_PREFIX,
    MAX_IMAGE_BYTES,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trigger-campaigns"])

_PAGE_PATH = Path(__file__).resolve().parent / "campaigns.html"


async def verify_admin_secret(x_admin_secret: str = Header(default="")):
    if not same_secret(settings.admin_secret, x_admin_secret):
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing X-Admin-Secret")


async def ensure_store():
    try:
        await campaign_store.connect()
    except CampaignStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Campaigns database unavailable: {e}")


class CampaignIn(BaseModel):
    name: str = Field(default="", max_length=120)
    karix_numbers: List[str] = Field(default_factory=list)
    all_numbers: bool = False
    trigger_words: List[str] = Field(min_length=1)
    message: str = Field(min_length=1)
    image_url: str = Field(default="", max_length=2000)
    is_active: bool = True


@router.get("/admin/campaigns", include_in_schema=False)
async def campaigns_page():
    if not _PAGE_PATH.exists():
        raise HTTPException(status_code=500, detail="Admin page not found")
    return FileResponse(str(_PAGE_PATH), media_type="text/html")


@router.get("/api/trigger/numbers", dependencies=[Depends(verify_admin_secret)])
async def get_campaign_numbers():
    karix = settings.karix_numbers_list
    nowonextel = settings.nowonextel_numbers_list
    meta = settings.meta_numbers_list
    numbers = settings.campaign_numbers_list

    def platform(n: str) -> str:
        if n in karix:
            return "karix"
        if n in nowonextel:
            return "nowonextel"
        return "meta"

    platforms = {n: platform(n) for n in numbers}
    return {
        "numbers": numbers,
        "karix_numbers": karix,
        "nowonextel_numbers": nowonextel,
        "meta_numbers": meta,
        "platforms": platforms,
    }


@router.get("/api/trigger/campaigns", dependencies=[Depends(verify_admin_secret), Depends(ensure_store)])
async def list_campaigns(karix_number: Optional[str] = Query(default=None)):
    return {"campaigns": await campaign_store.list_campaigns(karix_number)}


@router.get("/api/trigger/campaigns/{campaign_id}", dependencies=[Depends(verify_admin_secret), Depends(ensure_store)])
async def get_campaign(campaign_id: int):
    campaign = await campaign_store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/api/trigger/campaigns", dependencies=[Depends(verify_admin_secret), Depends(ensure_store)], status_code=201)
async def create_campaign(payload: CampaignIn):
    try:
        return await campaign_store.create_campaign(
            karix_numbers=payload.karix_numbers,
            all_numbers=payload.all_numbers,
            trigger_words=payload.trigger_words,
            message=payload.message,
            name=payload.name,
            is_active=payload.is_active,
            image_url=payload.image_url,
        )
    except CampaignValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CampaignConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/api/trigger/campaigns/{campaign_id}", dependencies=[Depends(verify_admin_secret), Depends(ensure_store)])
async def update_campaign(campaign_id: int, payload: CampaignIn):
    try:
        updated = await campaign_store.update_campaign(
            campaign_id=campaign_id,
            karix_numbers=payload.karix_numbers,
            all_numbers=payload.all_numbers,
            trigger_words=payload.trigger_words,
            message=payload.message,
            name=payload.name,
            is_active=payload.is_active,
            image_url=payload.image_url,
        )
    except CampaignValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CampaignConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return updated


@router.delete("/api/trigger/campaigns/{campaign_id}", dependencies=[Depends(verify_admin_secret), Depends(ensure_store)])
async def delete_campaign(campaign_id: int):
    if not await campaign_store.delete_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"message": f"Campaign {campaign_id} deleted"}


@router.post(
    "/api/trigger/images",
    dependencies=[Depends(verify_admin_secret), Depends(ensure_store)],
    status_code=201,
)
async def upload_campaign_image(file: UploadFile = File(...)):
    content = await file.read()
    try:
        meta = await campaign_store.save_image(content, filename=file.filename or "")
    except CampaignValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    base = settings.public_base_url.rstrip("/")
    if not base:
        raise HTTPException(
            status_code=500,
            detail="PUBLIC_BASE_URL is not configured, so uploaded images cannot be "
                   "given a public link. Set it to this service's public address.",
        )

    return {
        "url": f"{base}{IMAGE_ROUTE_PREFIX}{meta['id']}",
        "id": meta["id"],
        "content_type": meta["content_type"],
        "byte_size": meta["byte_size"],
        "filename": meta["filename"],
        "max_bytes": MAX_IMAGE_BYTES,
    }


@router.get(IMAGE_ROUTE_PREFIX + "{image_id}", include_in_schema=False)
async def serve_campaign_image(image_id: str):
    try:
        image = await campaign_store.get_image(image_id)
    except CampaignStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Campaigns database unavailable: {e}")
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(
        content=image["content"],
        media_type=image["content_type"],
        headers={"Cache-Control": "public, max-age=86400"},
    )
