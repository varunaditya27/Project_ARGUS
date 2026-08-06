"""Bulk roster import: CSV parsing, archive safety, and the write path.

No PostgreSQL, no network and no boto3: the CSV/ZIP planning is pure, object
storage is a recording adapter that satisfies
:class:`app.storage.ports.ObjectStorage`, and the service's three database seams
are replaced in :class:`FakeImportService`.
"""

from __future__ import annotations

import hashlib
import io
import uuid
import zipfile
from collections.abc import Mapping, Sequence

import pytest
from httpx import AsyncClient

from app.core.archives import SafeZipArchive
from app.core.errors import (
    DependencyNotConfiguredError,
    InvalidRequestError,
    PayloadTooLargeError,
)
from app.schemas.registration import ImportRowError
from app.services.registration_import import (
    RegistrationImportService,
    plan_import,
)
from app.storage.disabled import UnconfiguredObjectStorage
from app.storage.ports import ObjectStorage, StorageStatus, StoredObject, sniff_image_type

CLASS_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
#: Only the magic bytes matter: the import path identifies images without OpenCV.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


# ------------------------------------------------------------------- fixtures
def build_zip(entries: Mapping[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    buffer.seek(0)
    return buffer


def open_archive(
    entries: Mapping[str, bytes], *, max_total_bytes: int = 1 << 20, max_entry_bytes: int = 1 << 16
) -> SafeZipArchive:
    return SafeZipArchive.open(
        build_zip(entries), max_total_bytes=max_total_bytes, max_entry_bytes=max_entry_bytes
    )


def roster_csv(
    *rows: str, header: str = "student_name,roll_no,image_filename", bom: bool = False
) -> bytes:
    text = "\n".join([header, *rows]) + "\n"
    return ("\ufeff" + text if bom else text).encode()


class RecordingStorage:
    """Stands in for R2: records every upload and returns a deterministic URL."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str | None, int]] = []

    def status(self) -> StorageStatus:
        return StorageStatus(
            name="object_storage", configured=True, adapter="recording", detail="in-memory"
        )

    def ensure_configured(self) -> None:
        return None

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        image_type = sniff_image_type(data)
        assert image_type is not None
        self.uploads.append((namespace, filename, len(data)))
        digest = hashlib.sha256(data).hexdigest()[:32]
        key = f"enrollment/{namespace}/{digest}.{image_type.extension}"
        return StoredObject(
            key=key,
            url=f"https://images.example.test/{key}",
            media_type=image_type.media_type,
            size_bytes=len(data),
        )


class FakeImportService(RegistrationImportService):
    """Real orchestration with the three PostgreSQL seams answered in memory."""

    def __init__(
        self,
        storage: ObjectStorage,
        *,
        enrolled: set[int] | None = None,
        classrooms: set[uuid.UUID] | None = None,
        lost_races: set[int] | None = None,
        max_rows: int = 100,
        max_csv_bytes: int = 1 << 20,
    ) -> None:
        super().__init__(
            None,  # type: ignore[arg-type]
            storage,
            max_csv_bytes=max_csv_bytes,
            max_archive_bytes=1 << 20,
            max_rows=max_rows,
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


def reasons(errors: Sequence[ImportRowError]) -> dict[int, str]:
    return {error.row: error.reason for error in errors}


# ---------------------------------------------------------------- CSV parsing
def test_header_is_case_insensitive_order_independent_and_bom_tolerant() -> None:
    csv_bytes = roster_csv(
        "1.png,7,Ada Lovelace",
        header="Image_Filename, ROLL_NO ,Student_Name",
        bom=True,
    )
    plan = plan_import(
        csv_bytes,
        archive=open_archive({"1.png": PNG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert plan.errors == []
    assert [(row.roll_no, row.student_name) for row in plan.rows] == [(7, "Ada Lovelace")]
    assert plan.rows[0].class_id == CLASS_ID


def test_missing_columns_are_a_request_error() -> None:
    with pytest.raises(InvalidRequestError) as excinfo:
        plan_import(
            roster_csv("Ada,1,1.png", header="student_name,roll_no,image_filename"),
            archive=None,
            class_id=None,
            max_rows=10,
        )
    assert excinfo.value.details["missing"] == ["class_id"]


def test_class_id_column_carries_the_classroom_when_no_request_field_is_given() -> None:
    plan = plan_import(
        roster_csv(
            f"Ada,1,{CLASS_ID},https://cdn.example.test/ada.jpg",
            "Grace,2,not-a-uuid,https://cdn.example.test/grace.jpg",
            header="student_name,roll_no,class_id,image_url",
        ),
        archive=None,
        class_id=None,
        max_rows=10,
    )
    assert [row.class_id for row in plan.rows] == [CLASS_ID]
    assert "class_id must be a UUID" in reasons(plan.errors)[3]


def test_invalid_roll_numbers_are_reported_without_a_roll_number() -> None:
    plan = plan_import(
        roster_csv(
            "Ada,,1.png",
            "Grace,CS2024001,1.png",
            "Alan,0,1.png",
            "Edsger,4,1.png",
        ),
        archive=open_archive({"1.png": PNG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert plan.received_rows == 4
    assert [row.roll_no for row in plan.rows] == [4]
    assert [error.row for error in plan.errors] == [2, 3, 4]
    assert all(error.roll_no is None for error in plan.errors)
    assert "integer >= 1" in plan.errors[0].reason


def test_missing_student_name_is_reported_with_the_roll_number() -> None:
    plan = plan_import(
        roster_csv(" ,9,1.png"),
        archive=open_archive({"1.png": PNG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert plan.rows == []
    assert plan.errors[0].roll_no == 9
    assert "student_name" in plan.errors[0].reason


def test_duplicate_roll_number_inside_the_file_skips_the_second_row() -> None:
    plan = plan_import(
        roster_csv("Ada,5,1.png", "Grace,5,2.png"),
        archive=open_archive({"1.png": PNG, "2.png": JPEG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert [row.student_name for row in plan.rows] == ["Ada"]
    assert reasons(plan.errors) == {3: "roll_no 5 was already used on line 2."}


def test_more_rows_than_allowed_rejects_the_request() -> None:
    rows = [f"Student {index},{index},{index}.png" for index in range(1, 6)]
    with pytest.raises(PayloadTooLargeError) as excinfo:
        plan_import(
            roster_csv(*rows),
            archive=open_archive({f"{index}.png": PNG for index in range(1, 6)}),
            class_id=CLASS_ID,
            max_rows=3,
        )
    assert excinfo.value.details["max_rows"] == 3


# -------------------------------------------------------------------- archive
def test_missing_archive_entry_is_a_row_error() -> None:
    plan = plan_import(
        roster_csv("Ada,1,ada.png", "Grace,2,grace.png"),
        archive=open_archive({"ada.png": PNG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert [row.roll_no for row in plan.rows] == [1]
    assert "has no entry named 'grace.png'" in reasons(plan.errors)[3]


def test_archive_entries_resolve_by_bare_name_inside_a_folder() -> None:
    plan = plan_import(
        roster_csv("Ada,1,ada.png", "Grace,2,photos/grace.png"),
        archive=open_archive({"photos/ada.png": PNG, "photos/grace.png": JPEG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert plan.errors == []
    assert [row.entry.filename for row in plan.rows if row.entry] == [
        "photos/ada.png",
        "photos/grace.png",
    ]


def test_image_filename_without_an_archive_is_a_row_error() -> None:
    plan = plan_import(roster_csv("Ada,1,ada.png"), archive=None, class_id=CLASS_ID, max_rows=10)
    assert plan.rows == []
    assert "needs an images archive" in reasons(plan.errors)[2]


def test_zip_slip_entries_reject_the_archive() -> None:
    with pytest.raises(InvalidRequestError) as excinfo:
        open_archive({"ok.png": PNG, "../../etc/passwd.png": PNG})
    assert "../../etc/passwd.png" in excinfo.value.details["entries"]


def test_oversize_archive_upload_is_rejected() -> None:
    with pytest.raises(PayloadTooLargeError):
        open_archive({"ada.png": PNG}, max_total_bytes=8)


def test_archive_declaring_too_much_uncompressed_data_is_rejected() -> None:
    # Compresses to a few hundred bytes, so only the declared size catches it.
    bomb = PNG + b"\x00" * 500_000
    with pytest.raises(PayloadTooLargeError) as excinfo:
        open_archive({"bomb.png": bomb}, max_total_bytes=100_000, max_entry_bytes=1 << 20)
    assert excinfo.value.details["declared_bytes"] == len(bomb)


def test_entry_larger_than_one_enrollment_image_is_rejected() -> None:
    with pytest.raises(PayloadTooLargeError) as excinfo:
        open_archive({"big.png": PNG + b"\x00" * 5_000}, max_entry_bytes=1_000)
    assert excinfo.value.details["entries"] == ["big.png"]


# --------------------------------------------------------------- image_url path
def test_image_url_rows_need_no_archive_and_no_upload() -> None:
    plan = plan_import(
        roster_csv(
            "Ada,1,https://cdn.example.test/ada.jpg",
            "Grace,2,http://cdn.example.test/grace.jpg",
            "Alan,3,not-a-url",
            header="student_name,roll_no,image_url",
        ),
        archive=None,
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert [row.image_url for row in plan.rows] == ["https://cdn.example.test/ada.jpg"]
    assert plan.needs_upload is False
    assert "is not a valid https URL" in reasons(plan.errors)[3]
    assert "is not a valid https URL" in reasons(plan.errors)[4]


async def test_image_url_is_stored_verbatim() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage)
    report = await service.import_students(
        csv_bytes=roster_csv(
            "Ada,1,https://cdn.example.test/ada.jpg", header="student_name,roll_no,image_url"
        ),
        archive=None,
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.created, report.uploaded_images, report.skipped) == (1, 0, 0)
    assert storage.uploads == []
    assert service.inserted[0]["image_url"] == "https://cdn.example.test/ada.jpg"


# ------------------------------------------------------------------ write path
async def test_archive_images_are_uploaded_before_the_rows_are_written() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage)
    report = await service.import_students(
        csv_bytes=roster_csv(
            "Ada,1,ada.png,",
            "Grace,2,grace.jpg,",
            "Alan,3,,https://cdn.example.test/alan.jpg",
            header="student_name,roll_no,image_filename,image_url",
        ),
        archive=build_zip({"ada.png": PNG, "grace.jpg": JPEG}),
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.received_rows, report.created, report.skipped) == (3, 3, 0)
    assert report.uploaded_images == 2
    assert {student.roll_no for student in report.students} == {1, 2, 3}
    assert [filename for _, filename, _ in storage.uploads] == ["ada.png", "grace.jpg"]
    # Every row landed with a real URL and the classroom from the request field.
    assert len(service.inserted) == 3
    assert all(str(row["image_url"]).startswith("https://") for row in service.inserted)
    assert {row["class_id"] for row in service.inserted} == {CLASS_ID}
    # The object key is namespaced by the student UUID the row was inserted with.
    namespaces = {namespace for namespace, _, _ in storage.uploads}
    assert namespaces <= {str(row["student_id"]) for row in service.inserted}


async def test_archive_entry_that_is_not_an_image_is_skipped() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage)
    report = await service.import_students(
        csv_bytes=roster_csv("Ada,1,ada.png", "Grace,2,notes.txt"),
        archive=build_zip({"ada.png": PNG, "notes.txt": b"just text, not a picture"}),
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.created, report.skipped, report.uploaded_images) == (1, 1, 1)
    assert "not a decodable image" in reasons(report.errors)[3]
    assert [row["roll_no"] for row in service.inserted] == [1]


async def test_enrolled_roll_numbers_are_skipped_never_updated() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage, enrolled={2})
    report = await service.import_students(
        csv_bytes=roster_csv("Ada,1,ada.png", "Grace,2,grace.jpg"),
        archive=build_zip({"ada.png": PNG, "grace.jpg": JPEG}),
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.created, report.skipped) == (1, 1)
    assert reasons(report.errors) == {3: "a student with this roll number is already enrolled."}
    assert [row["roll_no"] for row in service.inserted] == [1]
    # The pre-check runs before the upload, so no image was pushed for row 3.
    assert [filename for _, filename, _ in storage.uploads] == ["ada.png"]


async def test_losing_a_concurrent_insert_is_a_row_error_not_a_failure() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage, lost_races={2})
    report = await service.import_students(
        csv_bytes=roster_csv("Ada,1,ada.png", "Grace,2,grace.jpg"),
        archive=build_zip({"ada.png": PNG, "grace.jpg": JPEG}),
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.created, report.skipped) == (1, 1)
    assert "concurrent request" in reasons(report.errors)[3]
    assert [student.roll_no for student in report.students] == [1]


async def test_rows_pointing_at_an_unknown_classroom_are_skipped() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage, classrooms=set())
    report = await service.import_students(
        csv_bytes=roster_csv("Ada,1,ada.png"),
        archive=build_zip({"ada.png": PNG}),
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.created, report.skipped) == (0, 1)
    assert reasons(report.errors) == {2: "the referenced classroom does not exist."}
    assert service.inserted == []
    assert storage.uploads == []


async def test_dry_run_validates_without_writing_or_uploading() -> None:
    storage = RecordingStorage()
    service = FakeImportService(storage, enrolled={2})
    report = await service.import_students(
        csv_bytes=roster_csv("Ada,1,ada.png", "Grace,2,grace.jpg", "Alan,3,missing.png"),
        archive=build_zip({"ada.png": PNG, "grace.jpg": JPEG}),
        class_id=CLASS_ID,
        dry_run=True,
    )
    assert report.dry_run is True
    assert (report.received_rows, report.created, report.skipped) == (3, 1, 2)
    assert report.uploaded_images == 0
    assert report.students == []
    assert storage.uploads == []
    assert service.inserted == []


async def test_oversize_csv_is_rejected_before_parsing() -> None:
    service = FakeImportService(RecordingStorage(), max_csv_bytes=32)
    with pytest.raises(PayloadTooLargeError) as excinfo:
        await service.import_students(
            csv_bytes=roster_csv(*[f"Student {i},{i},{i}.png" for i in range(1, 20)]),
            archive=None,
            class_id=CLASS_ID,
            dry_run=False,
        )
    assert excinfo.value.details["max_bytes"] == 32


# --------------------------------------------------------------- object storage
def test_both_adapters_satisfy_the_port() -> None:
    assert isinstance(UnconfiguredObjectStorage(), ObjectStorage)
    assert isinstance(RecordingStorage(), ObjectStorage)


async def test_unconfigured_storage_fails_the_import_with_the_env_vars() -> None:
    service = FakeImportService(UnconfiguredObjectStorage())
    with pytest.raises(DependencyNotConfiguredError) as excinfo:
        await service.import_students(
            csv_bytes=roster_csv("Ada,1,ada.png"),
            archive=build_zip({"ada.png": PNG}),
            class_id=CLASS_ID,
            dry_run=False,
        )
    required = excinfo.value.details["required_env"]
    assert "ARGUS_R2_BUCKET" in required
    assert "ARGUS_R2_PUBLIC_BASE_URL" in required


async def test_unconfigured_storage_also_fails_a_dry_run() -> None:
    service = FakeImportService(UnconfiguredObjectStorage())
    with pytest.raises(DependencyNotConfiguredError):
        await service.import_students(
            csv_bytes=roster_csv("Ada,1,ada.png"),
            archive=build_zip({"ada.png": PNG}),
            class_id=CLASS_ID,
            dry_run=True,
        )


# ------------------------------------------------------------------- endpoint
async def test_endpoint_returns_503_when_object_storage_is_disabled(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.post(
        "/api/v1/students/import",
        files={
            "csv_file": ("roster.csv", roster_csv("Ada,1,ada.png"), "text/csv"),
            "images": ("images.zip", build_zip({"ada.png": PNG}).getvalue(), "application/zip"),
        },
        data={"class_id": str(CLASS_ID)},
    )
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "dependency_not_configured"
    assert "ARGUS_R2_ENDPOINT_URL" in error["details"]["required_env"]


async def test_endpoint_reports_a_missing_header_with_the_shared_envelope(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.post(
        "/api/v1/students/import",
        files={"csv_file": ("roster.csv", roster_csv("Ada,1,ada.png"), "text/csv")},
        params={"dry_run": "true"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"]["missing"] == ["class_id"]
