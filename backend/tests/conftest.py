"""Shared fixtures.

The PostgreSQL-backed fixtures only run when ``ARGUS_TEST_DATABASE_URL`` points
at a throwaway database; every table is dropped and recreated per test.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.container import Container, build_container
from app.core.config import Settings
from app.db.models import Base
from app.main import create_app
from app.schemas.classroom import ClassroomCreate
from app.schemas.session import SessionCreate
from app.schemas.student import StudentCreate

TEST_DATABASE_URL = os.getenv("ARGUS_TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set ARGUS_TEST_DATABASE_URL to run the PostgreSQL integration tests",
)

T0 = dt.datetime(2026, 8, 6, 9, 0, 0)


def make_settings(**overrides: object) -> Settings:
    """Settings isolated from the developer's .env and shell environment.

    ``_env_file=None`` only ignores ``.env``; an exported ``ARGUS_MODEL_ROOT``
    would otherwise still leak in and change which adapters the suite exercises.
    """
    defaults: dict[str, object] = {
        "database_url": None,
        "chroma_mode": "disabled",
        "object_storage_mode": "disabled",
        "model_root": None,
        "detector_model_path": None,
        "embedder_model_path": None,
        "match_threshold": None,
        "review_threshold": None,
        "minimum_margin": None,
        "capture_interval_seconds": 0.05,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


def make_client(settings: Settings) -> AsyncClient:
    # ASGI client bound to a freshly built application.
    return AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://testserver"
    )


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    async with make_client(settings) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def client_unreachable_db() -> AsyncIterator[AsyncClient]:
    """Client whose DSN is valid but points nowhere.

    Exercises the paths that only run once the services exist: request
    validation, and the failure mode when PostgreSQL is down.
    """
    settings = make_settings(
        database_url="postgresql+asyncpg://argus:argus@127.0.0.1:1/argus_unreachable"
    )
    async with make_client(settings) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def db_container() -> AsyncIterator[Container]:
    # Fully wired application against an empty test database.
    container = build_container(make_settings(database_url=TEST_DATABASE_URL))
    assert container.database is not None
    async with container.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield container
    finally:
        await container.shutdown()


async def seed(container: Container, *, students: int = 3):
    # A classroom, a roster and one ACTIVE session.
    services = container.services
    classroom = await services.classrooms.create(
        ClassroomCreate(class_name="CSE-A", department="CSE", semester=5, strength=students)
    )
    roster = [
        await services.students.create(
            StudentCreate(
                student_name=f"Student {index}",
                roll_no=index,
                class_id=classroom.class_id,
                image_url=f"https://r2.example.com/enrollment/{index}.jpg",
            )
        )
        for index in range(1, students + 1)
    ]
    session = await services.sessions.create(
        SessionCreate(
            class_id=classroom.class_id,
            subject="Computer Vision",
            faculty="Dr. Placeholder",
            date=dt.date(2026, 8, 6),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 0),
        )
    )
    return classroom, roster, session
