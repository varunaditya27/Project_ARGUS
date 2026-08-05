from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClassSession
from app.domain.enums import SessionStatus


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

    async def get_active_for_class(self, class_id: uuid.UUID) -> ClassSession | None:
        stmt = select(ClassSession).where(
            ClassSession.class_id == class_id,
            ClassSession.status == SessionStatus.ACTIVE.value,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

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
