from __future__ import annotations

import uuid

from pydantic import Field

from app.schemas.common import ApiModel


class ClassroomCreate(ApiModel):
    class_name: str = Field(min_length=1, max_length=120, examples=["CSE-A"])
    department: str = Field(min_length=1, max_length=120, examples=["Computer Science"])
    semester: int = Field(ge=1, le=12)
    strength: int = Field(ge=0, description="Declared class strength as recorded by the admin.")


class ClassroomRead(ApiModel):
    class_id: uuid.UUID
    class_name: str
    department: str
    semester: int
    strength: int


class ClassroomDetail(ClassroomRead):
    roster_count: int = Field(
        description="Students currently assigned to this classroom. Attendance maths uses this, "
        "not `strength`; a mismatch means the roster import is incomplete."
    )
