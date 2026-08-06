"""Student wire format."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, HttpUrl

from app.schemas.common import ApiModel


class StudentCreate(ApiModel):
    student_name: str = Field(min_length=1, max_length=160)
    #: INTEGER and globally unique, per docs/db.md.
    roll_no: int = Field(ge=1)
    class_id: uuid.UUID | None = None
    #: R2 URL of the unmasked enrollment image. Use POST /students/import to have
    #: the backend upload the image itself.
    image_url: HttpUrl


class StudentRead(ApiModel):
    student_id: uuid.UUID
    student_name: str
    roll_no: int
    class_id: uuid.UUID | None
    image_url: str
    created_at: dt.datetime


class StudentTemplates(ApiModel):
    student_id: uuid.UUID
    #: mask_type values stored for this student in ChromaDB.
    templates: list[str]
