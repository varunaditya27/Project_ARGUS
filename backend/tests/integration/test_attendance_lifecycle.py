"""Capture during the session, absence derived once at close.

Run with::

    $env:ARGUS_TEST_DATABASE_URL = "postgresql+asyncpg://argus:argus@localhost:5432/argus_test"
    pytest tests/integration
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.container import Container
from app.core.errors import ConflictError, NotFoundError
from app.domain import AttendanceStatus, Observation, SessionStatus
from app.schemas.student import StudentCreate
from tests.conftest import requires_database
from tests.helpers import T0, seed

pytestmark = [pytest.mark.database, requires_database]


async def flush(container: Container) -> int:
    # What the interval flusher does on its tick.
    assert container.flusher is not None
    return await container.flusher.flush_once()


async def test_attendance_is_written_during_the_session(db_container: Container) -> None:
    _, roster, session = await seed(db_container)
    attendance = db_container.services.attendance

    await attendance.record(session.session_id, [Observation(roster[0].student_id, 0.62, T0)])
    assert await flush(db_container) == 1

    summary = await attendance.summary(session.session_id)
    assert (summary.present, summary.absent, summary.roster_count) == (1, 0, 3)
    assert summary.session_status == SessionStatus.ACTIVE


async def test_later_intervals_keep_best_confidence_and_first_sighting(
    db_container: Container,
) -> None:
    _, roster, session = await seed(db_container)
    attendance = db_container.services.attendance
    student = roster[0].student_id

    await attendance.record(session.session_id, [Observation(student, 0.62, T0)])
    await flush(db_container)
    await attendance.record(
        session.session_id, [Observation(student, 0.88, T0 + dt.timedelta(minutes=5))]
    )
    await flush(db_container)

    rows = await attendance.register(session.session_id, status=None, after_roll_no=None, limit=10)
    assert len(rows) == 1
    record = rows[0][0]
    assert record.confidence == pytest.approx(0.88)
    assert record.timestamp == T0
    assert record.status == AttendanceStatus.PRESENT


async def test_observations_outside_the_roster_are_rejected_by_sql(
    db_container: Container,
) -> None:
    _, roster, session = await seed(db_container)
    services = db_container.services
    outsider = await services.students.create(
        StudentCreate(
            student_name="Outsider",
            roll_no=9999,
            class_id=None,
            image_url="https://r2.example.com/enrollment/9999.jpg",
        )
    )

    await services.attendance.record(
        session.session_id,
        [
            Observation(roster[0].student_id, 0.71, T0),
            Observation(outsider.student_id, 0.99, T0),
            Observation(uuid.uuid4(), 0.99, T0),
        ],
    )
    assert await flush(db_container) == 1


async def test_close_marks_absentees_once_and_is_not_repeatable(db_container: Container) -> None:
    _, roster, session = await seed(db_container)
    attendance = db_container.services.attendance

    await attendance.record(session.session_id, [Observation(roster[0].student_id, 0.77, T0)])
    await flush(db_container)
    # Still buffered at close time: must be persisted before absence is derived.
    await attendance.record(session.session_id, [Observation(roster[1].student_id, 0.69, T0)])

    report = await attendance.close_session(session.session_id)
    assert (report.present, report.absent_marked, report.roster_count) == (2, 1, 3)

    summary = await attendance.summary(session.session_id)
    assert summary.session_status == SessionStatus.CLOSED
    assert summary.present + summary.absent == summary.roster_count

    with pytest.raises(ConflictError):
        await attendance.close_session(session.session_id)


async def test_closed_sessions_stop_accepting_attendance(db_container: Container) -> None:
    _, roster, session = await seed(db_container)
    attendance = db_container.services.attendance
    await attendance.close_session(session.session_id)

    await attendance.record(session.session_id, [Observation(roster[0].student_id, 0.95, T0)])
    assert await flush(db_container) == 0

    rows = await attendance.register(
        session.session_id, status=AttendanceStatus.PRESENT, after_roll_no=None, limit=10
    )
    assert rows == []


async def test_absent_rows_carry_the_documented_sentinel(db_container: Container) -> None:
    _, _, session = await seed(db_container)
    attendance = db_container.services.attendance
    report = await attendance.close_session(session.session_id)
    assert report.absent_marked == 3

    rows = await attendance.register(
        session.session_id, status=AttendanceStatus.ABSENT, after_roll_no=None, limit=10
    )
    assert len(rows) == 3
    assert all(record.confidence == 0.0 for record, _, _ in rows)
    assert all(record.timestamp == report.closed_at for record, _, _ in rows)


async def test_closing_an_unknown_session_is_a_404(db_container: Container) -> None:
    with pytest.raises(NotFoundError):
        await db_container.services.attendance.close_session(uuid.uuid4())


async def test_keyset_pagination_walks_the_register(db_container: Container) -> None:
    _, roster, session = await seed(db_container, students=5)
    attendance = db_container.services.attendance
    await attendance.close_session(session.session_id)

    seen: list[int] = []
    cursor: int | None = None
    while True:
        rows = await attendance.register(
            session.session_id, status=None, after_roll_no=cursor, limit=2
        )
        if not rows:
            break
        seen.extend(roll_no for _, _, roll_no in rows)
        cursor = seen[-1]
    assert seen == [student.roll_no for student in roster]
