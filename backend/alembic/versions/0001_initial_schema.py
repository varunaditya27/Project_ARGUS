"""Initial schema: classrooms, students, class_sessions, attendance.

This is a literal materialisation of docs/db.md. Nothing beyond those four
tables is created; the only additions are indexes, CHECK constraints over the
already-documented status vocabularies, and FK delete rules -- see
docs/database_setup.md -> "Schema mapping decisions".

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_NEW_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "classrooms",
        sa.Column("class_id", _UUID, server_default=_NEW_UUID, nullable=False),
        sa.Column("class_name", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("class_id", name="pk_classrooms"),
        # CHECK names are bare: the metadata naming convention expands them to
        # ck_<table>_<name>, matching app/db/models.py.
        sa.CheckConstraint("semester > 0", name="semester_positive"),
        sa.CheckConstraint("strength >= 0", name="strength_non_negative"),
    )

    op.create_table(
        "students",
        sa.Column("student_id", _UUID, server_default=_NEW_UUID, nullable=False),
        sa.Column("student_name", sa.Text(), nullable=False),
        sa.Column("roll_no", sa.Integer(), nullable=False),
        sa.Column("class_id", _UUID, nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("student_id", name="pk_students"),
        sa.UniqueConstraint("roll_no", name="uq_students_roll_no"),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classrooms.class_id"],
            name="fk_students_class_id",
            ondelete="SET NULL",
        ),
    )
    # Roster scan + keyset pagination by roll number inside a classroom.
    op.create_index("ix_students_class_id_roll_no", "students", ["class_id", "roll_no"])

    op.create_table(
        "class_sessions",
        sa.Column("session_id", _UUID, server_default=_NEW_UUID, nullable=False),
        sa.Column("class_id", _UUID, nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("faculty", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name="pk_class_sessions"),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classrooms.class_id"],
            name="fk_class_sessions_class_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="status_domain"),
        sa.CheckConstraint("end_time > start_time", name="time_range"),
    )
    op.create_index("ix_class_sessions_class_id_date", "class_sessions", ["class_id", "date"])
    # "Fetch Active Class Session" has a single answer only if one session per
    # classroom can be ACTIVE at a time.
    op.create_index(
        "uq_class_sessions_active_per_class",
        "class_sessions",
        ["class_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "attendance",
        sa.Column("attendance_id", _UUID, server_default=_NEW_UUID, nullable=False),
        sa.Column("session_id", _UUID, nullable=False),
        sa.Column("student_id", _UUID, nullable=False),
        sa.Column("timestamp", postgresql.TIMESTAMP(), server_default=_NOW, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("attendance_id", name="pk_attendance"),
        sa.UniqueConstraint("session_id", "student_id", name="uq_attendance_session_id_student_id"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["class_sessions.session_id"],
            name="fk_attendance_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.student_id"],
            name="fk_attendance_student_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("status IN ('Present', 'Absent')", name="status_domain"),
        sa.CheckConstraint("confidence >= -1.0 AND confidence <= 1.0", name="confidence_range"),
    )
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_attendance_student_id", table_name="attendance")
    op.drop_table("attendance")
    op.drop_index("uq_class_sessions_active_per_class", table_name="class_sessions")
    op.drop_index("ix_class_sessions_class_id_date", table_name="class_sessions")
    op.drop_table("class_sessions")
    op.drop_index("ix_students_class_id_roll_no", table_name="students")
    op.drop_table("students")
    op.drop_table("classrooms")
