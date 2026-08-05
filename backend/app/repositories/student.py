from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Student


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
