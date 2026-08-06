"""Attendance persistence.

Both write paths are single set-based statements, so their cost is independent
of how many students are involved: one round trip per capture interval, and one
for the whole absence pass.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Row, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attendance, ClassSession, Student
from app.domain import ABSENT_CONFIDENCE, AttendanceStatus, Observation, SessionStatus

#: The joins make PostgreSQL enforce, in the same statement, that the session is
#: still ACTIVE and that the recognised student is on that classroom's roster.
_UPSERT_PRESENT = text(
    """
    INSERT INTO attendance (session_id, student_id, "timestamp", confidence, status)
    SELECT cs.session_id, s.student_id, obs.observed_at, obs.confidence, :present
    FROM unnest(
             CAST(:student_ids AS uuid[]),
             CAST(:observed_at AS timestamp[]),
             CAST(:confidences AS double precision[])
         ) AS obs(student_id, observed_at, confidence)
    JOIN class_sessions cs
      ON cs.session_id = CAST(:session_id AS uuid) AND cs.status = :active
    JOIN students s
      ON s.student_id = obs.student_id AND s.class_id = cs.class_id
    ON CONFLICT (session_id, student_id) DO UPDATE
       SET confidence = GREATEST(attendance.confidence, EXCLUDED.confidence),
           "timestamp" = LEAST(attendance."timestamp", EXCLUDED."timestamp"),
           status = :present
    RETURNING student_id
    """
)

_INSERT_ABSENTEES = text(
    """
    INSERT INTO attendance (session_id, student_id, "timestamp", confidence, status)
    SELECT cs.session_id, s.student_id, CAST(:closed_at AS timestamp), :confidence, :absent
    FROM class_sessions cs
    JOIN students s ON s.class_id = cs.class_id
    WHERE cs.session_id = CAST(:session_id AS uuid)
      AND NOT EXISTS (
          SELECT 1 FROM attendance a
          WHERE a.session_id = cs.session_id AND a.student_id = s.student_id
      )
    ON CONFLICT (session_id, student_id) DO NOTHING
    """
)


@dataclass(frozen=True, slots=True)
class SessionCounts:
    present: int
    absent: int

    @property
    def recorded(self) -> int:
        # Roster members with any attendance row for this session.
        return self.present + self.absent


class AttendanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_present(
        self, session_id: uuid.UUID, observations: Sequence[Observation]
    ) -> list[uuid.UUID]:
        # One interval's observations, at most one per student because a single
        # ON CONFLICT DO UPDATE may not touch the same row twice. Rows filtered
        # out by the ACTIVE/roster join are reported back by omission.
        if not observations:
            return []
        result = await self._session.execute(
            _UPSERT_PRESENT,
            {
                "session_id": session_id,
                "student_ids": [obs.student_id for obs in observations],
                "observed_at": [obs.observed_at for obs in observations],
                "confidences": [float(obs.confidence) for obs in observations],
                "present": AttendanceStatus.PRESENT.value,
                "active": SessionStatus.ACTIVE.value,
            },
        )
        return [row[0] for row in result.fetchall()]

    async def insert_absentees(self, session_id: uuid.UUID, closed_at: dt.datetime) -> int:
        # Write Absent for every roster member with no attendance row.
        result = await self._session.execute(
            _INSERT_ABSENTEES,
            {
                "session_id": session_id,
                "closed_at": closed_at,
                "confidence": ABSENT_CONFIDENCE,
                "absent": AttendanceStatus.ABSENT.value,
            },
        )
        return int(result.rowcount or 0)

    async def delete_for_student(self, student_id: uuid.UUID) -> int:
        # The foreign keys carry no ON DELETE rule, so history goes first.
        result = await self._session.execute(
            delete(Attendance).where(Attendance.student_id == student_id)
        )
        return int(result.rowcount or 0)

    async def counts_for_session(self, session_id: uuid.UUID) -> SessionCounts:
        # Present and absent totals in one query.
        stmt = select(
            func.count().filter(Attendance.status == AttendanceStatus.PRESENT.value),
            func.count().filter(Attendance.status == AttendanceStatus.ABSENT.value),
        ).where(Attendance.session_id == session_id)
        present, absent = (await self._session.execute(stmt)).one()
        return SessionCounts(present=int(present), absent=int(absent))

    async def list_for_session(
        self,
        session_id: uuid.UUID,
        *,
        status: AttendanceStatus | None,
        after_roll_no: int | None,
        limit: int,
    ) -> Sequence[Row[tuple[Attendance, str, int]]]:
        # Register for a session, keyset-paged by roll number.
        stmt = (
            select(Attendance, Student.student_name, Student.roll_no)
            .join(Student, Student.student_id == Attendance.student_id)
            .where(Attendance.session_id == session_id)
            .order_by(Student.roll_no)
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Attendance.status == status.value)
        if after_roll_no is not None:
            stmt = stmt.where(Student.roll_no > after_roll_no)
        return (await self._session.execute(stmt)).all()

    async def list_for_student(
        self, student_id: uuid.UUID, *, limit: int, offset: int
    ) -> Sequence[Row[tuple[Attendance, ClassSession]]]:
        # One student's history, most recent session first.
        stmt = (
            select(Attendance, ClassSession)
            .join(ClassSession, ClassSession.session_id == Attendance.session_id)
            .where(Attendance.student_id == student_id)
            .order_by(ClassSession.date.desc(), ClassSession.start_time.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self._session.execute(stmt)).all()
