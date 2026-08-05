"""In-process capture buffer.

Attendance is taken *during* the lecture, not at the end: recognition pushes
observations here continuously and a background flusher persists them once per
capture interval. The buffer exists so that N detections of the same student
inside one interval cost one row write instead of N, which is what keeps the
write path flat when a 20 000 student cohort is being recognised.

Nothing here is a source of truth -- PostgreSQL is. The merge rule
(``max(confidence)``, ``min(timestamp)``) is identical to the ``ON CONFLICT DO
UPDATE`` rule in :mod:`app.repositories.attendance`, so it does not matter
whether two observations are merged in memory, in SQL, or in different backend
processes: the stored row is the same.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable

from app.core.errors import CapacityExceededError
from app.domain.observation import Observation


class ObservationBuffer:
    def __init__(self, *, max_sessions: int) -> None:
        self._max_sessions = max_sessions
        self._sessions: dict[uuid.UUID, dict[uuid.UUID, Observation]] = {}
        self._lock = asyncio.Lock()

    async def record(self, session_id: uuid.UUID, observations: Iterable[Observation]) -> int:
        """Merge observations into the pending interval. Returns the pending count."""
        async with self._lock:
            pending = self._sessions.get(session_id)
            if pending is None:
                if len(self._sessions) >= self._max_sessions:
                    raise CapacityExceededError(
                        "Too many sessions are buffering attendance in this worker.",
                        details={"max_sessions": self._max_sessions},
                    )
                pending = self._sessions[session_id] = {}
            for observation in observations:
                existing = pending.get(observation.student_id)
                pending[observation.student_id] = (
                    observation if existing is None else existing.merge(observation)
                )
            return len(pending)

    async def drain(self, session_id: uuid.UUID) -> list[Observation]:
        async with self._lock:
            return list(self._sessions.pop(session_id, {}).values())

    async def drain_all(self) -> list[tuple[uuid.UUID, list[Observation]]]:
        async with self._lock:
            drained = [(sid, list(pending.values())) for sid, pending in self._sessions.items()]
            self._sessions.clear()
            return drained

    async def requeue(self, session_id: uuid.UUID, observations: Iterable[Observation]) -> None:
        """Put observations back after a failed flush (idempotent thanks to merge)."""
        async with self._lock:
            pending = self._sessions.setdefault(session_id, {})
            for observation in observations:
                existing = pending.get(observation.student_id)
                pending[observation.student_id] = (
                    observation if existing is None else existing.merge(observation)
                )

    async def discard(self, session_id: uuid.UUID) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def stats(self) -> dict[str, int]:
        async with self._lock:
            return {
                "buffered_sessions": len(self._sessions),
                "pending_observations": sum(len(p) for p in self._sessions.values()),
            }
