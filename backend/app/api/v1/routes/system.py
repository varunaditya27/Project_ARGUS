"""Runtime introspection: /health, /runtime, /models (docs/design.md)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Response

from app.api.deps import ContainerDep
from app.core.errors import ArgusError
from app.recognition.factory import RecognitionStack
from app.schemas.recognition import ComponentStatusOut, ModelsResponse, ThresholdsOut

router = APIRouter(tags=["system"])

_STARTED_AT = time.monotonic()


async def _check(name: str, probe) -> dict[str, object]:
    try:
        await probe()
    except ArgusError as exc:
        return {"name": name, "healthy": False, "code": exc.code, "detail": exc.message}
    except Exception as exc:
        return {"name": name, "healthy": False, "code": "unexpected_error", "detail": str(exc)}
    return {"name": name, "healthy": True, "code": None, "detail": "ok"}


@router.get("/health", summary="Liveness plus dependency probes")
async def health(container: ContainerDep, response: Response) -> dict[str, object]:
    checks = []
    if container.database is None:
        checks.append(
            {
                "name": "postgresql",
                "healthy": False,
                "code": "dependency_not_configured",
                "detail": "ARGUS_DATABASE_URL is not set",
            }
        )
    else:
        checks.append(await _check("postgresql", container.database.ping))

    index_status = container.stack.index.status()
    if index_status.configured:
        checks.append(await _check("chromadb", container.stack.index.ping))
    else:
        checks.append(
            {
                "name": "chromadb",
                "healthy": False,
                "code": "dependency_not_configured",
                "detail": index_status.detail,
            }
        )

    healthy = all(check["healthy"] for check in checks)
    response.status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@router.get("/runtime", summary="Process and capture configuration")
async def runtime(container: ContainerDep) -> dict[str, object]:
    settings = container.settings
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.monotonic() - _STARTED_AT, 3),
        "timezone": "UTC (all timestamps are naive UTC)",
        "capture_interval_seconds": settings.capture_interval_seconds,
        "capture": await container.buffer.stats(),
        "database_configured": container.database is not None,
        "recognition_ready": container.stack.ready,
    }


@router.get("/models", response_model=ModelsResponse, summary="Vision component wiring")
async def models(container: ContainerDep) -> ModelsResponse:
    stack: RecognitionStack = container.stack
    settings = container.settings
    return ModelsResponse(
        components=[ComponentStatusOut.model_validate(s) for s in stack.statuses],
        thresholds=ThresholdsOut(
            match_threshold=settings.match_threshold,
            review_threshold=settings.review_threshold,
            minimum_margin=settings.minimum_margin,
            calibrated=stack.thresholds.calibrated,
        ),
        embedding_dim=stack.embedding_dim,
        mask_variants=list(stack.mask_variants),
        recognition_ready=stack.ready,
    )
