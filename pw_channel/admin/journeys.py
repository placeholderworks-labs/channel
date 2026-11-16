import asyncio

from fastapi import APIRouter, Depends, HTTPException

from pw_channel.auth.guards import require
from pw_channel.intake import adapters
from pw_channel.orchestrator import service, store
from pw_channel.db.core import is_configured

router = APIRouter(prefix="/api/admin/journeys", tags=["journeys"])


def _need_db() -> None:
    if not is_configured():
        raise HTTPException(status_code=503, detail="journeys need DATABASE_URL")


@router.get("")
async def list_journeys(status: str = "", limit: int = 50, user=Depends(require("ingestion.view"))):
    _need_db()
    rows = await asyncio.to_thread(store.recent_journeys, min(limit, 500), status)
    return {"journeys": rows}


@router.get("/templates")
async def list_templates(user=Depends(require("ingestion.view"))):
    found = service.templates()
    return {
        "templates": [
            {
                "name": template.name,
                "steps": [
                    {"key": step.key, "channel": step.channel, "action": step.action, "dependsOn": list(step.depends_on),
                     "when": list(step.when_names), "delaySecs": step.delay_secs, "responseWindowSecs": step.response_window_secs,
                     "retries": step.max_attempts - 1}
                    for step in template.steps
                ],
                "rules": {kind: [rule.text() for rule in rules] for kind, rules in template.rules.items()},
            }
            for template in found.values()
        ],
        "adapters": adapters.report(),
    }


@router.get("/{journey_id}")
async def journey_detail(journey_id: int, user=Depends(require("ingestion.view"))):
    _need_db()
    view = await asyncio.to_thread(store.journey_view, journey_id)
    if view is None:
        raise HTTPException(status_code=404, detail="no such journey")
    return view
