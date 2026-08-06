"""ORM mapping of the schema in docs/db.md.

The mapping is deliberately literal: four tables, their columns and the two
documented constraints, nothing else. Two consequences are therefore handled in
the service layer instead of by DDL - foreign keys default to NO ACTION, so
referencing rows are deleted explicitly, and nothing stops a second ACTIVE
session, so SessionService serialises that check with an advisory lock.

Face embeddings are not stored here; they live in ChromaDB.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Predictable names keep the models, the Alembic revision and the ON CONFLICT
#: targets in app.repositories.attendance in sync.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

_UUID_PK = text("gen_random_uuid()")
_NOW = text("CURRENT_TIMESTAMP")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Classroom(Base):
    __tablename__ = "classrooms"

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    class_name: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str] = mapped_column(Text, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Declared strength. The live roster count is derived from `students` and is
    #: what the absence pass uses.
    strength: Mapped[int] = mapped_column(Integer, nullable=False)


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    student_name: Mapped[str] = mapped_column(Text, nullable=False)
    roll_no: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classrooms.class_id"), nullable=True
    )
    #: Cloudflare R2 URL of the unmasked enrollment image.
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=False), nullable=False, server_default=_NOW
    )


class ClassSession(Base):
    __tablename__ = "class_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classrooms.class_id"), nullable=False
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
        UUID(as_uuid=True), ForeignKey("class_sessions.session_id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.student_id"), nullable=False
    )
    #: First detection that marked the student present, or the close instant for
    #: rows created by the absence pass.
    timestamp: Mapped[dt.datetime] = mapped_column(
        "timestamp", TIMESTAMP(timezone=False), nullable=False, server_default=_NOW
    )
    #: Highest confidence observed across the session (ABSENT_CONFIDENCE if absent).
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_attendance_session_id_student_id"),
    )
