"""In-process capture buffer and the task that drains it.

Attendance is taken during the lecture, not at the end: recognition pushes
observations into the buffer continuously and the flusher persists them once per
capture interval. Coalescing means N detections of one student inside an
interval cost one row write instead of N, which is what keeps the write path
flat for a 20 000 student cohort.

PostgreSQL remains the source of truth. The merge rule here is identical to the
ON CONFLICT DO UPDATE rule in app.repositories.attendance, so it makes no
difference whether two observations meet in memory, in SQL or across processes.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable, Iterable

from app.core.errors import CapacityExceededError
from app.core.logging import get_logger
from app.domain import Observation

logger = get_logger(__name__)

PersistCallback = Callable[[uuid.UUID, list[Observation]], Awaitable[int]]


class ObservationBuffer:
    def __init__(self, *, max_sessions: int) -> None:
        self._max_sessions = max_sessions
        self._sessions: dict[uuid.UUID, dict[uuid.UUID, Observation]] = {}
        self._lock = asyncio.Lock()

    async def record(self, session_id: uuid.UUID, observations: Iterable[Observation]) -> int:
        # Merge into the pending interval; returns the pending count for the session.
        async with self._lock:
            pending = self._sessions.get(session_id)
            if pending is None:
                if len(self._sessions) >= self._max_sessions:
                    raise CapacityExceededError(
                        "Too many sessions are buffering attendance in this worker.",
                        details={"max_sessions": self._max_sessions},
                    )
                pending = self._sessions[session_id] = {}
            _merge_into(pending, observations)
            return len(pending)

    async def drain(self, session_id: uuid.UUID) -> list[Observation]:
        # Take everything buffered for one session.
        async with self._lock:
            return list(self._sessions.pop(session_id, {}).values())

    async def drain_all(self) -> list[tuple[uuid.UUID, list[Observation]]]:
        # Take everything buffered, for the interval flush.
        async with self._lock:
            drained = [(sid, list(pending.values())) for sid, pending in self._sessions.items()]
            self._sessions.clear()
            return drained

    async def requeue(self, session_id: uuid.UUID, observations: Iterable[Observation]) -> None:
        # Put observations back after a failed flush; idempotent thanks to merge.
        async with self._lock:
            _merge_into(self._sessions.setdefault(session_id, {}), observations)


class IntervalFlusher:
    """Background task that turns the buffer into attendance rows."""

    def __init__(
        self, *, buffer: ObservationBuffer, persist: PersistCallback, interval_seconds: float
    ) -> None:
        self._buffer = buffer
        self._persist = persist
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        # Begin ticking once per capture interval.
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="argus-attendance-flusher")
            logger.info("Attendance flusher started (interval=%.1fs)", self._interval)

    async def stop(self) -> None:
        # Cancel the loop, then flush once more so nothing captured is lost.
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush_once()

    async def _run(self) -> None:
        # Tick forever; a failed tick must not kill the task.
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.flush_once()
            except Exception:
                logger.exception("Attendance interval flush failed")

    async def flush_once(self) -> int:
        # Persist every buffered session; a failed session is requeued, not lost.
        written = 0
        for session_id, observations in await self._buffer.drain_all():
            if not observations:
                continue
            try:
                written += await self._persist(session_id, observations)
            except Exception:
                await self._buffer.requeue(session_id, observations)
                logger.exception("Flush failed for session %s; observations requeued", session_id)
        return written


def _merge_into(pending: dict[uuid.UUID, Observation], observations: Iterable[Observation]) -> None:
    # Strongest confidence and earliest sighting win, per student.
    for observation in observations:
        existing = pending.get(observation.student_id)
        pending[observation.student_id] = (
            observation if existing is None else existing.merge(observation)
        )
