"""Initial schema: classrooms, students, class_sessions, attendance.

A literal materialisation of docs/db.md -- the four documented tables and the
two documented constraints, with no additional index, CHECK constraint or
foreign-key delete rule. See app/db/models.py for the two invariants that the
service layer upholds as a result.

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
        ),
    )

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
        ),
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
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.student_id"],
            name="fk_attendance_student_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("attendance")
    op.drop_table("class_sessions")
    op.drop_table("students")
    op.drop_table("classrooms")
