"""Attendance capture, finalisation and reporting.

Timeline of a session: it is created ACTIVE, recognition pushes observations
into the capture buffer, the flusher persists them once per interval so the
register fills up during the lecture, and closing it flushes what is still
buffered, writes Absent for every roster member without a row and flips the
status - all in one transaction with the session row locked.

Absence is therefore derived exactly once, at close, from "who was never
recognised", rather than guessed while the lecture runs.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Row

from app.core.errors import ArgusError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.utils import chunked, utc_now
from app.db.models import Attendance, ClassSession
from app.db.session import Database
from app.domain import AttendanceStatus, Observation, SessionStatus
from app.repositories.attendance import AttendanceRepository
from app.repositories.classroom import ClassroomRepository
from app.repositories.session import ClassSessionRepository
from app.schemas.attendance import AttendanceSummary
from app.schemas.session import SessionCloseReport
from app.services.capture import ObservationBuffer

logger = get_logger(__name__)


class AttendanceService:
    def __init__(self, database: Database, buffer: ObservationBuffer, *, chunk_size: int) -> None:
        self._db = database
        self._buffer = buffer
        self._chunk_size = chunk_size

    async def record(self, session_id: uuid.UUID, observations: Sequence[Observation]) -> int:
        # Buffer observations from the recognition path; no database round trip.
        return await self._buffer.record(session_id, observations)

    async def persist(self, session_id: uuid.UUID, observations: Sequence[Observation]) -> int:
        # Write one interval's coalesced observations; returns rows written.
        if not observations:
            return 0
        written = 0
        async with self._db.session() as session:
            repository = AttendanceRepository(session)
            for chunk in chunked(observations, self._chunk_size):
                written += len(await repository.upsert_present(session_id, chunk))
        if written != len(observations):
            logger.warning(
                "Session %s: %d observations skipped (session not ACTIVE or student off roster)",
                session_id,
                len(observations) - written,
            )
        return written

    async def close_session(self, session_id: uuid.UUID) -> SessionCloseReport:
        # Final flush, absence pass and status flip, in one locked transaction.
        pending = await self._buffer.drain(session_id)
        closed_at = utc_now()
        try:
            async with self._db.session() as session:
                sessions = ClassSessionRepository(session)
                class_session = await sessions.get_for_update(session_id)
                if class_session is None:
                    raise NotFoundError(f"Session {session_id} does not exist.")
                if class_session.status != SessionStatus.ACTIVE:
                    raise ConflictError(
                        f"Session {session_id} is already {class_session.status}.",
                        details={"status": class_session.status},
                    )

                attendance = AttendanceRepository(session)
                for chunk in chunked(pending, self._chunk_size):
                    await attendance.upsert_present(session_id, chunk)
                absent_marked = await attendance.insert_absentees(session_id, closed_at)
                await sessions.mark_closed(session_id)

                counts = await attendance.counts_for_session(session_id)
                roster = await ClassroomRepository(session).roster_count(class_session.class_id)
        except ArgusError:
            raise
        except Exception:
            await self._buffer.requeue(session_id, pending)
            raise

        logger.info(
            "Closed session %s: present=%d absent=%d roster=%d",
            session_id,
            counts.present,
            counts.absent,
            roster,
        )
        return SessionCloseReport(
            session_id=session_id,
            closed_at=closed_at,
            present=counts.present,
            absent_marked=absent_marked,
            roster_count=roster,
        )

    async def summary(self, session_id: uuid.UUID) -> AttendanceSummary:
        # Roster size against present and absent counts for one session.
        async with self._db.session() as session:
            class_session = await ClassSessionRepository(session).get(session_id)
            if class_session is None:
                raise NotFoundError(f"Session {session_id} does not exist.")
            roster = await ClassroomRepository(session).roster_count(class_session.class_id)
            counts = await AttendanceRepository(session).counts_for_session(session_id)
        return AttendanceSummary(
            session_id=session_id,
            session_status=SessionStatus(class_session.status),
            roster_count=roster,
            present=counts.present,
            absent=counts.absent,
        )

    async def register(
        self,
        session_id: uuid.UUID,
        *,
        status: AttendanceStatus | None,
        after_roll_no: int | None,
        limit: int,
    ) -> Sequence[Row[tuple[Attendance, str, int]]]:
        # Attendance register for one session, keyset-paged by roll number.
        async with self._db.session() as session:
            if await ClassSessionRepository(session).get(session_id) is None:
                raise NotFoundError(f"Session {session_id} does not exist.")
            return await AttendanceRepository(session).list_for_session(
                session_id, status=status, after_roll_no=after_roll_no, limit=limit
            )

    async def student_history(
        self, student_id: uuid.UUID, *, limit: int, offset: int
    ) -> Sequence[Row[tuple[Attendance, ClassSession]]]:
        # One student's attendance across sessions.
        async with self._db.session() as session:
            return await AttendanceRepository(session).list_for_student(
                student_id, limit=limit, offset=offset
            )
