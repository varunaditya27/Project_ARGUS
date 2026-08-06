"""Roster queries.

Listing uses keyset pagination on roll_no rather than OFFSET, so a 20 000
student roster is paged in constant time per page.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence

from sqlalchemy import delete, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Student

#: `= ANY(array)` rather than `IN (...)`: one bind parameter however many roll
#: numbers are checked, so a 20 000 row import stays a single round trip.
_EXISTING_ROLLS = text(
    "SELECT roll_no FROM students WHERE roll_no = ANY(CAST(:rolls AS integer[]))"
)


class StudentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, student_name: str, roll_no: int, image_url: str, class_id: uuid.UUID | None
    ) -> Student:
        # Insert and flush so the generated student_id is available to the caller.
        student = Student(
            student_name=student_name, roll_no=roll_no, image_url=image_url, class_id=class_id
        )
        self._session.add(student)
        await self._session.flush()
        return student

    async def get(self, student_id: uuid.UUID) -> Student | None:
        # Primary key lookup.
        return await self._session.get(Student, student_id)

    async def list(
        self, *, class_id: uuid.UUID | None, after_roll_no: int | None, limit: int
    ) -> Sequence[Student]:
        # Keyset page ordered by roll number.
        stmt = select(Student).order_by(Student.roll_no).limit(limit)
        if class_id is not None:
            stmt = stmt.where(Student.class_id == class_id)
        if after_roll_no is not None:
            stmt = stmt.where(Student.roll_no > after_roll_no)
        return (await self._session.execute(stmt)).scalars().all()

    async def delete(self, student_id: uuid.UUID) -> bool:
        # Remove the roster row; attendance rows must already be gone.
        result = await self._session.execute(
            delete(Student).where(Student.student_id == student_id)
        )
        return bool(result.rowcount)

    async def existing_roll_numbers(self, rolls: Sequence[int]) -> set[int]:
        # Which of these roll numbers are already enrolled, in one query.
        if not rolls:
            return set()
        result = await self._session.execute(_EXISTING_ROLLS, {"rolls": list(rolls)})
        return {int(roll_no) for roll_no in result.scalars()}

    async def insert_new(self, rows: Sequence[Mapping[str, object]]) -> set[int]:
        # One multi-row INSERT; a roll number taken concurrently loses its row and
        # is reported back by omission instead of aborting the whole batch.
        if not rows:
            return set()
        stmt = (
            pg_insert(Student)
            .values(list(rows))
            .on_conflict_do_nothing(index_elements=[Student.roll_no])
            .returning(Student.roll_no)
        )
        return {int(roll_no) for roll_no in (await self._session.execute(stmt)).scalars()}

    async def bulk_insert(self, rows: Iterable[dict[str, object]]) -> int:
        # Plain multi-row INSERT used to seed the benchmark dataset.
        payload = list(rows)
        if not payload:
            return 0
        await self._session.execute(insert(Student), payload)
        return len(payload)
