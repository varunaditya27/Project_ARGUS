"""AT-06 to AT-10: what the system decides when it looks at a frame.

These assert decision *behaviour* - who is returned, and whether the system
refuses to guess. They are not an accuracy measurement; that lives in
``evaluation/`` against a labelled set, because the repository ships one face.
"""

from __future__ import annotations

import pytest

from tests import images
from tests.acceptance.conftest import Stack

pytestmark = pytest.mark.acceptance


async def test_at06_an_enrolled_person_is_recognised(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    await stack.enroll(student_id)

    faces = (await stack.recognize(images.sample_face_bytes())).json()["faces"]

    assert len(faces) == 1
    assert faces[0]["state"] == "MATCH"
    assert faces[0]["student_id"] == student_id
    assert faces[0]["similarity"] is not None


async def test_at07_a_covered_face_still_resolves_to_the_enrolled_identity(stack: Stack) -> None:
    # The gallery holds synthetic masked templates; the probe is occluded by a
    # flat rectangle, drawn by different code, so this is not self-fulfilling.
    student_id = await stack.student(await stack.classroom())
    await stack.enroll(student_id)

    bbox = (await stack.recognize(images.sample_face_bytes())).json()["faces"][0]["bbox"]
    faces = (await stack.recognize(images.occluded(tuple(bbox)))).json()["faces"]

    assert len(faces) == 1
    assert faces[0]["state"] != "UNKNOWN"
    assert faces[0]["student_id"] == student_id


async def test_at08_a_face_with_no_gallery_entry_is_unknown(stack: Stack) -> None:
    # Nobody is enrolled, so the nearest neighbour does not exist to be guessed.
    await stack.student(await stack.classroom())

    faces = (await stack.recognize(images.sample_face_bytes())).json()["faces"]

    assert len(faces) == 1
    assert faces[0]["state"] == "UNKNOWN"
    assert faces[0]["student_id"] is None


async def test_at09_a_heavily_blurred_face_is_not_matched(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    await stack.enroll(student_id)

    faces = (await stack.recognize(images.blurred())).json()["faces"]

    # Either the detector declines it or the decision layer refuses to commit.
    assert all(face["state"] != "MATCH" for face in faces)
    assert all(face["reason"] for face in faces)


async def test_at09_a_tiny_face_is_not_matched(stack: Stack) -> None:
    # Edge: a face far across the room carries too few pixels to identify.
    student_id = await stack.student(await stack.classroom())
    await stack.enroll(student_id)

    faces = (await stack.recognize(images.tiny())).json()["faces"]
    assert all(face["state"] != "MATCH" for face in faces)


async def test_at10_every_face_in_a_frame_gets_its_own_decision(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    await stack.enroll(student_id)

    faces = (await stack.recognize(images.two_faces())).json()["faces"]

    assert len(faces) == 2
    boxes = [tuple(face["bbox"]) for face in faces]
    assert len(set(boxes)) == 2
    assert all(face["state"] for face in faces)


async def test_a_frame_with_nobody_in_it_returns_no_faces(stack: Stack) -> None:
    # Edge: an empty room is a valid frame, not an error.
    response = await stack.recognize(images.blank())
    assert response.status_code == 200
    assert response.json()["faces"] == []


async def test_an_undecodable_frame_is_refused(stack: Stack) -> None:
    response = await stack.recognize(images.corrupt())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


async def test_the_bounding_box_lies_inside_the_frame(stack: Stack) -> None:
    faces = (await stack.recognize(images.sample_face_bytes())).json()["faces"]
    x1, y1, x2, y2 = faces[0]["bbox"]
    assert 0 <= x1 < x2
    assert 0 <= y1 < y2
