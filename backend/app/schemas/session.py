"""Class session wire format."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, model_validator

from app.domain import SessionStatus
from app.schemas.common import ApiModel


class SessionCreate(ApiModel):
    class_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=160)
    faculty: str = Field(min_length=1, max_length=160)
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    status: SessionStatus = SessionStatus.ACTIVE

    @model_validator(mode="after")
    def _check_window(self) -> SessionCreate:
        # docs/db.md declares no CHECK constraint, so the window is validated here.
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class SessionRead(ApiModel):
    session_id: uuid.UUID
    class_id: uuid.UUID
    subject: str
    faculty: str
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    status: SessionStatus


class SessionCloseReport(ApiModel):
    """Result of the close transaction: final flush, absence pass, status flip."""

    session_id: uuid.UUID
    closed_at: dt.datetime
    present: int
    #: Absent rows created by this close.
    absent_marked: int
    roster_count: int
