"""Async engine / session lifecycle.

One :class:`Database` instance per process owns the connection pool. Requests get
a session from :meth:`Database.session`; write paths run inside a single
transaction so a failed request can never leave attendance half-written.
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
from app.core.errors import ConflictError, DependencyNotConfiguredError, DependencyUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


def _unavailable(exc: BaseException) -> DependencyUnavailableError:
    return DependencyUnavailableError(
        "PostgreSQL is unavailable or rejected the statement.",
        details={"driver_error": str(exc.__cause__ or exc)},
    )


class Database:
    def __init__(self, url: str, settings: Settings) -> None:
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
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Session bound to one transaction: commit on success, rollback on error.

        Driver-level failures are translated here so callers only ever see domain
        errors and a dead database surfaces as a clear 503 instead of a traceback.
        """
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
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError) as exc:
            raise _unavailable(exc) from exc

    async def dispose(self) -> None:
        await self._engine.dispose()


def build_database(settings: Settings) -> Database | None:
    if not settings.database_url:
        logger.warning("ARGUS_DATABASE_URL is not set; database-backed endpoints will return 503")
        return None
    return Database(settings.database_url, settings)


def require_database(database: Database | None) -> Database:
    if database is None:
        raise DependencyNotConfiguredError(
            "PostgreSQL is not configured. Set ARGUS_DATABASE_URL "
            "(postgresql+asyncpg://user:password@host:5432/argus)."
        )
    return database
