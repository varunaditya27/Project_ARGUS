"""Attendance wire format."""

from __future__ import annotations

import datetime as dt
import uuid

from app.domain import AttendanceStatus, SessionStatus
from app.schemas.common import ApiModel


class AttendanceRecord(ApiModel):
    attendance_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    roll_no: int
    #: First detection that marked the student present, or the close instant for
    #: Absent rows.
    timestamp: dt.datetime
    #: Highest confidence seen during the session; 0.0 for Absent.
    confidence: float
    status: AttendanceStatus


class StudentAttendanceRecord(ApiModel):
    session_id: uuid.UUID
    subject: str
    date: dt.date
    timestamp: dt.datetime
    confidence: float
    status: AttendanceStatus


class AttendanceSummary(ApiModel):
    session_id: uuid.UUID
    session_status: SessionStatus
    #: Students assigned to the classroom right now.
    roster_count: int
    present: int
    absent: int
