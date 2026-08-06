"""Domain errors and the single place where they become HTTP responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class ArgusError(Exception):
    """Base class for every expected failure the API can return."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        # Details are echoed to the caller, so they must stay free of secrets.
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(ArgusError):
    status_code = 404
    code = "not_found"


class ConflictError(ArgusError):
    status_code = 409
    code = "conflict"


class InvalidRequestError(ArgusError):
    status_code = 422
    code = "invalid_request"


class PayloadTooLargeError(ArgusError):
    status_code = 413
    code = "payload_too_large"


class CapacityExceededError(ArgusError):
    status_code = 503
    code = "capacity_exceeded"


class DependencyNotConfiguredError(ArgusError):
    status_code = 503
    code = "dependency_not_configured"


class DependencyUnavailableError(ArgusError):
    status_code = 503
    code = "dependency_unavailable"


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    # The one error envelope every response and the WebSocket share.
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    # Map every failure class onto the error envelope.
    @app.exception_handler(ArgusError)
    async def _argus(_: Request, exc: ArgusError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "invalid_request", "Request payload failed validation.", {"errors": exc.errors()}
            ),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Unmapped integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content=error_body("conflict", "The request violates a database constraint."),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database failure: %s", exc)
        return JSONResponse(
            status_code=503,
            content=error_body(
                "dependency_unavailable", "PostgreSQL is unavailable or rejected the statement."
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body("http_error", str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )
