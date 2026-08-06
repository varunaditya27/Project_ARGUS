"""Classroom queries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Classroom, Student


class ClassroomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, class_name: str, department: str, semester: int, strength: int
    ) -> Classroom:
        # Insert and flush so the generated class_id is available to the caller.
        classroom = Classroom(
            class_name=class_name, department=department, semester=semester, strength=strength
        )
        self._session.add(classroom)
        await self._session.flush()
        return classroom

    async def get(self, class_id: uuid.UUID) -> Classroom | None:
        # Primary key lookup.
        return await self._session.get(Classroom, class_id)

    async def list(
        self,
        *,
        department: str | None,
        semester: int | None,
        limit: int,
        offset: int,
    ) -> Sequence[Classroom]:
        # Filtered page, ordered so results are stable across requests.
        stmt = select(Classroom).order_by(
            Classroom.department, Classroom.semester, Classroom.class_name
        )
        if department is not None:
            stmt = stmt.where(Classroom.department == department)
        if semester is not None:
            stmt = stmt.where(Classroom.semester == semester)
        return (await self._session.execute(stmt.limit(limit).offset(offset))).scalars().all()

    async def roster_count(self, class_id: uuid.UUID) -> int:
        # Live number of students assigned, which is what attendance maths uses.
        stmt = select(func.count()).select_from(Student).where(Student.class_id == class_id)
        return int((await self._session.execute(stmt)).scalar_one())
