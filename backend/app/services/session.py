"""Class session use cases."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from app.core.errors import ConflictError, NotFoundError
from app.db.integrity import integrity_guard
from app.db.models import ClassSession
from app.db.session import Database
from app.domain import SessionStatus
from app.repositories.session import ClassSessionRepository
from app.schemas.session import SessionCreate

_CONSTRAINTS = {"fk_class_sessions_class_id": "The referenced classroom does not exist."}


class SessionService:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create(self, payload: SessionCreate) -> ClassSession:
        # Recognition fetches *the* active session for a classroom, so a second
        # one would make that lookup ambiguous. The schema declares no constraint
        # to lean on, so the check runs under an advisory lock held by this
        # transaction until the insert commits.
        async with self._db.session() as session, integrity_guard(_CONSTRAINTS):
            repository = ClassSessionRepository(session)
            if payload.status is SessionStatus.ACTIVE:
                await repository.lock_active_slot(payload.class_id)
                active = await repository.list_active_for_class(payload.class_id)
                if active:
                    raise ConflictError(
                        "This classroom already has an ACTIVE session. "
                        "Close it before opening another one.",
                        details={"active_session_ids": [str(s.session_id) for s in active]},
                    )
            return await repository.create(
                class_id=payload.class_id,
                subject=payload.subject,
                faculty=payload.faculty,
                date=payload.date,
                start_time=payload.start_time,
                end_time=payload.end_time,
                status=payload.status,
            )

    async def get(self, session_id: uuid.UUID) -> ClassSession:
        # One session, or 404.
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
        # Filtered page of sessions.
        async with self._db.session() as session:
            return await ClassSessionRepository(session).list(
                class_id=class_id,
                status=status,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
