"""Class session queries."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClassSession
from app.domain import SessionStatus

#: Arbitrary namespace so these locks cannot collide with another application's.
LOCK_NAMESPACE = 0x41475553

#: Transaction-scoped, so COMMIT or ROLLBACK releases it with no unlock call.
_LOCK_ACTIVE_SLOT = text("SELECT pg_advisory_xact_lock(:ns, hashtext(CAST(:class_id AS text)))")


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
        # Insert and flush so the generated session_id is available to the caller.
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
        # Primary key lookup.
        return await self._session.get(ClassSession, session_id)

    async def get_for_update(self, session_id: uuid.UUID) -> ClassSession | None:
        # Row-locked read so two concurrent closes cannot interleave.
        stmt = select(ClassSession).where(ClassSession.session_id == session_id).with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def lock_active_slot(self, class_id: uuid.UUID) -> None:
        # docs/db.md declares no partial unique index, so the "one ACTIVE session
        # per classroom" rule is serialised with an advisory lock instead.
        await self._session.execute(
            _LOCK_ACTIVE_SLOT, {"ns": LOCK_NAMESPACE, "class_id": str(class_id)}
        )

    async def list_active_for_class(self, class_id: uuid.UUID) -> Sequence[ClassSession]:
        # Every ACTIVE session for a classroom; nothing in the schema caps it at one.
        stmt = select(ClassSession).where(
            ClassSession.class_id == class_id,
            ClassSession.status == SessionStatus.ACTIVE.value,
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list(
        self,
        *,
        class_id: uuid.UUID | None,
        status: SessionStatus | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
        limit: int,
        offset: int,
    ) -> Sequence[ClassSession]:
        # Filtered page, most recent session first.
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
        return (await self._session.execute(stmt.limit(limit).offset(offset))).scalars().all()

    async def mark_closed(self, session_id: uuid.UUID) -> bool:
        # Flip ACTIVE -> CLOSED; False when it was not ACTIVE any more.
        stmt = (
            update(ClassSession)
            .where(
                ClassSession.session_id == session_id,
                ClassSession.status == SessionStatus.ACTIVE.value,
            )
            .values(status=SessionStatus.CLOSED.value)
        )
        return bool((await self._session.execute(stmt)).rowcount)
