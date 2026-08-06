"""Bulk roster registration from a CSV plus an archive of enrollment images.

Shape of POST /students/import: plan the CSV, reject the rows a pre-check can
already refuse, upload the images that are not hosted yet, insert the rest in
chunks. Partial success is the contract - valid rows are committed, invalid rows
are skipped and the report says why.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import BinaryIO

from app.core.archives import SafeZipArchive
from app.core.errors import ArgusError, DependencyNotConfiguredError, PayloadTooLargeError
from app.core.utils import chunked
from app.db.session import Database
from app.repositories.classroom import ClassroomRepository
from app.repositories.student import StudentRepository
from app.schemas.registration import ImportReport
from app.services.roster_csv import plan_import
from app.services.roster_plan import ImportPlan
from app.services.roster_uploads import Uploads, log_orphans, upload_images
from app.storage.ports import ObjectStorage

#: Rows per INSERT statement.
_INSERT_CHUNK = 1_000


class RosterImportService:
    def __init__(
        self,
        database: Database,
        storage: ObjectStorage | None,
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
        # Plan, pre-check in batch, then upload and insert unless this is a dry run.
        if len(csv_bytes) > self._max_csv_bytes:
            raise PayloadTooLargeError(
                "The CSV upload is too large.", details={"max_bytes": self._max_csv_bytes}
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
            # Fail before the first query; a dry run must report this too.
            if plan.needs_upload and self._storage is None:
                raise DependencyNotConfiguredError(
                    "Object storage is not configured, so enrollment images cannot be uploaded.",
                    details={
                        "component": "object_storage",
                        "required": "ARGUS_OBJECT_STORAGE_MODE=r2 and the ARGUS_R2_* settings",
                    },
                )
            await self._reject_unknown_classrooms(plan)
            await self._reject_enrolled_roll_numbers(plan)

            if dry_run:
                return plan.to_report(created=len(plan.rows), uploaded=0, dry_run=True)
            return await self._apply(plan, images)
        finally:
            if images is not None:
                images.close()

    async def _reject_unknown_classrooms(self, plan: ImportPlan) -> None:
        # A roster normally names one classroom, so this is one lookup.
        wanted = {row.class_id for row in plan.rows if row.class_id is not None}
        if not wanted:
            return
        unknown = wanted - await self._known_class_ids(list(wanted))
        if unknown:
            plan.drop(
                lambda row: row.class_id in unknown, "the referenced classroom does not exist."
            )

    async def _reject_enrolled_roll_numbers(self, plan: ImportPlan) -> None:
        # Single batch query; the UNIQUE constraint remains the real arbiter.
        enrolled = await self._existing_roll_numbers([row.roll_no for row in plan.rows])
        if enrolled:
            plan.drop(
                lambda row: row.roll_no in enrolled,
                "a student with this roll number is already enrolled.",
            )

    async def _apply(self, plan: ImportPlan, images: SafeZipArchive | None) -> ImportReport:
        # Upload first, then insert; each chunk runs in its own transaction.
        stored = await upload_images(plan, images, self._storage)
        created = 0
        for chunk in chunked(list(plan.rows), _INSERT_CHUNK):
            try:
                landed = await self._insert(_payload(chunk, stored))
            except ArgusError as exc:
                rolled_back = {row.student_id for row in chunk}
                plan.drop(
                    lambda row, ids=rolled_back: row.student_id in ids,
                    f"the database rejected the batch containing this row: {exc.message}",
                )
                log_orphans(chunk, stored, "their batch was rolled back")
                continue

            created += sum(1 for row in chunk if row.roll_no in landed)
            missed = [row for row in chunk if row.roll_no not in landed]
            if missed:
                missed_ids = {row.student_id for row in missed}
                plan.drop(
                    lambda row, ids=missed_ids: row.student_id in ids,
                    "the roll number was registered by a concurrent request.",
                )
                log_orphans(missed, stored, "their row lost a concurrent insert")
        return plan.to_report(created=created, uploaded=len(stored), dry_run=False)

    async def _known_class_ids(self, class_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        # Which of these classrooms exist.
        async with self._db.session() as session:
            repository = ClassroomRepository(session)
            return {cid for cid in class_ids if await repository.get(cid) is not None}

    async def _existing_roll_numbers(self, rolls: Sequence[int]) -> set[int]:
        # Which of these roll numbers are already taken.
        async with self._db.session() as session:
            return await StudentRepository(session).existing_roll_numbers(rolls)

    async def _insert(self, payload: Sequence[Mapping[str, object]]) -> set[int]:
        # One chunk, one transaction.
        async with self._db.session() as session:
            return await StudentRepository(session).insert_new(payload)


def _payload(chunk: Sequence, stored: Uploads) -> list[dict[str, object]]:
    # Turn planned rows into INSERT values, resolving the uploaded image URL.
    return [
        {
            "student_id": row.student_id,
            "student_name": row.student_name,
            "roll_no": row.roll_no,
            "class_id": row.class_id,
            "image_url": row.image_url or stored[row.student_id].url,
        }
        for row in chunk
    ]
