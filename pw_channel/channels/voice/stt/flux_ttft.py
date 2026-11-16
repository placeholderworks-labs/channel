import logging

logger = logging.getLogger(__name__)


def attach_ttft_metrics(service) -> None:
    state = {"open": False}

    async def opened() -> None:
        state["open"] = True
        await service.start_ttfb_metrics()

    async def first_text() -> None:
        if not state["open"]:
            return
        state["open"] = False
        await service.stop_ttfb_metrics()

    @service.event_handler("on_start_of_turn")
    async def _on_start_of_turn(_service, transcript):
        await opened()
        if (transcript or "").strip():
            await first_text()

    @service.event_handler("on_update")
    async def _on_update(_service, transcript):
        if (transcript or "").strip():
            await first_text()

    @service.event_handler("on_end_of_turn")
    async def _on_end_of_turn(_service, transcript):
        if (transcript or "").strip():
            await first_text()
        state["open"] = False
