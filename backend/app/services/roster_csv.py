"""CSV reading for bulk roster registration.

Every row is validated on its own, without touching PostgreSQL or object
storage, so the caller can report exactly which rows will be skipped and why
before anything is written.
"""

from __future__ import annotations

import csv
import io
import uuid
import zipfile
from collections.abc import Mapping, Sequence

from app.core.archives import SafeZipArchive
from app.core.errors import InvalidRequestError, PayloadTooLargeError
from app.services.roster_plan import (
    MAX_NAME_LENGTH,
    ImportPlan,
    PlannedRow,
    cell,
    column_index,
    parse_https_url,
    parse_roll_no,
)


def plan_import(
    csv_bytes: bytes,
    *,
    archive: SafeZipArchive | None,
    class_id: uuid.UUID | None,
    max_rows: int,
) -> ImportPlan:
    # Parse the file once and validate every row independently.
    try:
        # utf-8-sig also accepts a plain UTF-8 file; the BOM is stripped if present.
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError("The CSV must be UTF-8 encoded.") from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        columns = column_index(next(reader), require_class_id=class_id is None)
    except StopIteration:
        raise InvalidRequestError("The CSV is empty; a header row is required.") from None

    plan = ImportPlan()
    claimed: dict[int, int] = {}
    for row_number, cells in enumerate(reader, start=2):
        if not any(value.strip() for value in cells):
            continue
        plan.received_rows += 1
        if plan.received_rows > max_rows:
            raise PayloadTooLargeError(
                "The CSV contains more rows than this deployment accepts in one import.",
                details={"max_rows": max_rows},
            )
        _plan_row(plan, claimed, cells, columns, row_number, class_id, archive)
    return plan


def _plan_row(
    plan: ImportPlan,
    claimed: dict[int, int],
    cells: Sequence[str],
    columns: Mapping[str, int],
    row_number: int,
    class_id: uuid.UUID | None,
    archive: SafeZipArchive | None,
) -> None:
    # Validate one row and either plan it or reject it with a reason.
    raw_roll = cell(cells, columns, "roll_no")
    roll_no = parse_roll_no(raw_roll)
    if roll_no is None:
        plan.reject(row_number, None, f"roll_no must be an integer >= 1 (got {raw_roll!r}).")
        return

    student_name = cell(cells, columns, "student_name")
    if not student_name or len(student_name) > MAX_NAME_LENGTH:
        plan.reject(row_number, roll_no, f"student_name must be 1-{MAX_NAME_LENGTH} characters.")
        return

    row_class_id = class_id
    if row_class_id is None:
        raw_class_id = cell(cells, columns, "class_id")
        try:
            row_class_id = uuid.UUID(raw_class_id)
        except ValueError:
            plan.reject(row_number, roll_no, f"class_id must be a UUID (got {raw_class_id!r}).")
            return

    raw_url = cell(cells, columns, "image_url")
    image_url = parse_https_url(raw_url) if raw_url else None
    entry = None
    if image_url is None:
        entry = _resolve_image(plan, archive, cells, columns, row_number, roll_no, raw_url)
        if entry is None:
            return

    first_seen = claimed.get(roll_no)
    if first_seen is not None:
        plan.reject(
            row_number, roll_no, f"roll_no {roll_no} was already used on line {first_seen}."
        )
        return
    claimed[roll_no] = row_number
    plan.rows.append(
        PlannedRow(
            row_number=row_number,
            student_id=uuid.uuid4(),
            student_name=student_name,
            roll_no=roll_no,
            class_id=row_class_id,
            image_url=image_url,
            entry=entry,
        )
    )


def _resolve_image(
    plan: ImportPlan,
    archive: SafeZipArchive | None,
    cells: Sequence[str],
    columns: Mapping[str, int],
    row_number: int,
    roll_no: int,
    raw_url: str,
) -> zipfile.ZipInfo | None:
    # Find the archive entry this row refers to, or reject the row.
    filename = cell(cells, columns, "image_filename")
    if not filename:
        plan.reject(
            row_number,
            roll_no,
            f"image_url {raw_url!r} is not a valid https URL."
            if raw_url
            else "the row needs an image_filename present in the archive, or an already-hosted "
            "https image_url.",
        )
        return None
    if archive is None:
        plan.reject(row_number, roll_no, f"image_filename {filename!r} needs an images archive.")
        return None
    entry = archive.resolve(filename)
    if entry is None:
        plan.reject(
            row_number,
            roll_no,
            f"{filename!r} matches more than one archive entry; use the full path inside the ZIP."
            if archive.is_ambiguous(filename)
            else f"the images archive has no entry named {filename!r}.",
        )
    return entry
