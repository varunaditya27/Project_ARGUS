"""Bulk roster registration from a CSV plus an archive of enrollment images.

Shape of the operation (``POST /students/import``):

1. **Plan.** The CSV is parsed once and every row is validated on its own. The
   ZIP index is checked before anything is decompressed, so a malicious archive is
   rejected without being extracted.
2. **Pre-check.** The referenced classrooms and the already-used roll numbers are
   resolved in batch queries - never one query per row, because the file can hold
   20 000 rows.
3. **Upload.** ``students.image_url`` is NOT NULL (``docs/db.md``), so the image
   has to exist in Cloudflare R2 *before* the row can be written. Rows that came
   with an already-hosted ``image_url`` skip this step entirely.
4. **Insert.** Valid rows are written in chunks, each chunk in its own
   transaction, with ``ON CONFLICT DO NOTHING`` on ``roll_no``.

Partial success is the contract: valid rows are committed, invalid rows are
skipped and the response reports why, per row. A roll number that already exists -
in the database or twice inside the same file - is always an error for that row and
never an update of the enrolled student.

Nothing here fabricates data. If a row needs an upload and object storage is not
configured, the request fails with 503 before any row is written, rather than
inventing a URL.
"""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import BinaryIO

from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.core.archives import SafeZipArchive
from app.core.collections import chunked
from app.core.errors import ArgusError, InvalidRequestError, PayloadTooLargeError
from app.core.logging import get_logger
from app.db.database import Database
from app.repositories.classroom import ClassroomRepository
from app.repositories.student import StudentRepository
from app.schemas.registration import (
    MAX_REPORTED_ERRORS,
    ImportedStudent,
    ImportReport,
    ImportRowError,
)
from app.storage.ports import ObjectStorage, StoredObject, sniff_image_type

logger = get_logger(__name__)

REQUIRED_COLUMNS = ("student_name", "roll_no")
KNOWN_COLUMNS = ("student_name", "roll_no", "class_id", "image_filename", "image_url")

#: Matches the API contract in :class:`app.schemas.student.StudentCreate`.
_MAX_NAME_LENGTH = 160
#: Rows per INSERT statement, and images uploaded concurrently per batch.
_INSERT_CHUNK_SIZE = 1_000
_UPLOAD_CONCURRENCY = 8

_URL_ADAPTER = TypeAdapter(HttpUrl)


# ------------------------------------------------------------------------ plan
@dataclass(frozen=True, slots=True)
class PlannedRow:
    #: 1-based line number in the uploaded CSV (the header is line 1).
    row_number: int
    #: Allocated here rather than by the database so the object key can be derived
    #: from it before the row exists.
    student_id: uuid.UUID
    student_name: str
    roll_no: int
    class_id: uuid.UUID | None
    #: Already-hosted URL taken from the CSV; ``None`` when ``entry`` must be
    #: uploaded first.
    image_url: str | None
    entry: zipfile.ZipInfo | None


@dataclass(slots=True)
class ImportPlan:
    received_rows: int = 0
    rows: list[PlannedRow] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)
    #: Counted separately from ``errors``, which is capped for large files.
    skipped: int = 0

    def reject(self, row_number: int, roll_no: int | None, reason: str) -> None:
        self.skipped += 1
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append(ImportRowError(row=row_number, roll_no=roll_no, reason=reason))

    def drop(self, matches: Callable[[PlannedRow], bool], reason: str) -> None:
        """Reject every planned row matching ``matches`` and keep the rest."""
        kept: list[PlannedRow] = []
        for row in self.rows:
            if matches(row):
                self.reject(row.row_number, row.roll_no, reason)
            else:
                kept.append(row)
        self.rows = kept

    def remove(self, matches: Callable[[PlannedRow], bool]) -> None:
        """Drop already-reported rows without counting them a second time."""
        self.rows = [row for row in self.rows if not matches(row)]

    @property
    def errors_truncated(self) -> bool:
        return self.skipped > len(self.errors)

    @property
    def needs_upload(self) -> bool:
        return any(row.image_url is None for row in self.rows)


