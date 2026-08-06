"""Composition root.

Everything with a lifetime longer than a request - the engine pool, the capture
buffer, the flusher task, the recognition stack - is built here once and handed
to the services. Routers pull them from app.api.deps and never construct their
own.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import DependencyNotConfiguredError
from app.core.logging import get_logger
from app.db.session import Database, build_database
from app.recognition.stack import RecognitionStack, build_recognition_stack
from app.services.attendance import AttendanceService
from app.services.capture import IntervalFlusher, ObservationBuffer
from app.services.classroom import ClassroomService
from app.services.offline import OfflineRecognitionService
from app.services.recognition import RecognitionService
from app.services.roster_import import RosterImportService
from app.services.session import SessionService
from app.services.student import StudentService
from app.storage.local import LocalObjectStorage
from app.storage.ports import ObjectStorage
from app.storage.r2 import R2ObjectStorage

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
    offline: OfflineRecognitionService
    roster_import: RosterImportService


@dataclass(slots=True)
class Container:
    settings: Settings
    stack: RecognitionStack
    buffer: ObservationBuffer
    storage: ObjectStorage | None
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
        # Load the ONNX graphs before the first request, then start flushing.
        await asyncio.to_thread(self.stack.warmup)
        if self.flusher is not None:
            await self.flusher.start()

    async def shutdown(self) -> None:
        # Flush what is buffered, then release the pool.
        if self.flusher is not None:
            await self.flusher.stop()
        if self.database is not None:
            await self.database.dispose()


def build_object_storage(settings: Settings) -> ObjectStorage | None:
    # R2 or the local filesystem when configured; otherwise nothing, and the
    # endpoints that need an upload say so rather than half-working.
    if settings.object_storage_mode == "disabled":
        return None
    if settings.object_storage_mode == "local":
        return LocalObjectStorage(
            root=settings.local_storage_path,
            public_base_url=settings.local_public_base_url,
            key_prefix=settings.storage_key_prefix,
        )
    assert settings.r2_endpoint_url is not None
    assert settings.r2_bucket is not None
    assert settings.r2_access_key_id is not None
    assert settings.r2_secret_access_key is not None
    assert settings.r2_public_base_url is not None
    return R2ObjectStorage(
        endpoint_url=settings.r2_endpoint_url,
        bucket=settings.r2_bucket,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=settings.r2_secret_access_key,
        public_base_url=settings.r2_public_base_url,
        key_prefix=settings.storage_key_prefix,
    )


def build_container(settings: Settings) -> Container:
    # Wire the whole application from the settings.
    stack = build_recognition_stack(settings)
    buffer = ObservationBuffer(max_sessions=settings.capture_max_buffered_sessions)
    storage = build_object_storage(settings)
    database = build_database(settings)

    registry: ServiceRegistry | None = None
    flusher: IntervalFlusher | None = None
    if database is not None:
        registry = _build_services(settings, database, stack, buffer, storage)
        flusher = IntervalFlusher(
            buffer=buffer,
            persist=registry.attendance.persist,
            interval_seconds=settings.capture_interval_seconds,
        )

    logger.info(
        "Container ready (database=%s, recognition_ready=%s, object_storage=%s)",
        database is not None,
        stack.ready,
        storage.describe() if storage else "disabled",
    )
    return Container(
        settings=settings,
        stack=stack,
        buffer=buffer,
        storage=storage,
        database=database,
        flusher=flusher,
        registry=registry,
    )


def _build_services(
    settings: Settings,
    database: Database,
    stack: RecognitionStack,
    buffer: ObservationBuffer,
    storage: ObjectStorage | None,
) -> ServiceRegistry:
    # The database-backed half of the application.
    attendance = AttendanceService(database, buffer, chunk_size=settings.capture_flush_chunk_size)
    students = StudentService(database, stack)
    recognition = RecognitionService(
        stack=stack, settings=settings, students=students, attendance=attendance
    )
    return ServiceRegistry(
        classrooms=ClassroomService(database),
        students=students,
        sessions=SessionService(database),
        attendance=attendance,
        recognition=recognition,
        offline=OfflineRecognitionService(
            recognition=recognition, attendance=attendance, settings=settings
        ),
        roster_import=RosterImportService(
            database,
            storage,
            max_csv_bytes=settings.import_max_csv_bytes,
            max_archive_bytes=settings.import_max_archive_bytes,
            max_rows=settings.import_max_rows,
            max_image_bytes=settings.enrollment_max_image_bytes,
        ),
    )
