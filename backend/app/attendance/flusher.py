"""Background task that turns the capture buffer into attendance rows.

One tick = one capture interval. Every tick drains every buffered session and
hands it to the persist callback; a session whose flush fails is requeued so a
transient database error delays attendance instead of losing it.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable

from app.attendance.buffer import ObservationBuffer
from app.core.logging import get_logger
from app.domain.observation import Observation

logger = get_logger(__name__)

PersistCallback = Callable[[uuid.UUID, list[Observation]], Awaitable[int]]


class IntervalFlusher:
    def __init__(
        self,
        *,
        buffer: ObservationBuffer,
        persist: PersistCallback,
        interval_seconds: float,
    ) -> None:
        self._buffer = buffer
        self._persist = persist
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="argus-attendance-flusher")
            logger.info("Attendance flusher started (interval=%.1fs)", self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        # Final tick so observations captured just before shutdown are not lost.
        await self.flush_once()
        logger.info("Attendance flusher stopped")

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.flush_once()
            except Exception:
                logger.exception("Attendance interval flush failed")

    async def flush_once(self) -> int:
        """Persist every buffered session. Returns the number of rows written."""
        written = 0
        for session_id, observations in await self._buffer.drain_all():
            if not observations:
                continue
            try:
                written += await self._persist(session_id, observations)
            except Exception:
                await self._buffer.requeue(session_id, observations)
                logger.exception(
                    "Flush failed for session %s; %d observations requeued",
                    session_id,
                    len(observations),
                )
        return written
