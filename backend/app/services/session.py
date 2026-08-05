from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from app.core.errors import NotFoundError
from app.db.database import Database
from app.db.integrity import integrity_guard
from app.db.models import ClassSession
from app.domain.enums import SessionStatus
from app.repositories.session import ClassSessionRepository
from app.schemas.session import SessionCreate

_CONSTRAINT_MESSAGES = {
    "uq_class_sessions_active_per_class": (
        "This classroom already has an ACTIVE session. Close it before opening another one."
    ),
    "fk_class_sessions_class_id": "The referenced classroom does not exist.",
    "ck_class_sessions_time_range": "end_time must be after start_time.",
}


class SessionService:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create(self, payload: SessionCreate) -> ClassSession:
        async with self._db.session() as session, integrity_guard(_CONSTRAINT_MESSAGES):
            return await ClassSessionRepository(session).create(
                class_id=payload.class_id,
                subject=payload.subject,
                faculty=payload.faculty,
                date=payload.date,
                start_time=payload.start_time,
                end_time=payload.end_time,
                status=payload.status,
            )

    async def get(self, session_id: uuid.UUID) -> ClassSession:
        async with self._db.session() as session:
            class_session = await ClassSessionRepository(session).get(session_id)
        if class_session is None:
            raise NotFoundError(f"Session {session_id} does not exist.")
        return class_session

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
        async with self._db.session() as session:
            return await ClassSessionRepository(session).list(
                class_id=class_id,
                status=status,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
