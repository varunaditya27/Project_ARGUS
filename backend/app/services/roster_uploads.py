"""Enrollment image uploads for the roster import.

students.image_url is NOT NULL, so the object has to exist in R2 before the row
can be written. Archive entries are decompressed one at a time because zipfile
is not thread safe, and the uploads themselves are overlapped because a large
roster is dominated by round trips rather than by CPU.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence

from app.core.archives import SafeZipArchive
from app.core.logging import get_logger
from app.core.utils import chunked
from app.services.roster_plan import ImportPlan, PlannedRow
from app.storage.ports import ObjectStorage, StoredObject, sniff_image_type

logger = get_logger(__name__)

#: Images uploaded concurrently per batch.
_CONCURRENCY = 8

Uploads = dict[uuid.UUID, StoredObject]


async def upload_images(
    plan: ImportPlan, images: SafeZipArchive | None, storage: ObjectStorage | None
) -> Uploads:
    # Upload every archive-backed image and report rows whose entry is not one.
    pending = [row for row in plan.rows if row.image_url is None]
    if not pending:
        return {}
    assert images is not None and storage is not None

    stored: Uploads = {}
    rejected: set[uuid.UUID] = set()
    try:
        for batch in chunked(pending, _CONCURRENCY):
            payloads: list[tuple[PlannedRow, bytes]] = []
            for row in batch:
                assert row.entry is not None
                data = await asyncio.to_thread(images.read, row.entry)
                if sniff_image_type(data) is None:
                    rejected.add(row.student_id)
                    plan.reject(
                        row.row_number,
                        row.roll_no,
                        f"archive entry {row.entry.filename!r} is not a decodable image.",
                    )
                    continue
                payloads.append((row, data))
            uploaded = await asyncio.gather(
                *(
                    storage.put_image(
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
        log_orphans(pending, stored, "the import failed while uploading")
        raise

    if rejected:
        plan.remove(lambda row: row.student_id in rejected)
    return stored


def log_orphans(rows: Sequence[PlannedRow], stored: Mapping[uuid.UUID, StoredObject], why: str):
    # Name any uploaded object left unreferenced so the bucket can be cleaned up.
    keys = [stored[row.student_id].key for row in rows if row.student_id in stored]
    if keys:
        logger.error(
            "Roster import left %d uploaded image(s) unreferenced because %s: %s",
            len(keys),
            why,
            ", ".join(keys),
        )
