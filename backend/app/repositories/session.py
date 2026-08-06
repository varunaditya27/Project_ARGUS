from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClassSession
from app.domain.enums import SessionStatus

#: Arbitrary namespace so ARGUS locks cannot collide with another application's
#: advisory locks on the same database.
ACTIVE_SESSION_LOCK_NAMESPACE = 0x41475553

#: Transaction-scoped, so it is released by COMMIT or ROLLBACK without any
#: unlock call -- there is no path where a crashed request leaves it held.
_LOCK_ACTIVE_SLOT = text(
    "SELECT pg_advisory_xact_lock(:namespace, hashtext(CAST(:class_id AS text)))"
)


class ClassSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        class_id: uuid.UUID,
        subject: str,
        faculty: str,
        date: dt.date,
        start_time: dt.time,
        end_time: dt.time,
        status: SessionStatus,
    ) -> ClassSession:
        class_session = ClassSession(
            class_id=class_id,
            subject=subject,
            faculty=faculty,
            date=date,
            start_time=start_time,
            end_time=end_time,
            status=status.value,
        )
        self._session.add(class_session)
        await self._session.flush()
        return class_session

    async def get(self, session_id: uuid.UUID) -> ClassSession | None:
        return await self._session.get(ClassSession, session_id)

    async def get_for_update(self, session_id: uuid.UUID) -> ClassSession | None:
        """Row-locked read used by session close so two closers cannot interleave."""
        stmt = select(ClassSession).where(ClassSession.session_id == session_id).with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def lock_active_slot(self, class_id: uuid.UUID) -> None:
        """Serialise "is this classroom already ACTIVE?" against other writers.

        ``docs/db.md`` declares no partial unique index, so the single-ACTIVE-
        session rule the recognition workflow depends on cannot be enforced by a
        constraint. This lock makes the read-then-insert atomic instead, at the
        cost of one round trip on session creation only.
        """
        await self._session.execute(
            _LOCK_ACTIVE_SLOT,
            {"namespace": ACTIVE_SESSION_LOCK_NAMESPACE, "class_id": str(class_id)},
        )

    async def list_active_for_class(self, class_id: uuid.UUID) -> Sequence[ClassSession]:
        """Every ACTIVE session for a classroom.

        Returns a sequence rather than a single row because nothing in the schema
        guarantees there is at most one; callers decide what a second one means.
        """
        stmt = select(ClassSession).where(
            ClassSession.class_id == class_id,
            ClassSession.status == SessionStatus.ACTIVE.value,
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list(
        self,
        *,
        class_id: uuid.UUID | None = None,
        status: SessionStatus | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        limit: int,
        offset: int,
    ) -> Sequence[ClassSession]:
        stmt = select(ClassSession).order_by(
            ClassSession.date.desc(), ClassSession.start_time.desc()
        )
        if class_id is not None:
            stmt = stmt.where(ClassSession.class_id == class_id)
        if status is not None:
            stmt = stmt.where(ClassSession.status == status.value)
        if date_from is not None:
            stmt = stmt.where(ClassSession.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(ClassSession.date <= date_to)
        result = await self._session.execute(stmt.limit(limit).offset(offset))
        return result.scalars().all()

    async def mark_closed(self, session_id: uuid.UUID) -> bool:
        """Flip ACTIVE -> CLOSED. Returns False if it was not ACTIVE any more."""
        stmt = (
            update(ClassSession)
            .where(
                ClassSession.session_id == session_id,
                ClassSession.status == SessionStatus.ACTIVE.value,
            )
            .values(status=SessionStatus.CLOSED.value)
        )
        return bool((await self._session.execute(stmt)).rowcount)
