"""Plan structures and field parsing for bulk roster registration."""

from __future__ import annotations

import uuid
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.core.errors import InvalidRequestError
from app.schemas.registration import MAX_REPORTED_ERRORS, ImportReport, ImportRowError

REQUIRED_COLUMNS = ("student_name", "roll_no")
KNOWN_COLUMNS = ("student_name", "roll_no", "class_id", "image_filename", "image_url")

#: Matches the limit on app.schemas.student.StudentCreate.
MAX_NAME_LENGTH = 160
_URL = TypeAdapter(HttpUrl)


@dataclass(frozen=True, slots=True)
class PlannedRow:
    #: 1-based line in the CSV; the header is line 1.
    row_number: int
    #: Allocated here, not by the database, so the object key can be derived
    #: before the row exists.
    student_id: uuid.UUID
    student_name: str
    roll_no: int
    class_id: uuid.UUID | None
    #: Already-hosted URL from the CSV; None when `entry` must be uploaded first.
    image_url: str | None
    entry: zipfile.ZipInfo | None


@dataclass(slots=True)
class ImportPlan:
    received_rows: int = 0
    rows: list[PlannedRow] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)
    #: Counted separately from `errors`, which is capped for large files.
    skipped: int = 0

    def reject(self, row_number: int, roll_no: int | None, reason: str) -> None:
        # Record a skipped row, capping the reported detail.
        self.skipped += 1
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append(ImportRowError(row=row_number, roll_no=roll_no, reason=reason))

    def drop(self, matches: Callable[[PlannedRow], bool], reason: str) -> None:
        # Reject every planned row matching `matches` and keep the rest.
        kept: list[PlannedRow] = []
        for row in self.rows:
            if matches(row):
                self.reject(row.row_number, row.roll_no, reason)
            else:
                kept.append(row)
        self.rows = kept

    def remove(self, matches: Callable[[PlannedRow], bool]) -> None:
        # Drop already-reported rows without counting them twice.
        self.rows = [row for row in self.rows if not matches(row)]

    @property
    def needs_upload(self) -> bool:
        # True when at least one row needs an image uploaded first.
        return any(row.image_url is None for row in self.rows)

    def to_report(self, *, created: int, uploaded: int, dry_run: bool) -> ImportReport:
        # Assemble the response from the final state of the plan.
        return ImportReport(
            received_rows=self.received_rows,
            created=created,
            skipped=self.skipped,
            dry_run=dry_run,
            uploaded_images=uploaded,
            errors=sorted(self.errors, key=lambda error: error.row),
            errors_truncated=self.skipped > len(self.errors),
        )


def column_index(header: Sequence[str], *, require_class_id: bool) -> dict[str, int]:
    # Map column name to position; case-insensitive and order-independent.
    index: dict[str, int] = {}
    for position, cell in enumerate(header):
        name = cell.strip().lower()
        if not name:
            continue
        if name in index:
            raise InvalidRequestError(f"The CSV header repeats the '{name}' column.")
        index[name] = position

    missing = [name for name in REQUIRED_COLUMNS if name not in index]
    if require_class_id and "class_id" not in index:
        missing.append("class_id")
    if missing:
        raise InvalidRequestError(
            "The CSV header is missing required columns. Supply class_id as a request field to "
            "make that column optional.",
            details={"missing": missing, "recognised_columns": list(KNOWN_COLUMNS)},
        )
    if not ({"image_filename", "image_url"} & index.keys()):
        raise InvalidRequestError(
            "The CSV needs an image_filename column (entries in the images archive) or an "
            "image_url column (already-hosted https URLs).",
            details={"recognised_columns": list(KNOWN_COLUMNS)},
        )
    return index


def cell(cells: Sequence[str], columns: Mapping[str, int], name: str) -> str:
    # Value of `name` in this row, or "" for an absent or short column.
    position = columns.get(name)
    return cells[position].strip() if position is not None and position < len(cells) else ""


def parse_roll_no(raw: str) -> int | None:
    # roll_no is INTEGER in docs/db.md, so only positive integers are valid.
    try:
        roll_no = int(raw)
    except ValueError:
        return None
    return roll_no if roll_no >= 1 else None


def parse_https_url(raw: str) -> str | None:
    # Only https URLs are accepted as already-hosted images.
    try:
        url = _URL.validate_python(raw)
    except ValidationError:
        return None
    return str(url) if url.scheme == "https" else None