def _column_index(header: Sequence[str], *, require_class_id: bool) -> dict[str, int]:
    """Map column name to position. Case-insensitive and order-independent."""
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


def _cell(cells: Sequence[str], columns: Mapping[str, int], name: str) -> str:
    """Value of ``name`` in this row, or ``""`` for an absent or short column."""
    position = columns.get(name)
    return cells[position].strip() if position is not None and position < len(cells) else ""


def _parse_roll_no(raw: str) -> int | None:
    """``students.roll_no`` is INTEGER in docs/db.md, so only integers are valid."""
    try:
        roll_no = int(raw)
    except ValueError:
        return None
    return roll_no if roll_no >= 1 else None


def _parse_https_url(raw: str) -> str | None:
    try:
        url = _URL_ADAPTER.validate_python(raw)
    except ValidationError:
        return None
    return str(url) if url.scheme == "https" else None


def plan_import(
    csv_bytes: bytes,
    *,
    archive: SafeZipArchive | None,
    class_id: uuid.UUID | None,
    max_rows: int,
) -> ImportPlan:
    """Validate every CSV row without touching the database or object storage."""
    try:
        # utf-8-sig also accepts a plain UTF-8 file: the BOM is stripped when present.
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError(
            "The CSV must be UTF-8 encoded.", details={"decode_error": str(exc)}
        ) from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise InvalidRequestError("The CSV is empty; a header row is required.") from None
    columns = _column_index(header, require_class_id=class_id is None)

    plan = ImportPlan()
    claimed: dict[int, int] = {}
    for row_number, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        plan.received_rows += 1
        if plan.received_rows > max_rows:
            raise PayloadTooLargeError(
                "The CSV contains more rows than this deployment accepts in one import.",
                details={"max_rows": max_rows},
            )

        raw_roll_no = _cell(cells, columns, "roll_no")
        roll_no = _parse_roll_no(raw_roll_no)
        if roll_no is None:
            plan.reject(
                row_number,
                None,
                f"roll_no must be an integer >= 1 (got {raw_roll_no!r}).",
            )
            continue

        student_name = _cell(cells, columns, "student_name")
        if not student_name or len(student_name) > _MAX_NAME_LENGTH:
            plan.reject(
                row_number,
                roll_no,
                f"student_name must be 1-{_MAX_NAME_LENGTH} characters.",
            )
            continue

        row_class_id = class_id
        if row_class_id is None:
            raw_class_id = _cell(cells, columns, "class_id")
            try:
                row_class_id = uuid.UUID(raw_class_id)
            except ValueError:
                plan.reject(row_number, roll_no, f"class_id must be a UUID (got {raw_class_id!r}).")
                continue

        raw_url = _cell(cells, columns, "image_url")
        image_url = _parse_https_url(raw_url) if raw_url else None
        entry: zipfile.ZipInfo | None = None
        if image_url is None:
            filename = _cell(cells, columns, "image_filename")
            if not filename:
                plan.reject(
                    row_number,
                    roll_no,
                    f"image_url {raw_url!r} is not a valid https URL."
                    if raw_url
                    else "the row needs an image_filename present in the archive, or an "
                    "already-hosted https image_url.",
                )
                continue
            if archive is None:
                plan.reject(
                    row_number,
                    roll_no,
                    f"image_filename {filename!r} needs an images archive, but none was uploaded.",
                )
                continue
            entry = archive.resolve(filename)
            if entry is None:
                plan.reject(
                    row_number,
                    roll_no,
                    f"{filename!r} matches more than one archive entry; use the full path "
                    "inside the ZIP."
                    if archive.is_ambiguous(filename)
                    else f"the images archive has no entry named {filename!r}.",
                )
                continue

        first_seen = claimed.get(roll_no)
        if first_seen is not None:
            plan.reject(
                row_number, roll_no, f"roll_no {roll_no} was already used on line {first_seen}."
            )
            continue
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
    return plan


