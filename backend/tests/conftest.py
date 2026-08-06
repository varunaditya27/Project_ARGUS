"""Shared fixtures and the guards that decide which suites can run here.

Three tiers live under this directory. ``unit`` needs nothing. ``integration``
needs PostgreSQL (``ARGUS_TEST_DATABASE_URL``) and, for the storage cases, a
temporary directory. ``acceptance`` additionally needs the ONNX pack and a
Chroma store, and skips with a named reason when either is absent, so a machine
without the models still reports honestly instead of silently passing.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.container import Container, build_container
from app.core.config import Settings
from app.db.models import Base
from app.main import create_app

TEST_DATABASE_URL = os.getenv("ARGUS_TEST_DATABASE_URL")

FIXTURES = Path(__file__).parent / "fixtures"
#: Public LFW portrait, the only face image the repository ships.
SAMPLE_FACE = FIXTURES / "sample_face.jpg"

#: Where the InsightFace buffalo_l pack lives; the repository root by default.
MODEL_ROOT = Path(
    os.getenv("ARGUS_TEST_MODEL_ROOT", Path(__file__).parents[2] / "models" / "buffalo_l")
)
DETECTOR = MODEL_ROOT / "det_10g.onnx"
EMBEDDER = MODEL_ROOT / "w600k_r50.onnx"

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set ARGUS_TEST_DATABASE_URL to run the PostgreSQL integration tests",
)
requires_models = pytest.mark.skipif(
    not (DETECTOR.exists() and EMBEDDER.exists()),
    reason=f"no ONNX pack under {MODEL_ROOT}; see backend/README.md",
)


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


async def reset_database(url: str) -> None:
    # Drop and recreate every table so a test starts from an empty database.
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


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
    assert TEST_DATABASE_URL
    await reset_database(TEST_DATABASE_URL)
    container = build_container(make_settings(database_url=TEST_DATABASE_URL))
    try:
        yield container
    finally:
        await container.shutdown()


@pytest_asyncio.fixture
async def db_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    # HTTP client over an empty test database, with images written to tmp_path.
    assert TEST_DATABASE_URL
    await reset_database(TEST_DATABASE_URL)
    settings = make_settings(
        database_url=TEST_DATABASE_URL,
        object_storage_mode="local",
        local_storage_path=tmp_path / "media",
        local_public_base_url="http://testserver/media",
    )
    async with make_client(settings) as http_client:
        yield http_client
