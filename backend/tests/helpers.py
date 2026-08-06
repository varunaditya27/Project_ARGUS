"""Builders, seeds and test doubles shared across the suites."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import uuid
import zipfile
from collections.abc import Mapping, Sequence

from app.container import Container
from app.core.archives import SafeZipArchive
from app.schemas.classroom import ClassroomCreate
from app.schemas.registration import ImportRowError
from app.schemas.session import SessionCreate
from app.schemas.student import StudentCreate
from app.services.roster_import import RosterImportService
from app.storage.ports import ObjectStorage, StoredObject, sniff_image_type

CLASS_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
#: Fixed clock for attendance assertions.
T0 = dt.datetime(2026, 8, 6, 9, 0, 0)
#: Only the magic bytes matter: the import path identifies images without OpenCV.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def build_zip(entries: Mapping[str, bytes]) -> io.BytesIO:
    # An in-memory ZIP holding the given entries.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    buffer.seek(0)
    return buffer


def open_archive(
    entries: Mapping[str, bytes], *, max_total_bytes: int = 1 << 20, max_entry_bytes: int = 1 << 16
) -> SafeZipArchive:
    # The same ZIP, opened through the production guard.
    return SafeZipArchive.open(
        build_zip(entries), max_total_bytes=max_total_bytes, max_entry_bytes=max_entry_bytes
    )


def roster_csv(
    *rows: str, header: str = "student_name,roll_no,image_filename", bom: bool = False
) -> bytes:
    # An upload body for POST /students/import.
    text = "\n".join([header, *rows]) + "\n"
    return ("\ufeff" + text if bom else text).encode()


def reasons(errors: Sequence[ImportRowError]) -> dict[int, str]:
    # Row number to failure reason.
    return {error.row: error.reason for error in errors}


async def seed(container: Container, *, students: int = 3):
    # A classroom, a roster and one ACTIVE session.
    services = container.services
    classroom = await services.classrooms.create(
        ClassroomCreate(class_name="CSE-A", department="CSE", semester=5, strength=students)
    )
    roster = [
        await services.students.create(
            StudentCreate(
                student_name=f"Student {index}",
                roll_no=index,
                class_id=classroom.class_id,
                image_url=f"https://r2.example.com/enrollment/{index}.jpg",
            )
        )
        for index in range(1, students + 1)
    ]
    session = await services.sessions.create(
        SessionCreate(
            class_id=classroom.class_id,
            subject="Computer Vision",
            faculty="Dr. Placeholder",
            date=dt.date(2026, 8, 6),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 0),
        )
    )
    return classroom, roster, session


class RecordingStorage:
    """Stands in for R2: records every upload and returns a deterministic URL."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str | None]] = []

    def describe(self) -> str:
        return "recording"

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        image_type = sniff_image_type(data)
        assert image_type is not None
        self.uploads.append((namespace, filename))
        digest = hashlib.sha256(data).hexdigest()[:32]
        key = f"enrollment/{namespace}/{digest}.{image_type.extension}"
        return StoredObject(key=key, url=f"https://images.example.test/{key}")


class FakeImportService(RosterImportService):
    """Real orchestration with the three PostgreSQL seams answered in memory."""

    def __init__(
        self,
        storage: ObjectStorage | None,
        *,
        enrolled: set[int] | None = None,
        classrooms: set[uuid.UUID] | None = None,
        lost_races: set[int] | None = None,
        max_csv_bytes: int = 1 << 20,
    ) -> None:
        super().__init__(
            None,  # type: ignore[arg-type]
            storage,
            max_csv_bytes=max_csv_bytes,
            max_archive_bytes=1 << 20,
            max_rows=100,
            max_image_bytes=1 << 16,
        )
        self.enrolled = enrolled or set()
        #: None means "every referenced classroom exists".
        self.classrooms = classrooms
        #: Roll numbers a concurrent request wins from under us.
        self.lost_races = lost_races or set()
        self.inserted: list[Mapping[str, object]] = []

    async def _known_class_ids(self, class_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        if self.classrooms is None:
            return set(class_ids)
        return {class_id for class_id in class_ids if class_id in self.classrooms}

    async def _existing_roll_numbers(self, rolls: Sequence[int]) -> set[int]:
        return {roll_no for roll_no in rolls if roll_no in self.enrolled}

    async def _insert(self, payload: Sequence[Mapping[str, object]]) -> set[int]:
        landed = {int(str(row["roll_no"])) for row in payload} - self.lost_races
        self.inserted.extend(row for row in payload if int(str(row["roll_no"])) in landed)
        return landed
