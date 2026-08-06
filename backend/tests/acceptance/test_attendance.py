"""AT-11 to AT-14: recognition turning into a register, and identities leaving it."""

from __future__ import annotations

import pytest

from tests import images
from tests.acceptance.conftest import Stack

pytestmark = pytest.mark.acceptance


async def test_at11_a_recognised_student_is_marked_present_during_the_session(
    stack: Stack,
) -> None:
    class_id = await stack.classroom(strength=3)
    student_id = await stack.student(class_id, roll_no=1)
    for roll_no in (2, 3):
        await stack.student(class_id, roll_no=roll_no)
    await stack.enroll(student_id)
    session_id = await stack.session(class_id)

    decision = (await stack.recognize(images.sample_face_bytes(), session_id)).json()
    assert decision["faces"][0]["attendance_recorded"] is True

    assert await stack.flush() == 1
    register = (await stack.client.get(f"/api/v1/sessions/{session_id}/attendance")).json()
    assert [row["roll_no"] for row in register["items"]] == [1]
    assert register["items"][0]["status"] == "Present"

    summary = (await stack.client.get(f"/api/v1/sessions/{session_id}/attendance/summary")).json()
    assert (summary["present"], summary["absent"], summary["roster_count"]) == (1, 0, 3)


async def test_at11_seeing_the_same_person_twice_writes_one_row(stack: Stack) -> None:
    # Edge: attendance is per student per session, not per detection.
    class_id = await stack.classroom(strength=1)
    student_id = await stack.student(class_id, roll_no=1)
    await stack.enroll(student_id)
    session_id = await stack.session(class_id)

    await stack.recognize(images.sample_face_bytes(), session_id)
    await stack.flush()
    await stack.recognize(images.sample_face_bytes(), session_id)
    await stack.flush()

    register = (await stack.client.get(f"/api/v1/sessions/{session_id}/attendance")).json()
    assert len(register["items"]) == 1


async def test_at12_absence_is_derived_once_at_close(stack: Stack) -> None:
    class_id = await stack.classroom(strength=3)
    seen = await stack.student(class_id, roll_no=1)
    for roll_no in (2, 3):
        await stack.student(class_id, roll_no=roll_no)
    await stack.enroll(seen)
    session_id = await stack.session(class_id)

    await stack.recognize(images.sample_face_bytes(), session_id)
    report = (await stack.client.post(f"/api/v1/sessions/{session_id}/close")).json()

    # The buffered sighting is flushed by the close, before absence is computed.
    assert (report["present"], report["absent_marked"], report["roster_count"]) == (1, 2, 3)
    absent = (
        await stack.client.get(
            f"/api/v1/sessions/{session_id}/attendance", params={"status": "Absent"}
        )
    ).json()
    assert [row["roll_no"] for row in absent["items"]] == [2, 3]
    assert all(row["confidence"] == 0.0 for row in absent["items"])


async def test_at13_a_closed_session_records_nothing_further(stack: Stack) -> None:
    class_id = await stack.classroom(strength=1)
    student_id = await stack.student(class_id, roll_no=1)
    await stack.enroll(student_id)
    session_id = await stack.session(class_id)
    await stack.client.post(f"/api/v1/sessions/{session_id}/close")

    await stack.recognize(images.sample_face_bytes(), session_id)
    await stack.flush()

    summary = (await stack.client.get(f"/api/v1/sessions/{session_id}/attendance/summary")).json()
    assert summary["session_status"] == "CLOSED"
    assert summary["present"] == 0


async def test_at14_deleting_an_identity_removes_it_from_the_gallery(stack: Stack) -> None:
    class_id = await stack.classroom()
    student_id = await stack.student(class_id, roll_no=1)
    await stack.enroll(student_id)
    assert (await stack.recognize(images.sample_face_bytes())).json()["faces"][0][
        "state"
    ] == "MATCH"

    deleted = await stack.client.delete(f"/api/v1/students/{student_id}")
    assert deleted.status_code == 200
    assert deleted.json()["templates_removed"] >= 1

    faces = (await stack.recognize(images.sample_face_bytes())).json()["faces"]
    assert faces[0]["state"] == "UNKNOWN"
    assert faces[0]["student_id"] is None


async def test_at14_deleting_an_identity_removes_their_attendance(stack: Stack) -> None:
    class_id = await stack.classroom(strength=1)
    student_id = await stack.student(class_id, roll_no=1)
    await stack.enroll(student_id)
    session_id = await stack.session(class_id)
    await stack.recognize(images.sample_face_bytes(), session_id)
    await stack.flush()

    await stack.client.delete(f"/api/v1/students/{student_id}")

    register = (await stack.client.get(f"/api/v1/sessions/{session_id}/attendance")).json()
    assert register["items"] == []


async def test_recognition_without_a_session_records_nothing(stack: Stack) -> None:
    # Edge: a frame posted with no session is a lookup, not attendance.
    class_id = await stack.classroom(strength=1)
    student_id = await stack.student(class_id, roll_no=1)
    await stack.enroll(student_id)
    session_id = await stack.session(class_id)

    faces = (await stack.recognize(images.sample_face_bytes())).json()["faces"]
    assert faces[0]["attendance_recorded"] is False
    assert await stack.flush() == 0

    summary = (await stack.client.get(f"/api/v1/sessions/{session_id}/attendance/summary")).json()
    assert summary["present"] == 0
