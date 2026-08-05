from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TypeVar

T = TypeVar("T")


def chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Split a sequence into slices of at most ``size`` items."""
    if size < 1:
        raise ValueError("size must be >= 1")
    for start in range(0, len(items), size):
        yield items[start : start + size]