# --------------------------------------------------------------------- service
class RegistrationImportService:
    def __init__(
        self,
        database: Database,
        storage: ObjectStorage,
        *,
        max_csv_bytes: int,
        max_archive_bytes: int,
        max_rows: int,
        max_image_bytes: int,
    ) -> None:
        self._db = database
        self._storage = storage
        self._max_csv_bytes = max_csv_bytes
        self._max_archive_bytes = max_archive_bytes
        self._max_rows = max_rows
        self._max_image_bytes = max_image_bytes

    async def import_students(
        self,
        *,
        csv_bytes: bytes,
        archive: BinaryIO | None,
        class_id: uuid.UUID | None,
        dry_run: bool,
    ) -> ImportReport:
        if len(csv_bytes) > self._max_csv_bytes:
            raise PayloadTooLargeError(
                "The CSV upload is too large.",
                details={"max_bytes": self._max_csv_bytes, "received_bytes": len(csv_bytes)},
            )

        images: SafeZipArchive | None = None
        try:
            if archive is not None:
                images = SafeZipArchive.open(
                    archive,
                    max_total_bytes=self._max_archive_bytes,
                    max_entry_bytes=self._max_image_bytes,
                )
            plan = plan_import(
                csv_bytes, archive=images, class_id=class_id, max_rows=self._max_rows
            )
            # Fail before the first query and the first upload: a request that needs
            # R2 while R2 is unconfigured can never be completed, and a dry run must
            # report that instead of pretending the real run would succeed.
            if plan.needs_upload:
                self._storage.ensure_configured()

            await self._reject_unknown_classrooms(plan)
            await self._reject_enrolled_roll_numbers(plan)

            if dry_run:
                return self._report(plan, created=[], uploaded=0, dry_run=True)
            return await self._apply(plan, images)
        finally:
            if images is not None:
                images.close()

    # ----------------------------------------------------------------- batches
    async def _reject_unknown_classrooms(self, plan: ImportPlan) -> None:
        """One lookup per distinct classroom - normally exactly one for a roster."""
        wanted = {row.class_id for row in plan.rows if row.class_id is not None}
        if not wanted:
            return
        known = await self._known_class_ids(sorted(wanted))
        unknown = wanted - known
        if unknown:
            plan.drop(
                lambda row: row.class_id in unknown, "the referenced classroom does not exist."
            )

    async def _reject_enrolled_roll_numbers(self, plan: ImportPlan) -> None:
        """Single batch query. The UNIQUE constraint remains the real arbiter."""
        if not plan.rows:
            return
        enrolled = await self._existing_roll_numbers([row.roll_no for row in plan.rows])
        if enrolled:
            plan.drop(
                lambda row: row.roll_no in enrolled,
                "a student with this roll number is already enrolled.",
            )

    # ------------------------------------------------------------------- apply
    async def _apply(self, plan: ImportPlan, images: SafeZipArchive | None) -> ImportReport:
        # Uploads first: image_url is NOT NULL, so the object has to exist before
        # the row can. Rows whose image could not be uploaded are already reported
        # and removed from the plan by then.
        stored = await self._upload_images(plan, images)

        created: list[ImportedStudent] = []
        # Snapshot: the loop reports rejections back into the plan as it goes.
        for chunk in chunked(list(plan.rows), _INSERT_CHUNK_SIZE):
            payload = [
                {
                    "student_id": row.student_id,
                    "student_name": row.student_name,
                    "roll_no": row.roll_no,
                    "class_id": row.class_id,
                    "image_url": row.image_url or stored[row.student_id].url,
                }
                for row in chunk
            ]
            try:
                landed = await self._insert(payload)
            except ArgusError as exc:
                # The chunk ran in its own transaction, so it rolled back whole.
                rolled_back = {row.student_id for row in chunk}
                plan.drop(
                    lambda row, ids=rolled_back: row.student_id in ids,
                    f"the database rejected the batch containing this row: {exc.message}",
                )
                self._log_orphans(chunk, stored, "their batch was rolled back")
                continue

            created.extend(
                ImportedStudent(student_id=row.student_id, roll_no=row.roll_no)
                for row in chunk
                if row.roll_no in landed
            )
            missed = [row for row in chunk if row.roll_no not in landed]
            if missed:
                missed_ids = {row.student_id for row in missed}
                plan.drop(
                    lambda row, ids=missed_ids: row.student_id in ids,
                    "the roll number was registered by a concurrent request while this import "
                    "was running.",
                )
                self._log_orphans(missed, stored, "their row lost a concurrent insert")

        return self._report(plan, created=created, uploaded=len(stored), dry_run=False)

    async def _upload_images(
        self, plan: ImportPlan, images: SafeZipArchive | None
    ) -> dict[uuid.UUID, StoredObject]:
        """Upload every archive-backed image, in small concurrent batches.

        Entries are decompressed one at a time (``zipfile`` is not thread safe) and
        the network calls are overlapped, because a 20 000 image roster is dominated
        by round trips rather than by CPU.
        """
        pending = [row for row in plan.rows if row.image_url is None]
        if not pending:
            return {}
        assert images is not None  # a row without image_url always carries an entry

        stored: dict[uuid.UUID, StoredObject] = {}
        rejected: set[uuid.UUID] = set()
        try:
            for batch in chunked(pending, _UPLOAD_CONCURRENCY):
                payloads: list[tuple[PlannedRow, bytes]] = []
                for row in batch:
                    assert row.entry is not None
                    data = await asyncio.to_thread(images.read, row.entry)
                    if sniff_image_type(data) is None:
                        rejected.add(row.student_id)
                        plan.reject(
                            row.row_number,
                            row.roll_no,
                            f"archive entry {row.entry.filename!r} is not a decodable image "
                            "(JPEG, PNG, WEBP, GIF or BMP).",
                        )
                        continue
                    payloads.append((row, data))
                uploaded = await asyncio.gather(
                    *(
                        self._storage.put_image(
                            data,
                            namespace=str(row.student_id),
                            filename=row.entry.filename if row.entry else None,
                        )
                        for row, data in payloads
                    )
                )
                stored.update(
                    {row.student_id: obj for (row, _), obj in zip(payloads, uploaded, strict=True)}
                )
        except Exception:
            self._log_orphans(pending, stored, "the import failed while uploading")
            raise

        if rejected:
            plan.remove(lambda row: row.student_id in rejected)
        return stored

    # ---------------------------------------------------------------- database
    # The three methods below are the only points that touch PostgreSQL, which
    # keeps the import unit-testable without a live database.
    async def _known_class_ids(self, class_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        async with self._db.session() as session:
            repository = ClassroomRepository(session)
            return {
                class_id for class_id in class_ids if await repository.get(class_id) is not None
            }

    async def _existing_roll_numbers(self, rolls: Sequence[int]) -> set[int]:
        async with self._db.session() as session:
            return await StudentRepository(session).existing_roll_numbers(rolls)

    async def _insert(self, payload: Sequence[Mapping[str, object]]) -> set[int]:
        async with self._db.session() as session:
            return await StudentRepository(session).insert_new(payload)

    # ----------------------------------------------------------------- reporting
    def _log_orphans(
        self, rows: Sequence[PlannedRow], stored: Mapping[uuid.UUID, StoredObject], reason: str
    ) -> None:
        keys = [stored[row.student_id].key for row in rows if row.student_id in stored]
        if keys:
            logger.error(
                "Registration import left %d uploaded image(s) in object storage unreferenced "
                "because %s: %s",
                len(keys),
                reason,
                ", ".join(keys),
            )

    @staticmethod
    def _report(
        plan: ImportPlan, *, created: Sequence[ImportedStudent], uploaded: int, dry_run: bool
    ) -> ImportReport:
        return ImportReport(
            received_rows=plan.received_rows,
            created=len(plan.rows) if dry_run else len(created),
            skipped=plan.skipped,
            dry_run=dry_run,
            uploaded_images=uploaded,
            students=list(created),
            errors=sorted(plan.errors, key=lambda error: error.row),
            errors_truncated=plan.errors_truncated,
        )
