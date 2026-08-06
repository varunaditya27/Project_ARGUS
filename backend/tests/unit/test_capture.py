"""Interval capture buffer and flusher behaviour."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.errors import CapacityExceededError
from app.domain import Observation
from app.services.capture import IntervalFlusher, ObservationBuffer

SESSION = uuid.uuid4()
STUDENT = uuid.uuid4()
T0 = dt.datetime(2026, 8, 6, 9, 0, 0)


def observation(student_id: uuid.UUID, confidence: float, offset_seconds: int) -> Observation:
    return Observation(
        student_id=student_id,
        confidence=confidence,
        observed_at=T0 + dt.timedelta(seconds=offset_seconds),
    )


async def test_repeated_detections_collapse_to_one_row() -> None:
    buffer = ObservationBuffer(max_sessions=4)
    await buffer.record(SESSION, [observation(STUDENT, 0.62, 0)])
    await buffer.record(SESSION, [observation(STUDENT, 0.81, 30)])
    await buffer.record(SESSION, [observation(STUDENT, 0.55, 60)])

    drained = await buffer.drain(SESSION)
    assert len(drained) == 1
    # Highest confidence wins, earliest sighting is kept -- same rule as the
    # GREATEST/LEAST ON CONFLICT clause in the repository.
    assert drained[0].confidence == 0.81
    assert drained[0].observed_at == T0


async def test_drain_empties_the_session() -> None:
    buffer = ObservationBuffer(max_sessions=4)
    await buffer.record(SESSION, [observation(STUDENT, 0.7, 0)])
    assert len(await buffer.drain(SESSION)) == 1
    assert await buffer.drain(SESSION) == []


async def test_requeue_merges_back() -> None:
    buffer = ObservationBuffer(max_sessions=4)
    await buffer.record(SESSION, [observation(STUDENT, 0.90, 10)])
    pending = await buffer.drain(SESSION)
    await buffer.requeue(SESSION, pending)
    await buffer.record(SESSION, [observation(STUDENT, 0.40, 0)])

    drained = await buffer.drain(SESSION)
    assert len(drained) == 1
    assert drained[0].confidence == 0.90
    assert drained[0].observed_at == T0


async def test_buffer_is_bounded() -> None:
    buffer = ObservationBuffer(max_sessions=1)
    await buffer.record(SESSION, [observation(STUDENT, 0.7, 0)])
    with pytest.raises(CapacityExceededError):
        await buffer.record(uuid.uuid4(), [observation(STUDENT, 0.7, 0)])


async def test_flusher_persists_each_buffered_session() -> None:
    buffer = ObservationBuffer(max_sessions=4)
    persisted: list[tuple[uuid.UUID, int]] = []

    async def persist(session_id: uuid.UUID, observations: list[Observation]) -> int:
        persisted.append((session_id, len(observations)))
        return len(observations)

    other_session = uuid.uuid4()
    await buffer.record(SESSION, [observation(STUDENT, 0.7, 0)])
    await buffer.record(other_session, [observation(uuid.uuid4(), 0.8, 0)])

    flusher = IntervalFlusher(buffer=buffer, persist=persist, interval_seconds=0.01)
    assert await flusher.flush_once() == 2
    assert sorted(persisted) == sorted([(SESSION, 1), (other_session, 1)])
    assert await buffer.drain_all() == []


async def test_failed_flush_requeues_instead_of_losing_attendance() -> None:
    buffer = ObservationBuffer(max_sessions=4)

    async def failing_persist(session_id: uuid.UUID, observations: list[Observation]) -> int:
        raise RuntimeError("database unavailable")

    await buffer.record(SESSION, [observation(STUDENT, 0.7, 0)])
    flusher = IntervalFlusher(buffer=buffer, persist=failing_persist, interval_seconds=0.01)

    assert await flusher.flush_once() == 0
    assert len(await buffer.drain(SESSION)) == 1
