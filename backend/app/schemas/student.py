from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, HttpUrl, field_serializer

from app.schemas.common import ApiModel


class StudentCreate(ApiModel):
    student_name: str = Field(min_length=1, max_length=160)
    #: INTEGER and globally unique, per docs/db.md.
    roll_no: int = Field(ge=1)
    class_id: uuid.UUID | None = None
    #: Cloudflare R2 URL of the original unmasked enrollment image. The upload
    #: itself is done by the client/enrollment tool; the backend stores the URL.
    image_url: HttpUrl

    @field_serializer("image_url")
    def _url_to_str(self, value: HttpUrl) -> str:
        return str(value)


class StudentRead(ApiModel):
    student_id: uuid.UUID
    student_name: str
    roll_no: int
    class_id: uuid.UUID | None
    image_url: str
    created_at: dt.datetime


class StudentTemplates(ApiModel):
    student_id: uuid.UUID
    templates: list[str] = Field(
        description="mask_type values stored for this student in ChromaDB."
    )
