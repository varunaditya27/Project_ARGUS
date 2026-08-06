"""Wire format for bulk roster registration (POST /students/import)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel

#: A large file with a broken header would otherwise produce one error entry per
#: row. `skipped` still counts every one of them.
MAX_REPORTED_ERRORS = 1_000


class ImportRowError(ApiModel):
    #: 1-based line in the CSV; the header is line 1.
    row: int = Field(ge=1)
    #: Null when the roll number itself could not be parsed.
    roll_no: int | None = None
    reason: str


class ImportReport(ApiModel):
    #: Data rows read from the CSV, excluding the header.
    received_rows: int
    created: int
    skipped: int
    dry_run: bool
    uploaded_images: int
    errors: list[ImportRowError] = Field(default_factory=list)
    #: True when the error list was cut short at MAX_REPORTED_ERRORS.
    errors_truncated: bool = False
