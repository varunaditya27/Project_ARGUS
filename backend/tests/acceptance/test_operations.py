"""AT-15 to AT-18: how the system behaves when it is not fully provisioned."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests import images
from tests.acceptance.conftest import Stack
from tests.conftest import make_client, make_settings
from tests.helpers import PNG, build_zip, roster_csv

pytestmark = pytest.mark.acceptance


async def test_at15_uncalibrated_thresholds_can_never_match(uncalibrated: Stack) -> None:
    # The shipped default. An enrolled person is still found - the system just
    # refuses to call it a match, and says why.
    class_id = await uncalibrated.classroom(strength=1)
    student_id = await uncalibrated.student(class_id, roll_no=1)
    await uncalibrated.enroll(student_id)
    session_id = await uncalibrated.session(class_id)

    face = (await uncalibrated.recognize(images.sample_face_bytes(), session_id)).json()["faces"][0]

    assert face["state"] == "HUMAN_REVIEW"
    assert face["student_id"] == student_id
    assert "calibrat" in face["reason"].lower()
    assert face["attendance_recorded"] is False


async def test_at15_the_models_endpoint_admits_it_is_not_ready(uncalibrated: Stack) -> None:
    body = (await uncalibrated.client.get("/api/v1/models")).json()
    assert body["recognition_ready"] is False
    assert all(component["configured"] for component in body["components"])
    assert body["thresholds"]["match_threshold"] is None


async def test_at15_an_uncalibrated_session_closes_everyone_absent(uncalibrated: Stack) -> None:
    # Edge: refusing to guess has a consequence, and it is a visible one.
    class_id = await uncalibrated.classroom(strength=2)
    student_id = await uncalibrated.student(class_id, roll_no=1)
    await uncalibrated.student(class_id, roll_no=2)
    await uncalibrated.enroll(student_id)
    session_id = await uncalibrated.session(class_id)

    await uncalibrated.recognize(images.sample_face_bytes(), session_id)
    report = (await uncalibrated.client.post(f"/api/v1/sessions/{session_id}/close")).json()
    assert (report["present"], report["absent_marked"]) == (0, 2)


async def test_at16_a_missing_dependency_is_named_not_guessed_around() -> None:
    # Nothing provisioned at all: every surface says which setting is missing.
    async with make_client(make_settings()) as client:
        health = await client.get("/api/v1/health")
        assert health.status_code == 503
        assert health.json()["status"] == "degraded"

        recognise = await client.post(
            "/api/v1/recognize", files={"frame": ("f.jpg", images.blank(), "image/jpeg")}
        )
        assert recognise.status_code == 503
        assert recognise.json()["error"]["code"] == "dependency_not_configured"


async def test_at16_an_unreachable_database_fails_explicitly(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.get("/api/v1/classrooms")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"


async def test_at17_a_roster_import_commits_the_good_rows_and_reports_the_rest(
    stack: Stack,
) -> None:
    class_id = await stack.classroom(strength=3)
    csv_bytes = roster_csv(
        "Ada Lovelace,1,ada.png",
        "Grace Hopper,CS002,grace.png",
        "Alan Turing,3,missing.png",
        "Ada Again,1,ada.png",
    )
    response = await stack.client.post(
        "/api/v1/students/import",
        files={
            "csv_file": ("roster.csv", csv_bytes, "text/csv"),
            "images": ("images.zip", build_zip({"ada.png": PNG}).getvalue(), "application/zip"),
        },
        data={"class_id": class_id, "dry_run": "false"},
    )

    report = response.json()
    assert (report["created"], report["skipped"]) == (1, 3)
    assert report["uploaded_images"] == 1
    assert {error["row"] for error in report["errors"]} == {3, 4, 5}

    roster = (await stack.client.get("/api/v1/students")).json()
    assert [student["roll_no"] for student in roster["items"]] == [1]


async def test_at17_a_dry_run_writes_nothing(stack: Stack) -> None:
    class_id = await stack.classroom()
    response = await stack.client.post(
        "/api/v1/students/import",
        files={
            "csv_file": ("roster.csv", roster_csv("Ada Lovelace,1,ada.png"), "text/csv"),
            "images": ("images.zip", build_zip({"ada.png": PNG}).getvalue(), "application/zip"),
        },
        data={"class_id": class_id, "dry_run": "true"},
    )
    assert response.json()["created"] == 1
    assert (await stack.client.get("/api/v1/students")).json()["items"] == []


async def test_at18_an_offline_batch_decides_every_image(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom(strength=1), roll_no=1)
    await stack.enroll(student_id)
    archive = build_zip(
        {"a.jpg": images.sample_face_bytes(), "b.jpg": images.blank(), "notes.txt": b"ignored"}
    )

    result = (
        await stack.client.post(
            "/api/v1/recognize/batch",
            files={"archive": ("batch.zip", archive.getvalue(), "application/zip")},
        )
    ).json()

    assert result["processed"] == 2
    assert result["faces_detected"] == 1
    assert result["matched"] + result["human_review"] + result["unknown"] == 1
