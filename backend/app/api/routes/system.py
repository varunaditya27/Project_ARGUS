"""Operational routes: /health and /models."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response

from app.api.deps import ContainerDep
from app.core.errors import ArgusError
from app.schemas.recognition import ComponentStatusOut, ModelsResponse, ThresholdsOut

router = APIRouter(tags=["system"])


async def _probe(name: str, check: Callable[[], Awaitable[None]]) -> dict[str, object]:
    # Run one dependency check and report it without raising.
    try:
        await check()
    except ArgusError as exc:
        return {"name": name, "healthy": False, "detail": exc.message}
    except Exception as exc:
        return {"name": name, "healthy": False, "detail": str(exc)}
    return {"name": name, "healthy": True, "detail": "ok"}


@router.get("/health", summary="Liveness plus dependency probes")
async def health(container: ContainerDep, response: Response) -> dict[str, object]:
    # 200 when PostgreSQL and ChromaDB both answer, 503 otherwise.
    checks: list[dict[str, object]] = []
    if container.database is None:
        checks.append(
            {"name": "postgresql", "healthy": False, "detail": "ARGUS_DATABASE_URL is not set"}
        )
    else:
        checks.append(await _probe("postgresql", container.database.ping))

    index = container.stack.index
    if index is None:
        checks.append(
            {"name": "chromadb", "healthy": False, "detail": "ARGUS_CHROMA_MODE is disabled"}
        )
    else:
        checks.append(await _probe("chromadb", index.ping))

    healthy = all(check["healthy"] for check in checks)
    response.status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@router.get("/models", response_model=ModelsResponse, summary="Vision component wiring")
async def models(container: ContainerDep) -> ModelsResponse:
    # What the recognition stack is actually running, and its thresholds.
    stack = container.stack
    settings = container.settings
    return ModelsResponse(
        components=[ComponentStatusOut.model_validate(s) for s in stack.statuses],
        thresholds=ThresholdsOut(
            match_threshold=settings.match_threshold,
            review_threshold=settings.review_threshold,
            minimum_margin=settings.minimum_margin,
        ),
        recognition_ready=stack.ready,
    )
