"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.container import build_container
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.schemas.common import ErrorResponse

DESCRIPTION = """
Attendance backend for Project ARGUS.

* Attendance is captured **while the session is ACTIVE**: recognitions are
  coalesced per capture interval and written continuously.
* Absence is derived **once, when the session is closed** - every roster member
  without an attendance row becomes `Absent` in a single statement.
* Recognition endpoints return `503` until the ONNX models, ChromaDB and the
  calibrated thresholds are in place; they never return a fabricated identity.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Warm the models and run the flusher for the lifetime of the process.
    container = app.state.container
    await container.startup()
    try:
        yield
    finally:
        await container.shutdown()


def create_app(settings: Settings | None = None) -> FastAPI:
    # Build the application; tests pass their own settings.
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

    if settings.object_storage_mode == "local":
        # Enrollment images are written to disk, so this process also serves them.
        settings.local_storage_path.mkdir(parents=True, exist_ok=True)
        app.mount(
            settings.media_url_path,
            StaticFiles(directory=settings.local_storage_path),
            name="media",
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
