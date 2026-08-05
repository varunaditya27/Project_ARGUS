from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.errors import NotFoundError
from app.db.database import Database
from app.db.models import Classroom
from app.repositories.classroom import ClassroomRepository
from app.schemas.classroom import ClassroomCreate


class ClassroomService:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create(self, payload: ClassroomCreate) -> Classroom:
        async with self._db.session() as session:
            return await ClassroomRepository(session).create(
                class_name=payload.class_name,
                department=payload.department,
                semester=payload.semester,
                strength=payload.strength,
            )

    async def list(
        self,
        *,
        department: str | None,
        semester: int | None,
        limit: int,
        offset: int,
    ) -> Sequence[Classroom]:
        async with self._db.session() as session:
            return await ClassroomRepository(session).list(
                department=department, semester=semester, limit=limit, offset=offset
            )

    async def get_with_roster_count(self, class_id: uuid.UUID) -> tuple[Classroom, int]:
        async with self._db.session() as session:
            repository = ClassroomRepository(session)
            classroom = await repository.get(class_id)
            if classroom is None:
                raise NotFoundError(f"Classroom {class_id} does not exist.")
            return classroom, await repository.roster_count(class_id)
