from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.database import Database
from app.db.integrity import integrity_guard
from app.db.models import Student
from app.recognition.ports import TemplateIndex
from app.repositories.student import StudentRepository
from app.schemas.student import StudentCreate

logger = get_logger(__name__)

_CONSTRAINT_MESSAGES = {
    "uq_students_roll_no": "A student with this roll number already exists.",
    "fk_students_class_id": "The referenced classroom does not exist.",
}


class StudentService:
    def __init__(self, database: Database, index: TemplateIndex) -> None:
        self._db = database
        self._index = index

    async def create(self, payload: StudentCreate) -> Student:
        async with self._db.session() as session, integrity_guard(_CONSTRAINT_MESSAGES):
            return await StudentRepository(session).create(
                student_name=payload.student_name,
                roll_no=payload.roll_no,
                image_url=str(payload.image_url),
                class_id=payload.class_id,
            )

    async def get(self, student_id: uuid.UUID) -> Student:
        async with self._db.session() as session:
            student = await StudentRepository(session).get(student_id)
        if student is None:
            raise NotFoundError(f"Student {student_id} does not exist.")
        return student

    async def list(
        self, *, class_id: uuid.UUID | None, after_roll_no: int | None, limit: int
    ) -> Sequence[Student]:
        async with self._db.session() as session:
            return await StudentRepository(session).list(
                class_id=class_id, after_roll_no=after_roll_no, limit=limit
            )

    async def delete(self, student_id: uuid.UUID) -> int:
        """Remove a student and every template that could still match them.

        Vectors go first: if Chroma fails the student stays enrolled and the call
        fails loudly, whereas the reverse order could leave searchable vectors
        pointing at a deleted identity (acceptance test AT-11).
        """
        await self.get(student_id)

        removed_templates = 0
        if self._index.status().configured:
            removed_templates = await self._index.delete_student(student_id)

        async with self._db.session() as session:
            deleted = await StudentRepository(session).delete(student_id)
        if not deleted:
            raise NotFoundError(f"Student {student_id} does not exist.")
        logger.info("Deleted student %s and %d templates", student_id, removed_templates)
        return removed_templates
