from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence

from sqlalchemy import delete, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Student

#: ``= ANY(array)`` rather than ``IN (...)``: one bind parameter regardless of how
#: many roll numbers are checked, so a 20 000 row import stays a single round trip
#: and never approaches the protocol's parameter limit.
_EXISTING_ROLL_NUMBERS = text(
    "SELECT roll_no FROM students WHERE roll_no = ANY(CAST(:rolls AS integer[]))"
)


class StudentRepository:
    """Roster access.

    Listing uses keyset pagination on ``roll_no`` instead of OFFSET: a 20 000
    student roster is paged in constant time per page and the
    ``(class_id, roll_no)`` index satisfies both the filter and the ordering.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        student_name: str,
        roll_no: int,
        image_url: str,
        class_id: uuid.UUID | None,
    ) -> Student:
        student = Student(
            student_name=student_name,
            roll_no=roll_no,
            image_url=image_url,
            class_id=class_id,
        )
        self._session.add(student)
        await self._session.flush()
        return student

    async def get(self, student_id: uuid.UUID) -> Student | None:
        return await self._session.get(Student, student_id)

    async def get_by_roll_no(self, roll_no: int) -> Student | None:
        stmt = select(Student).where(Student.roll_no == roll_no)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list(
        self,
        *,
        class_id: uuid.UUID | None = None,
        after_roll_no: int | None = None,
        limit: int,
    ) -> Sequence[Student]:
        stmt = select(Student).order_by(Student.roll_no).limit(limit)
        if class_id is not None:
            stmt = stmt.where(Student.class_id == class_id)
        if after_roll_no is not None:
            stmt = stmt.where(Student.roll_no > after_roll_no)
        return (await self._session.execute(stmt)).scalars().all()

    async def delete(self, student_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Student).where(Student.student_id == student_id)
        )
        return bool(result.rowcount)

    async def bulk_insert(self, rows: Iterable[dict[str, object]]) -> int:
        """Multi-row INSERT used by roster import and the benchmark harness."""
        payload = list(rows)
        if not payload:
            return 0
        # executemany form: it raises on failure, so a return means every row landed.
        await self._session.execute(insert(Student), payload)
        return len(payload)

    async def existing_roll_numbers(self, rolls: Sequence[int]) -> set[int]:
        """Roll numbers from ``rolls`` that are already enrolled, in one query."""
        if not rolls:
            return set()
        result = await self._session.execute(_EXISTING_ROLL_NUMBERS, {"rolls": list(rolls)})
        return {int(roll_no) for roll_no in result.scalars()}

    async def insert_new(self, rows: Sequence[Mapping[str, object]]) -> set[int]:
        """Insert roster rows and report which roll numbers actually landed.

        One multi-row statement per call, and ``ON CONFLICT DO NOTHING`` on the
        ``roll_no`` unique index instead of a pre-flight SELECT: a roll number
        inserted by a concurrent request loses its row here and is reported back to
        the caller by omission, rather than aborting the whole batch. Existing
        students are never updated.
        """
        if not rows:
            return set()
        stmt = (
            pg_insert(Student)
            .values(list(rows))
            .on_conflict_do_nothing(index_elements=[Student.roll_no])
            .returning(Student.roll_no)
        )
        result = await self._session.execute(stmt)
        return {int(roll_no) for roll_no in result.scalars()}
