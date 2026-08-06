"""Time and sequence helpers.

docs/db.md declares the timestamp columns as TIMESTAMP without a time zone, so
every write path stores naive UTC.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import TypeVar

T = TypeVar("T")


def utc_now() -> datetime:
    # Current UTC instant as a naive datetime.
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    # Normalise a client-supplied datetime to naive UTC.
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    # Split a sequence into slices of at most `size` items.
    if size < 1:
        raise ValueError("size must be >= 1")
    for start in range(0, len(items), size):
        yield items[start : start + size]
