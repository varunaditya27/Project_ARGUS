"""Async engine and session lifecycle.

One Database instance per process owns the connection pool. Every unit of work
runs in a single transaction, so a failed request cannot leave attendance
half-written.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.errors import ConflictError, DependencyUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


def _unavailable(exc: BaseException) -> DependencyUnavailableError:
    # Driver failures surface as a 503 rather than a traceback.
    return DependencyUnavailableError(
        "PostgreSQL is unavailable or rejected the statement.",
        details={"driver_error": str(exc.__cause__ or exc)},
    )


class Database:
    def __init__(self, url: str, settings: Settings) -> None:
        # A statement timeout bounds any single query a request can trigger.
        self._engine: AsyncEngine = create_async_engine(
            url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle_seconds,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "application_name": "argus-backend",
                    "statement_timeout": str(settings.db_statement_timeout_ms),
                }
            },
        )
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        # Exposed for schema creation in the benchmarks and the test harness.
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        # One transaction: commit on success, roll back on any error.
        try:
            async with self._sessionmaker() as session, session.begin():
                yield session
        except IntegrityError as exc:
            raise ConflictError(
                "The request violates a database constraint.",
                details={"driver_error": str(exc.orig)},
            ) from exc
        except (SQLAlchemyError, OSError) as exc:
            raise _unavailable(exc) from exc

    async def ping(self) -> None:
        # Health probe.
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError) as exc:
            raise _unavailable(exc) from exc

    async def dispose(self) -> None:
        # Close the pool at shutdown.
        await self._engine.dispose()


def build_database(settings: Settings) -> Database | None:
    # None when no URL is configured; database-backed routes then return 503.
    if not settings.database_url:
        logger.warning("ARGUS_DATABASE_URL is not set; database-backed endpoints will return 503")
        return None
    return Database(settings.database_url, settings)
