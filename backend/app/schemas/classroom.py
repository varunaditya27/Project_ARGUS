"""Classroom wire format."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.schemas.common import ApiModel


class ClassroomCreate(ApiModel):
    class_name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)
    semester: int = Field(ge=1, le=12)
    strength: int = Field(ge=0)


class ClassroomRead(ApiModel):
    class_id: uuid.UUID
    class_name: str
    department: str
    semester: int
    strength: int


class ClassroomDetail(ClassroomRead):
    #: Students currently assigned. Attendance maths uses this, not `strength`.
    roster_count: int
