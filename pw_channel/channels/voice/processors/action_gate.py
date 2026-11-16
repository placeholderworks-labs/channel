import asyncio
import logging

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterruptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)


class ActionGateProcessor(FrameProcessor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._generation = 0
        self._interrupts = 0
        self._speaking = False
        self._waiters: list[asyncio.Future] = []

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def interrupts(self) -> int:
        return self._interrupts

    async def wait_for_drain(self, snapshot: int, timeout: float) -> bool:
        if self._generation > snapshot:
            return True

        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        self._waiters.append(waiter)
        try:
            await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(
                f"[action_gate] bot never reported finishing its line within {timeout}s — "
                "acting anyway rather than leaving the action hanging"
            )
            return False
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def _release(self) -> None:
        for waiter in list(self._waiters):
            if not waiter.done():
                waiter.set_result(True)
        self._waiters.clear()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._speaking = False
            self._generation += 1
            self._release()
        elif isinstance(frame, InterruptionFrame):
            self._speaking = False
            self._generation += 1
            self._interrupts += 1
            self._release()

        await self.push_frame(frame, direction)
