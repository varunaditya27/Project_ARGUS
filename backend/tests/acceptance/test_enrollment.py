"""AT-01 to AT-05: getting a person into the gallery, and refusing to.

Driven entirely through HTTP against the real detector, embedder, mask
synthesizer and Chroma store.
"""

from __future__ import annotations

import pytest

from tests import images
from tests.acceptance.conftest import Stack

pytestmark = pytest.mark.acceptance


async def test_at01_a_clear_photograph_enrolls(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    response = await stack.enroll(student_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student_id"] == student_id
    assert "UNMASKED" in body["stored_variants"]
    assert body["templates_stored"] == len(body["stored_variants"])


async def test_at02_masked_variants_are_stored_against_the_same_identity(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    stored = (await stack.enroll(student_id)).json()["stored_variants"]

    templates = (await stack.client.get(f"/api/v1/students/{student_id}/templates")).json()
    assert templates["student_id"] == student_id
    assert set(templates["templates"]) == set(stored)
    # The point of the exercise: the gallery is masked as well as unmasked.
    assert len(set(stored) - {"UNMASKED"}) >= 1


async def test_at02_re_enrolling_replaces_rather_than_accumulates(stack: Stack) -> None:
    # Edge: a second enrollment of the same person must not double the gallery.
    student_id = await stack.student(await stack.classroom())
    first = (await stack.enroll(student_id)).json()["templates_stored"]
    await stack.enroll(student_id)

    templates = (await stack.client.get(f"/api/v1/students/{student_id}/templates")).json()
    assert len(templates["templates"]) == first


async def test_at03_a_photograph_with_no_face_is_refused(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    response = await stack.enroll(student_id, images.blank())

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert "face" in error["message"].lower()


async def test_at04_a_photograph_with_two_faces_is_refused(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    response = await stack.enroll(student_id, images.two_faces())

    assert response.status_code == 422
    assert "face" in response.json()["error"]["message"].lower()


async def test_at05_a_truncated_image_is_refused_without_crashing(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    response = await stack.enroll(student_id, images.corrupt())

    assert response.status_code == 422
    # The service is still answering afterwards.
    assert (await stack.client.get("/api/v1/health")).status_code == 200


async def test_at05_a_file_that_is_not_an_image_is_refused(stack: Stack) -> None:
    student_id = await stack.student(await stack.classroom())
    response = await stack.enroll(student_id, b"#!/bin/sh\nrm -rf /\n")
    assert response.status_code == 422


async def test_at05_an_oversized_upload_is_refused(tmp_path, stack: Stack) -> None:
    # Edge: the cap is enforced before the frame is decoded.
    limit = stack.container.settings.enrollment_max_image_bytes
    student_id = await stack.student(await stack.classroom())
    response = await stack.enroll(student_id, b"\xff\xd8\xff\xe0" + b"\x00" * (limit + 1))
    assert response.status_code in (413, 422)


async def test_enrolling_an_unknown_student_is_a_404(stack: Stack) -> None:
    import uuid

    response = await stack.enroll(str(uuid.uuid4()))
    assert response.status_code == 404
