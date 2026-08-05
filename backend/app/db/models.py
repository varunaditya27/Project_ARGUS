"""ORM mapping of the schema documented in ``docs/db.md``.

Rules followed here:

* The four documented tables, their columns, types and constraints are mapped
  1:1. No extra table or column is introduced.
* Additions are limited to things that carry no new information -- indexes for
  the access paths the attendance flow actually uses, CHECK constraints that
  encode the already-documented status vocabularies, and FK delete rules -- all
  listed in ``docs/database_setup.md``.
* Face embeddings are **not** stored here; they live in ChromaDB.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import AttendanceStatus, SessionStatus

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

    __table_args__ = (
        CheckConstraint("semester > 0", name="semester_positive"),
        CheckConstraint("strength >= 0", name="strength_non_negative"),
    )


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
        ForeignKey("classrooms.class_id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Cloudflare R2 URL of the original (unmasked) enrollment image.
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    classroom: Mapped[Classroom | None] = relationship(back_populates="students", lazy="raise")

    __table_args__ = (
        # Roster scan + keyset pagination inside a classroom, ordered by roll_no.
        Index("ix_students_class_id_roll_no", "class_id", "roll_no"),
    )


class ClassSession(Base):
    __tablename__ = "class_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classrooms.class_id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    faculty: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"status IN ('{SessionStatus.ACTIVE}', '{SessionStatus.CLOSED}')",
            name="status_domain",
        ),
        CheckConstraint("end_time > start_time", name="time_range"),
        Index("ix_class_sessions_class_id_date", "class_id", "date"),
        # "Fetch Active Class Session" (docs/db.md recognition workflow) only has a
        # single answer if at most one session per classroom is ACTIVE. Enforced in
        # the database so concurrent writers cannot both win.
        Index(
            "uq_class_sessions_active_per_class",
            "class_id",
            unique=True,
            postgresql_where=text(f"status = '{SessionStatus.ACTIVE}'"),
        ),
    )


class Attendance(Base):
    __tablename__ = "attendance"

    attendance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("class_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="CASCADE"),
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
        CheckConstraint(
            f"status IN ('{AttendanceStatus.PRESENT}', '{AttendanceStatus.ABSENT}')",
            name="status_domain",
        ),
        # Cosine similarity domain, matching the Pydantic contract in docs/design.md.
        CheckConstraint("confidence >= -1.0 AND confidence <= 1.0", name="confidence_range"),
        # Per-student attendance history. (session_id lookups are already served
        # by the uq_attendance_session_id_student_id index prefix.)
        Index("ix_attendance_student_id", "student_id"),
    )
