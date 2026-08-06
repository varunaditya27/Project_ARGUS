"""Translate PostgreSQL constraint violations into domain errors.

Mapping by constraint name instead of a pre-flight SELECT keeps writes to a
single statement and stays correct under concurrency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError, InvalidRequestError


def constraint_name(error: IntegrityError) -> str | None:
    # asyncpg reports the violated constraint on the wrapped driver exception.
    cause = getattr(error, "orig", None)
    for candidate in (cause, getattr(cause, "__cause__", None)):
        name = getattr(candidate, "constraint_name", None)
        if name:
            return str(name)
    return None


@asynccontextmanager
async def integrity_guard(messages: Mapping[str, str]) -> AsyncIterator[None]:
    # Map {constraint_name: message}; unrecognised violations become 422.
    try:
        yield
    except IntegrityError as exc:
        name = constraint_name(exc)
        message = messages.get(name or "")
        if message:
            raise ConflictError(message, details={"constraint": name}) from exc
        raise InvalidRequestError(
            "The request violates a database constraint.", details={"constraint": name}
        ) from exc
