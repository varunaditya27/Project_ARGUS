"""Wire format for bulk roster registration (``POST /students/import``)."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.schemas.common import ApiModel

#: A 20 000 row file with a broken header would otherwise produce a 20 000 entry
#: error list. The report stays useful without becoming a multi-megabyte payload.
MAX_REPORTED_ERRORS = 1_000


class ImportRowError(ApiModel):
    row: int = Field(
        ge=1,
        description="1-based line number in the uploaded CSV; the header is line 1, "
        "so the first data row is line 2.",
    )
    roll_no: int | None = Field(
        default=None, description="Null when the roll number itself could not be parsed."
    )
    reason: str


class ImportedStudent(ApiModel):
    student_id: uuid.UUID
    roll_no: int


class ImportReport(ApiModel):
    received_rows: int = Field(description="Data rows read from the CSV, excluding the header.")
    created: int
    skipped: int
    dry_run: bool
    uploaded_images: int = Field(
        description="Images uploaded to object storage. Always 0 for a dry run, and lower than "
        "`created` when rows carried an already-hosted image_url."
    )
    students: list[ImportedStudent] = Field(
        default_factory=list,
        description="The students that were created. Empty for a dry run, which writes nothing.",
    )
    errors: list[ImportRowError] = Field(
        default_factory=list, description="One entry per skipped row."
    )
    errors_truncated: bool = Field(
        default=False,
        description=f"True when more than {MAX_REPORTED_ERRORS} rows failed and the list was cut "
        "short; `skipped` still counts every one of them.",
    )
