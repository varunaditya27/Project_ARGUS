"""Write path of the bulk roster import.

Object storage is a recording adapter satisfying :class:`ObjectStorage`, and the
service's three PostgreSQL seams are answered in memory, so the real
orchestration runs without a database or a network.
"""

from __future__ import annotations

import pytest

from app.core.errors import DependencyNotConfiguredError, PayloadTooLargeError
from tests.helpers import (
    CLASS_ID,
    JPEG,
    PNG,
    FakeImportService,
    RecordingStorage,
    build_zip,
    reasons,
    roster_csv,
)


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
    assert [filename for _, filename in storage.uploads] == ["ada.png", "grace.jpg"]
    assert all(str(row["image_url"]).startswith("https://") for row in service.inserted)
    assert {row["class_id"] for row in service.inserted} == {CLASS_ID}
    # The object key is namespaced by the student UUID the row was inserted with.
    assert {namespace for namespace, _ in storage.uploads} <= {
        str(row["student_id"]) for row in service.inserted
    }


async def test_archive_entry_that_is_not_an_image_is_skipped() -> None:
    service = FakeImportService(RecordingStorage())
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
    # The pre-check runs before the upload, so no image was pushed for row 3.
    assert [filename for _, filename in storage.uploads] == ["ada.png"]


async def test_losing_a_concurrent_insert_is_a_row_error_not_a_failure() -> None:
    service = FakeImportService(RecordingStorage(), lost_races={2})
    report = await service.import_students(
        csv_bytes=roster_csv("Ada,1,ada.png", "Grace,2,grace.jpg"),
        archive=build_zip({"ada.png": PNG, "grace.jpg": JPEG}),
        class_id=CLASS_ID,
        dry_run=False,
    )
    assert (report.created, report.skipped) == (1, 1)
    assert "concurrent request" in reasons(report.errors)[3]


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
    assert (report.uploaded_images, storage.uploads, service.inserted) == (0, [], [])


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


@pytest.mark.parametrize("dry_run", [False, True])
async def test_missing_object_storage_fails_the_import(dry_run: bool) -> None:
    service = FakeImportService(None)
    with pytest.raises(DependencyNotConfiguredError) as excinfo:
        await service.import_students(
            csv_bytes=roster_csv("Ada,1,ada.png"),
            archive=build_zip({"ada.png": PNG}),
            class_id=CLASS_ID,
            dry_run=dry_run,
        )
    assert "ARGUS_OBJECT_STORAGE_MODE" in excinfo.value.details["required"]
