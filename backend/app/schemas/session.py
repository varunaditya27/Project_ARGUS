from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, model_validator

from app.domain.enums import SessionStatus
from app.schemas.common import ApiModel


class SessionCreate(ApiModel):
    class_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=160)
    faculty: str = Field(min_length=1, max_length=160)
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    status: SessionStatus = Field(
        default=SessionStatus.ACTIVE,
        description="A session must be ACTIVE for attendance to be captured. "
        "At most one ACTIVE session per classroom is allowed.",
    )

    @model_validator(mode="after")
    def _check_window(self) -> SessionCreate:
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
    """Result of the close transaction: last flush + absence pass + status flip."""

    session_id: uuid.UUID
    closed_at: dt.datetime
    flushed_observations: int = Field(
        description="Observations still buffered at close time that were written before closing."
    )
    present: int
    absent_marked: int = Field(description="Absent rows created by this close.")
    roster_count: int
    total_recorded: int
