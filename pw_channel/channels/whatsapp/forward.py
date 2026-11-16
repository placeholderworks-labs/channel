import asyncio
import logging

from pw_channel.channels.whatsapp.settings import settings
from pw_sdk.utils import http

logger = logging.getLogger(__name__)

FORWARDED_HEADER = "X-Dev-Forwarded"


def target_for(provider_name: str, from_number: str, to_number: str) -> str | None:
    suffix = "" if provider_name == "meta" else f"/{provider_name}"
    tunnel = settings.dev_tunnel_map.get(from_number)
    if tunnel:
        return f"{tunnel.rstrip('/')}{suffix}"
    if settings.staging_webhook_url and from_number in settings.staging_numbers_list:
        staging_karix = settings.staging_karix_number.strip().lstrip("+")
        if provider_name == "karix" and staging_karix and to_number != staging_karix:
            return None
        return f"{settings.staging_webhook_url.rstrip('/')}{suffix}"
    return None


async def _post(url: str, payload: dict, headers: dict) -> None:
    try:
        response = await http.request("POST", url, json=payload, headers={FORWARDED_HEADER: "true", **headers},
                                      retries=0, timeout=10.0)
        logger.info(f"[whatsapp] forwarded webhook to {url}: HTTP {response.status_code}")
    except Exception as error:
        logger.error(f"[whatsapp] could not forward webhook to {url}: {error}")


def forward(url: str, payload: dict, headers: dict | None = None) -> None:
    asyncio.create_task(_post(url, payload, headers or {}))
