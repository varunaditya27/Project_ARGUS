"""Placeholder load data for the database benchmark.

Every row is obviously synthetic (``BENCH-*`` names, ``*.invalid`` image URLs) so
benchmark data can never be mistaken for a real roster.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import chunked
from app.db.models import Base, Classroom
from app.db.session import Database
from app.domain import SessionStatus
from app.repositories.session import ClassSessionRepository
from app.repositories.student import StudentRepository

PLACEHOLDER_IMAGE = "https://benchmark.invalid/placeholder/{roll_no}.jpg"


def resolve_dsn() -> str:
    # Refuse to run anywhere near the application database.
    dsn = os.getenv("ARGUS_BENCH_DATABASE_URL")
    if not dsn:
        sys.exit("ARGUS_BENCH_DATABASE_URL is not set; the benchmark recreates every table.")
    if dsn == os.getenv("ARGUS_DATABASE_URL"):
        sys.exit("Refusing to run: ARGUS_BENCH_DATABASE_URL equals ARGUS_DATABASE_URL.")
    return dsn


async def reset_schema(database: Database) -> None:
    # Drop and recreate every table in the benchmark database.
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


async def seed_roster(
    session: AsyncSession, *, students: int, chunk: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    # One classroom plus a full cohort of placeholder students.
    classroom = Classroom(
        class_name="BENCH-COHORT", department="BENCHMARK", semester=1, strength=students
    )
    session.add(classroom)
    await session.flush()

    student_ids = [uuid.uuid4() for _ in range(students)]
    rows = [
        {
            "student_id": student_id,
            "student_name": f"BENCH-{roll_no:06d}",
            "roll_no": roll_no,
            "class_id": classroom.class_id,
            "image_url": PLACEHOLDER_IMAGE.format(roll_no=roll_no),
        }
        for roll_no, student_id in enumerate(student_ids, start=1)
    ]
    for batch in chunked(rows, chunk):
        await StudentRepository(session).bulk_insert(batch)
    return classroom.class_id, student_ids


async def open_session(database: Database, class_id: uuid.UUID) -> uuid.UUID:
    # A single ACTIVE session to capture against.
    async with database.session() as db_session:
        class_session = await ClassSessionRepository(db_session).create(
            class_id=class_id,
            subject="BENCH",
            faculty="BENCH",
            date=dt.date.today(),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 0),
            status=SessionStatus.ACTIVE,
        )
    return class_session.session_id
