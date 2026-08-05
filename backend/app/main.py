"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.container import build_container
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.schemas.common import ErrorResponse

logger = get_logger(__name__)

DESCRIPTION = """
Attendance backend for Project ARGUS.

* Attendance is captured **while the session is ACTIVE**: recognitions are
  coalesced per capture interval and written continuously.
* Absence is derived **once, when the session is closed** - every roster member
  without an attendance row becomes `Absent` in a single set-based statement.
* Recognition endpoints return `503` until the SCRFD/ArcFace/MaskTheFace
  adapters and the calibrated thresholds are in place; they never return
  fabricated identities.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = app.state.container
    await container.startup()
    try:
        yield
    finally:
        await container.shutdown()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, as_json=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        responses={
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse, "description": "A dependency is missing or unavailable"},
        },
    )
    app.state.container = build_container(settings)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
