from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class KeysetPage(BaseModel, Generic[T]):
    """Cursor page. ``next_cursor`` is the value to pass back as ``after``."""

    items: list[T]
    next_cursor: int | None = Field(
        default=None,
        description="Pass as `after` to fetch the following page; null when exhausted.",
    )


class OffsetPage(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
