"""Time helpers.

``docs/db.md`` declares the timestamp columns as ``TIMESTAMP`` (no time zone), so
the backend stores naive UTC values everywhere and never local time. Every write
path must go through :func:`utc_now` so that comparisons such as
``LEAST(attendance.timestamp, EXCLUDED.timestamp)`` stay meaningful.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time


def utc_now() -> datetime:
    """Current UTC instant as a naive datetime (microsecond precision)."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    """Normalise an incoming datetime to naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def combine(day: date, moment: time) -> datetime:
    """Combine a session ``date`` + ``TIME`` column into a naive UTC datetime."""
    return datetime.combine(day, moment.replace(tzinfo=None))
