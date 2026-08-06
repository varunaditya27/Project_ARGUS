"""CSV parsing and archive safety for the bulk roster import.

Pure planning: no PostgreSQL, no network, no object storage.
"""

from __future__ import annotations

import pytest

from app.core.errors import InvalidRequestError, PayloadTooLargeError
from app.services.roster_csv import plan_import
from tests.helpers import CLASS_ID, JPEG, PNG, open_archive, reasons, roster_csv


def test_header_is_case_insensitive_order_independent_and_bom_tolerant() -> None:
    plan = plan_import(
        roster_csv(
            "1.png,7,Ada Lovelace", header="Image_Filename, ROLL_NO ,Student_Name", bom=True
        ),
        archive=open_archive({"1.png": PNG}),
        class_id=CLASS_ID,
        max_rows=10,
    )
    assert plan.errors == []
    assert [(row.roll_no, row.student_name) for row in plan.rows] == [(7, "Ada Lovelace")]
    assert plan.rows[0].class_id == CLASS_ID


def test_missing_columns_are_a_request_error() -> None:
    with pytest.raises(InvalidRequestError) as excinfo:
        plan_import(roster_csv("Ada,1,1.png"), archive=None, class_id=None, max_rows=10)
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
        roster_csv("Ada,,1.png", "Grace,CS2024001,1.png", "Alan,0,1.png", "Edsger,4,1.png"),
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
    with pytest.raises(PayloadTooLargeError) as excinfo:
        plan_import(
            roster_csv(*[f"Student {index},{index},{index}.png" for index in range(1, 6)]),
            archive=open_archive({f"{index}.png": PNG for index in range(1, 6)}),
            class_id=CLASS_ID,
            max_rows=3,
        )
    assert excinfo.value.details["max_rows"] == 3


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
