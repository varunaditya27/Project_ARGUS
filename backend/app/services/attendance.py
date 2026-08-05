"""Attendance capture, finalisation and reporting.

Timeline of a session:

1. ``POST /sessions`` creates it with status ACTIVE.
2. Recognition pushes accepted observations into the capture buffer.
3. Every ``ARGUS_CAPTURE_INTERVAL_SECONDS`` the flusher persists them, so the
   register fills up *during* the lecture.
4. ``POST /sessions/{id}/close`` flushes what is still buffered, writes ``Absent``
   for every roster member without a row, and flips the status - all inside one
   transaction with the session row locked.

Absence is therefore derived exactly once, at close, from "who was never
recognised", instead of being guessed while the lecture is running.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Row

from app.attendance.buffer import ObservationBuffer
from app.core.clock import utc_now
from app.core.collections import chunked
from app.core.errors import ArgusError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.database import Database
from app.db.models import Attendance, ClassSession
from app.domain.enums import AttendanceStatus, SessionStatus
from app.domain.observation import Observation
from app.repositories.attendance import AttendanceRepository
from app.repositories.classroom import ClassroomRepository
from app.repositories.session import ClassSessionRepository
from app.schemas.attendance import AttendanceSummary
from app.schemas.session import SessionCloseReport

logger = get_logger(__name__)


class AttendanceService:
    def __init__(
        self,
        database: Database,
        buffer: ObservationBuffer,
        *,
        chunk_size: int,
    ) -> None:
        self._db = database
        self._buffer = buffer
        self._chunk_size = chunk_size

    # ------------------------------------------------------------------ capture
    async def record(self, session_id: uuid.UUID, observations: Sequence[Observation]) -> int:
        """Buffer observations from the recognition path (no database round trip)."""
        return await self._buffer.record(session_id, observations)

    async def persist(self, session_id: uuid.UUID, observations: Sequence[Observation]) -> int:
        """Write one interval's coalesced observations; returns rows written."""
        if not observations:
            return 0
        async with self._db.session() as session:
            repository = AttendanceRepository(session)
            written = 0
            for chunk in chunked(observations, self._chunk_size):
                written += len(await repository.upsert_present(session_id, chunk))
        if written != len(observations):
            logger.warning(
                "Session %s: %d/%d observations skipped (session not ACTIVE or student not on "
                "the roster)",
                session_id,
                len(observations) - written,
                len(observations),
            )
        return written

    async def flush_session(self, session_id: uuid.UUID) -> int:
        observations = await self._buffer.drain(session_id)
        try:
            return await self.persist(session_id, observations)
        except Exception:
            await self._buffer.requeue(session_id, observations)
            raise

    # --------------------------------------------------------------- finalisation
    async def close_session(self, session_id: uuid.UUID) -> SessionCloseReport:
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
                flushed = 0
                for chunk in chunked(pending, self._chunk_size):
                    flushed += len(await attendance.upsert_present(session_id, chunk))

                absent_marked = await attendance.insert_absentees(session_id, closed_at)
                await sessions.mark_closed(session_id)

                counts = await attendance.counts_for_session(session_id)
                roster_count = await ClassroomRepository(session).roster_count(
                    class_session.class_id
                )
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
            roster_count,
        )
        return SessionCloseReport(
            session_id=session_id,
            closed_at=closed_at,
            flushed_observations=flushed,
            present=counts.present,
            absent_marked=absent_marked,
            roster_count=roster_count,
            total_recorded=counts.recorded,
        )

    # ------------------------------------------------------------------ reporting
    async def summary(self, session_id: uuid.UUID) -> AttendanceSummary:
        async with self._db.session() as session:
            class_session = await ClassSessionRepository(session).get(session_id)
            if class_session is None:
                raise NotFoundError(f"Session {session_id} does not exist.")
            classrooms = ClassroomRepository(session)
            classroom = await classrooms.get(class_session.class_id)
            roster_count = await classrooms.roster_count(class_session.class_id)
            counts = await AttendanceRepository(session).counts_for_session(session_id)

        stats = await self._buffer.stats()
        return AttendanceSummary(
            session_id=session_id,
            session_status=class_session.status,
            roster_count=roster_count,
            declared_strength=classroom.strength if classroom else 0,
            present=counts.present,
            absent=counts.absent,
            unrecorded=max(roster_count - counts.recorded, 0),
            pending_observations=stats["pending_observations"],
        )

    async def register(
        self,
        session_id: uuid.UUID,
        *,
        status: AttendanceStatus | None,
        after_roll_no: int | None,
        limit: int,
    ) -> Sequence[Row[tuple[Attendance, str, int]]]:
        async with self._db.session() as session:
            if await ClassSessionRepository(session).get(session_id) is None:
                raise NotFoundError(f"Session {session_id} does not exist.")
            return await AttendanceRepository(session).list_for_session(
                session_id, status=status, after_roll_no=after_roll_no, limit=limit
            )

    async def student_history(
        self, student_id: uuid.UUID, *, limit: int, offset: int
    ) -> Sequence[Row[tuple[Attendance, ClassSession]]]:
        async with self._db.session() as session:
            return await AttendanceRepository(session).list_for_student(
                student_id, limit=limit, offset=offset
            )
