"""Composition root.

Everything with a lifetime longer than a request (engine pool, capture buffer,
flusher task, recognition stack) is created here once and handed to the services.
Routers never construct dependencies themselves - they pull them from
:mod:`app.api.deps`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.attendance.buffer import ObservationBuffer
from app.attendance.flusher import IntervalFlusher
from app.core.config import Settings
from app.core.errors import DependencyNotConfiguredError
from app.core.logging import get_logger
from app.db.database import Database, build_database
from app.recognition.factory import RecognitionStack, build_recognition_stack
from app.services.attendance import AttendanceService
from app.services.classroom import ClassroomService
from app.services.recognition import RecognitionService
from app.services.session import SessionService
from app.services.student import StudentService

logger = get_logger(__name__)

_NO_DATABASE = (
    "PostgreSQL is not configured. Set ARGUS_DATABASE_URL "
    "(postgresql+asyncpg://user:password@host:5432/argus)."
)


@dataclass(frozen=True, slots=True)
class ServiceRegistry:
    classrooms: ClassroomService
    students: StudentService
    sessions: SessionService
    attendance: AttendanceService
    recognition: RecognitionService


@dataclass(slots=True)
class Container:
    settings: Settings
    stack: RecognitionStack
    buffer: ObservationBuffer
    database: Database | None
    flusher: IntervalFlusher | None
    registry: ServiceRegistry | None

    @property
    def services(self) -> ServiceRegistry:
        """Database-backed services; 503 when PostgreSQL is not configured."""
        if self.registry is None:
            raise DependencyNotConfiguredError(_NO_DATABASE)
        return self.registry

    async def startup(self) -> None:
        if self.flusher is not None:
            await self.flusher.start()

    async def shutdown(self) -> None:
        if self.flusher is not None:
            await self.flusher.stop()
        if self.database is not None:
            await self.database.dispose()


def build_container(settings: Settings) -> Container:
    stack = build_recognition_stack(settings)
    buffer = ObservationBuffer(max_sessions=settings.capture_max_buffered_sessions)
    database = build_database(settings)

    registry: ServiceRegistry | None = None
    flusher: IntervalFlusher | None = None

    if database is not None:
        attendance = AttendanceService(
            database, buffer, chunk_size=settings.capture_flush_chunk_size
        )
        students = StudentService(database, stack.index)
        registry = ServiceRegistry(
            classrooms=ClassroomService(database),
            students=students,
            sessions=SessionService(database),
            attendance=attendance,
            recognition=RecognitionService(
                stack=stack, settings=settings, students=students, attendance=attendance
            ),
        )
        flusher = IntervalFlusher(
            buffer=buffer,
            persist=attendance.persist,
            interval_seconds=settings.capture_interval_seconds,
        )

    logger.info(
        "Container ready (database=%s, recognition_ready=%s, capture_interval=%.1fs)",
        database is not None,
        stack.ready,
        settings.capture_interval_seconds,
    )
    return Container(
        settings=settings,
        stack=stack,
        buffer=buffer,
        database=database,
        flusher=flusher,
        registry=registry,
    )
