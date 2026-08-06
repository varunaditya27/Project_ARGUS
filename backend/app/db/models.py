"""ORM mapping of the schema documented in ``docs/db.md``.

The mapping is deliberately literal: the four documented tables, their columns,
types and the two documented constraints, and nothing else. No extra index,
CHECK constraint or foreign-key delete rule is declared, so the DDL Alembic
emits is exactly what the schema document specifies.

Two consequences are handled in the service layer rather than the schema:

* Foreign keys default to ``NO ACTION``, so rows that reference a student or a
  session must be removed before it is deleted -- see ``StudentService.delete``.
* Nothing stops two ACTIVE sessions existing for one classroom, which the
  recognition workflow ("Fetch Active Class Session") assumes cannot happen.
  ``SessionService.create`` serialises that check with an advisory lock.

Face embeddings are **not** stored here; they live in ChromaDB.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_UUID_PK = text("gen_random_uuid()")


class Classroom(Base):
    __tablename__ = "classrooms"

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    class_name: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str] = mapped_column(Text, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Declared/official class strength. The live roster count is derived from
    #: ``students`` and is what the absence pass uses.
    strength: Mapped[int] = mapped_column(Integer, nullable=False)

    students: Mapped[list[Student]] = relationship(back_populates="classroom", lazy="raise")


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    student_name: Mapped[str] = mapped_column(Text, nullable=False)
    #: INTEGER per docs/db.md, globally unique.
    roll_no: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classrooms.class_id"),
        nullable=True,
    )
    #: Cloudflare R2 URL of the original (unmasked) enrollment image.
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    classroom: Mapped[Classroom | None] = relationship(back_populates="students", lazy="raise")


class ClassSession(Base):
    __tablename__ = "class_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classrooms.class_id"),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    faculty: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)


class Attendance(Base):
    __tablename__ = "attendance"

    attendance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("class_sessions.session_id"),
        nullable=False,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id"),
        nullable=False,
    )
    #: First detection that marked the student present, or the session close
    #: instant for rows created by the absence pass.
    timestamp: Mapped[dt.datetime] = mapped_column(
        "timestamp",
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    #: Highest recognition confidence observed across the session's capture
    #: intervals (``ABSENT_CONFIDENCE`` for absent rows).
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_attendance_session_id_student_id"),
    )
