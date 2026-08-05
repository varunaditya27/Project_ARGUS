"""End-to-end attendance lifecycle against a real PostgreSQL instance.

Run with::

    $env:ARGUS_TEST_DATABASE_URL = "postgresql+asyncpg://argus:argus@localhost:5432/argus_test"
    pytest tests/test_attendance_flow.py

Skipped automatically when the variable is absent.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.container import Container, build_container
from app.core.errors import ConflictError, NotFoundError
from app.db.base import Base
from app.domain.enums import AttendanceStatus, SessionStatus
from app.domain.observation import Observation
from app.schemas.classroom import ClassroomCreate
from app.schemas.session import SessionCreate
from app.schemas.student import StudentCreate
from tests.conftest import TEST_DATABASE_URL, make_settings, requires_database

pytestmark = [pytest.mark.database, requires_database]

T0 = dt.datetime(2026, 8, 6, 9, 0, 0)


@pytest_asyncio.fixture
async def container() -> AsyncIterator[Container]:
    instance = build_container(make_settings(database_url=TEST_DATABASE_URL))
    assert instance.database is not None
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield instance
    finally:
        await instance.shutdown()


async def seed(container: Container, *, students: int = 3):
    services = container.services
    classroom = await services.classrooms.create(
        ClassroomCreate(class_name="CSE-A", department="CSE", semester=5, strength=students)
    )
    roster = [
        await services.students.create(
            StudentCreate(
                student_name=f"Student {index}",
                roll_no=index,
                class_id=classroom.class_id,
                image_url=f"https://r2.example.com/enrollment/{index}.jpg",
            )
        )
        for index in range(1, students + 1)
    ]
    session = await services.sessions.create(
        SessionCreate(
            class_id=classroom.class_id,
            subject="Computer Vision",
            faculty="Dr. Placeholder",
            date=dt.date(2026, 8, 6),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 0),
        )
    )
    return classroom, roster, session


async def test_attendance_is_written_during_the_session(container: Container) -> None:
    _, roster, session = await seed(container)
    attendance = container.services.attendance

    await attendance.record(session.session_id, [Observation(roster[0].student_id, 0.62, T0)])
    assert await attendance.flush_session(session.session_id) == 1

    summary = await attendance.summary(session.session_id)
    assert (summary.present, summary.absent, summary.unrecorded) == (1, 0, 2)
    assert summary.session_status == SessionStatus.ACTIVE


async def test_later_intervals_keep_best_confidence_and_first_sighting(
    container: Container,
) -> None:
    _, roster, session = await seed(container)
    attendance = container.services.attendance
    student = roster[0].student_id

    await attendance.record(session.session_id, [Observation(student, 0.62, T0)])
    await attendance.flush_session(session.session_id)
    await attendance.record(
        session.session_id, [Observation(student, 0.88, T0 + dt.timedelta(minutes=5))]
    )
    await attendance.flush_session(session.session_id)

    rows = await attendance.register(session.session_id, status=None, after_roll_no=None, limit=10)
    assert len(rows) == 1
    record = rows[0][0]
    assert record.confidence == pytest.approx(0.88)
    assert record.timestamp == T0
    assert record.status == AttendanceStatus.PRESENT


async def test_observations_outside_the_roster_are_rejected_by_sql(
    container: Container,
) -> None:
    _, roster, session = await seed(container)
    services = container.services
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
    assert await services.attendance.flush_session(session.session_id) == 1


async def test_close_marks_absentees_once_and_is_not_repeatable(container: Container) -> None:
    _, roster, session = await seed(container)
    attendance = container.services.attendance

    await attendance.record(session.session_id, [Observation(roster[0].student_id, 0.77, T0)])
    await attendance.flush_session(session.session_id)
    # Still buffered at close time: must be persisted before absence is derived.
    await attendance.record(session.session_id, [Observation(roster[1].student_id, 0.69, T0)])

    report = await attendance.close_session(session.session_id)
    assert report.flushed_observations == 1
    assert report.present == 2
    assert report.absent_marked == 1
    assert report.roster_count == 3
    assert report.total_recorded == 3

    summary = await attendance.summary(session.session_id)
    assert summary.session_status == SessionStatus.CLOSED
    assert summary.unrecorded == 0

    with pytest.raises(ConflictError):
        await attendance.close_session(session.session_id)


async def test_closed_sessions_stop_accepting_attendance(container: Container) -> None:
    _, roster, session = await seed(container)
    attendance = container.services.attendance
    await attendance.close_session(session.session_id)

    await attendance.record(session.session_id, [Observation(roster[0].student_id, 0.95, T0)])
    assert await attendance.flush_session(session.session_id) == 0

    rows = await attendance.register(
        session.session_id, status=AttendanceStatus.PRESENT, after_roll_no=None, limit=10
    )
    assert rows == []


async def test_absent_rows_carry_the_documented_sentinel(container: Container) -> None:
    _, _, session = await seed(container)
    report = await container.services.attendance.close_session(session.session_id)
    assert report.absent_marked == 3

    rows = await container.services.attendance.register(
        session.session_id, status=AttendanceStatus.ABSENT, after_roll_no=None, limit=10
    )
    assert len(rows) == 3
    assert all(record.confidence == 0.0 for record, _, _ in rows)
    assert all(record.timestamp == report.closed_at for record, _, _ in rows)


async def test_one_active_session_per_classroom(container: Container) -> None:
    classroom, _, _ = await seed(container)
    duplicate = SessionCreate(
        class_id=classroom.class_id,
        subject="Second lecture",
        faculty="Dr. Placeholder",
        date=dt.date(2026, 8, 6),
        start_time=dt.time(11, 0),
        end_time=dt.time(12, 0),
    )
    with pytest.raises(ConflictError):
        await container.services.sessions.create(duplicate)


async def test_duplicate_roll_number_is_rejected(container: Container) -> None:
    classroom, _, _ = await seed(container)
    with pytest.raises(ConflictError):
        await container.services.students.create(
            StudentCreate(
                student_name="Clash",
                roll_no=1,
                class_id=classroom.class_id,
                image_url="https://r2.example.com/enrollment/clash.jpg",
            )
        )


async def test_closing_an_unknown_session_is_a_404(container: Container) -> None:
    with pytest.raises(NotFoundError):
        await container.services.attendance.close_session(uuid.uuid4())


async def test_keyset_pagination_walks_the_register(container: Container) -> None:
    _, roster, session = await seed(container, students=5)
    attendance = container.services.attendance
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
