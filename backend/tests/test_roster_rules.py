"""Rules the schema does not enforce: one ACTIVE session, unique roll numbers,
and cleaning up attendance when a student is deleted."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

import pytest

from app.container import Container
from app.core.errors import ConflictError, NotFoundError
from app.domain import Observation, SessionStatus
from app.schemas.classroom import ClassroomCreate
from app.schemas.session import SessionCreate
from app.schemas.student import StudentCreate
from tests.conftest import T0, requires_database, seed

pytestmark = [pytest.mark.database, requires_database]


def second_lecture(class_id: uuid.UUID) -> SessionCreate:
    return SessionCreate(
        class_id=class_id,
        subject="Second lecture",
        faculty="Dr. Placeholder",
        date=dt.date(2026, 8, 6),
        start_time=dt.time(11, 0),
        end_time=dt.time(12, 0),
    )


async def active_session_ids(container: Container, class_id: uuid.UUID) -> list[uuid.UUID]:
    sessions = await container.services.sessions.list(
        class_id=class_id,
        status=SessionStatus.ACTIVE,
        date_from=None,
        date_to=None,
        limit=10,
        offset=0,
    )
    return [session.session_id for session in sessions]


async def test_one_active_session_per_classroom(db_container: Container) -> None:
    classroom, _, _ = await seed(db_container)
    with pytest.raises(ConflictError):
        await db_container.services.sessions.create(second_lecture(classroom.class_id))


async def test_concurrent_opens_cannot_both_win(db_container: Container) -> None:
    """The schema has no partial unique index, so the advisory lock is the guarantee."""
    classroom = await db_container.services.classrooms.create(
        ClassroomCreate(class_name="CSE-B", department="CSE", semester=5, strength=0)
    )
    payload = second_lecture(classroom.class_id)

    results = await asyncio.gather(
        *(db_container.services.sessions.create(payload) for _ in range(4)),
        return_exceptions=True,
    )
    created = [result for result in results if not isinstance(result, BaseException)]
    rejected = [result for result in results if isinstance(result, ConflictError)]
    assert len(created) == 1
    assert len(rejected) == 3
    assert await active_session_ids(db_container, classroom.class_id) == [created[0].session_id]


async def test_a_classroom_can_open_a_new_session_once_the_first_closes(
    db_container: Container,
) -> None:
    classroom, _, session = await seed(db_container)
    await db_container.services.attendance.close_session(session.session_id)

    reopened = await db_container.services.sessions.create(second_lecture(classroom.class_id))
    assert reopened.status == SessionStatus.ACTIVE
    assert await active_session_ids(db_container, classroom.class_id) == [reopened.session_id]


async def test_deleting_a_student_removes_their_attendance(db_container: Container) -> None:
    """AT-11. The foreign keys carry no ON DELETE, so the service must clear them."""
    _, roster, session = await seed(db_container)
    student = roster[0]
    attendance = db_container.services.attendance

    await attendance.record(session.session_id, [Observation(student.student_id, 0.81, T0)])
    assert db_container.flusher is not None
    await db_container.flusher.flush_once()
    assert (await attendance.summary(session.session_id)).present == 1

    await db_container.services.students.delete(student.student_id)

    with pytest.raises(NotFoundError):
        await db_container.services.students.get(student.student_id)
    summary = await attendance.summary(session.session_id)
    assert (summary.present, summary.roster_count) == (0, 2)


async def test_duplicate_roll_number_is_rejected(db_container: Container) -> None:
    classroom, _, _ = await seed(db_container)
    with pytest.raises(ConflictError):
        await db_container.services.students.create(
            StudentCreate(
                student_name="Clash",
                roll_no=1,
                class_id=classroom.class_id,
                image_url="https://r2.example.com/enrollment/clash.jpg",
            )
        )
