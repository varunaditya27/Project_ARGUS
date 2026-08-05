from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.container import build_container
from app.core.config import Settings
from app.main import create_app

TEST_DATABASE_URL = os.getenv("ARGUS_TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set ARGUS_TEST_DATABASE_URL to run the PostgreSQL integration tests",
)


def make_settings(**overrides: object) -> Settings:
    """Settings isolated from the developer's .env and shell environment."""
    defaults: dict[str, object] = {
        "database_url": None,
        "chroma_mode": "disabled",
        "match_threshold": None,
        "review_threshold": None,
        "minimum_margin": None,
        "capture_interval_seconds": 0.05,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def container(settings: Settings):
    return build_container(settings)


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    async with make_client(settings) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def client_unreachable_db() -> AsyncIterator[AsyncClient]:
    """Client whose DSN is syntactically valid but points nowhere.

    Lets the tests exercise the paths that only run once the services exist:
    request validation, and the failure mode when PostgreSQL is down.
    """
    settings = make_settings(
        database_url="postgresql+asyncpg://argus:argus@127.0.0.1:1/argus_unreachable"
    )
    async with make_client(settings) as http_client:
        yield http_client


def make_client(settings: Settings) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://testserver"
    )
