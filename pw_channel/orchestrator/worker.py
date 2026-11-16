import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timezone

from pw_channel.orchestrator import service, store
from pw_channel.orchestrator.dispatcher import dispatch

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, *, poll_secs: float | None = None, batch: int | None = None, lease_secs: float | None = None,
                 concurrency: int | None = None):
        self.id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.poll_secs = poll_secs or float(os.getenv("WORKER_POLL_SECS", "2"))
        self.batch = batch or int(os.getenv("WORKER_BATCH", "20"))
        self.lease_secs = lease_secs or float(os.getenv("WORKER_LEASE_SECS", "120"))
        self.limit = asyncio.Semaphore(concurrency or int(os.getenv("WORKER_CONCURRENCY", "10")))
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def _run_one(self, task: store.TaskRow, now: datetime) -> None:
        async with self.limit:
            try:
                outcome = await dispatch(task, now)
                logger.info(f"[worker] task {task.id} {task.channel}.{task.action} ({task.key}) -> {outcome}")
            except Exception:
                logger.exception(f"[worker] task {task.id} failed unexpectedly")

    async def tick(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        await asyncio.to_thread(service.process_events, 100, now)
        await asyncio.to_thread(service.sweep, now)
        tasks = await asyncio.to_thread(store.claim_ready, self.id, self.batch, self.lease_secs, now)
        if tasks:
            await asyncio.gather(*(self._run_one(task, now) for task in tasks))
        return len(tasks)

    async def run(self) -> None:
        logger.info(f"[worker] {self.id} started (poll every {self.poll_secs:g}s, batch {self.batch})")
        while not self._stop.is_set():
            try:
                busy = await self.tick()
            except Exception:
                logger.exception("[worker] tick failed")
                busy = 0
            if not busy:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_secs)
                except asyncio.TimeoutError:
                    pass
        logger.info(f"[worker] {self.id} stopped")
