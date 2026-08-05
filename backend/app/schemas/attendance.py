from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field

from app.domain.enums import AttendanceStatus
from app.schemas.common import ApiModel


class AttendanceRecord(ApiModel):
    attendance_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    roll_no: int
    timestamp: dt.datetime = Field(
        description="First detection that marked the student present (UTC), or the session "
        "close instant for Absent rows."
    )
    confidence: float = Field(
        description="Highest recognition confidence observed during the session; 0.0 for Absent."
    )
    status: AttendanceStatus


class StudentAttendanceRecord(ApiModel):
    session_id: uuid.UUID
    subject: str
    faculty: str
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    timestamp: dt.datetime
    confidence: float
    status: AttendanceStatus


class AttendanceSummary(ApiModel):
    session_id: uuid.UUID
    session_status: str
    roster_count: int = Field(description="Students assigned to the classroom right now.")
    declared_strength: int = Field(description="classrooms.strength as entered by the admin.")
    present: int
    absent: int
    #: Non-zero only while the session is ACTIVE: roster members with no row yet.
    unrecorded: int = Field(
        description="Roster members with no attendance row yet. Becomes 0 once the session is "
        "closed, because closing writes Absent for all of them."
    )
    pending_observations: int = Field(
        description="Observations buffered in this worker that are not persisted yet."
    )
