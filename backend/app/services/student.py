"""Student use cases."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.integrity import integrity_guard
from app.db.models import Student
from app.db.session import Database
from app.recognition.stack import RecognitionStack
from app.repositories.attendance import AttendanceRepository
from app.repositories.student import StudentRepository
from app.schemas.student import StudentCreate

logger = get_logger(__name__)

_CONSTRAINTS = {
    "uq_students_roll_no": "A student with this roll number already exists.",
    "fk_students_class_id": "The referenced classroom does not exist.",
}


class StudentService:
    def __init__(self, database: Database, stack: RecognitionStack) -> None:
        self._db = database
        self._stack = stack

    async def create(self, payload: StudentCreate) -> Student:
        # Enrol a student; the unique roll number is arbitrated by the database.
        async with self._db.session() as session, integrity_guard(_CONSTRAINTS):
            return await StudentRepository(session).create(
                student_name=payload.student_name,
                roll_no=payload.roll_no,
                image_url=str(payload.image_url),
                class_id=payload.class_id,
            )

    async def get(self, student_id: uuid.UUID) -> Student:
        # One student, or 404.
        async with self._db.session() as session:
            student = await StudentRepository(session).get(student_id)
        if student is None:
            raise NotFoundError(f"Student {student_id} does not exist.")
        return student

    async def list(
        self, *, class_id: uuid.UUID | None, after_roll_no: int | None, limit: int
    ) -> Sequence[Student]:
        # Keyset page of the roster.
        async with self._db.session() as session:
            return await StudentRepository(session).list(
                class_id=class_id, after_roll_no=after_roll_no, limit=limit
            )

    async def delete(self, student_id: uuid.UUID) -> int:
        # Vectors go first: if Chroma fails the student stays enrolled, whereas
        # the reverse order could leave searchable vectors for a deleted
        # identity. Attendance rows go next because the FKs carry no ON DELETE.
        await self.get(student_id)
        removed_templates = 0
        if self._stack.index is not None:
            removed_templates = await self._stack.index.delete_student(student_id)

        async with self._db.session() as session:
            removed_rows = await AttendanceRepository(session).delete_for_student(student_id)
            deleted = await StudentRepository(session).delete(student_id)
        if not deleted:
            raise NotFoundError(f"Student {student_id} does not exist.")
        logger.info(
            "Deleted student %s with %d templates and %d attendance rows",
            student_id,
            removed_templates,
            removed_rows,
        )
        return removed_templates
