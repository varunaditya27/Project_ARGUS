"""Student endpoints over HTTP: roster writes, reads and keyset paging."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import requires_database

pytestmark = [pytest.mark.database, requires_database]


async def classroom(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/classrooms",
        json={"class_name": "CSE-A", "department": "CSE", "semester": 5, "strength": 3},
    )
    return response.json()["class_id"]


async def add(client: AsyncClient, roll_no: int, class_id: str | None = None, **overrides: object):
    return await client.post(
        "/api/v1/students",
        json={
            "student_name": f"Student {roll_no}",
            "roll_no": roll_no,
            "class_id": class_id,
            "image_url": f"https://images.example.test/{roll_no}.jpg",
            **overrides,
        },
    )


async def test_a_created_student_reads_back(db_client: AsyncClient) -> None:
    created = (await add(db_client, 1, await classroom(db_client))).json()
    fetched = await db_client.get(f"/api/v1/students/{created['student_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["roll_no"] == 1


async def test_a_student_may_be_unassigned(db_client: AsyncClient) -> None:
    # class_id is nullable in docs/db.md: a transfer leaves the row valid.
    response = await add(db_client, 7, None)
    assert response.status_code == 201
    assert response.json()["class_id"] is None


async def test_a_duplicate_roll_number_is_a_conflict(db_client: AsyncClient) -> None:
    class_id = await classroom(db_client)
    assert (await add(db_client, 1, class_id)).status_code == 201
    duplicate = await add(db_client, 1, class_id)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


async def test_roll_numbers_are_unique_across_classrooms(db_client: AsyncClient) -> None:
    # Edge: the uniqueness in docs/db.md is global, not per classroom.
    await add(db_client, 1, await classroom(db_client))
    other = await db_client.post(
        "/api/v1/classrooms",
        json={"class_name": "ECE-B", "department": "ECE", "semester": 3, "strength": 3},
    )
    assert (await add(db_client, 1, other.json()["class_id"])).status_code == 409


@pytest.mark.parametrize("roll_no", [0, -1, "CS2024001", 1.5])
async def test_a_roll_number_that_is_not_a_positive_integer_is_refused(
    db_client: AsyncClient, roll_no: object
) -> None:
    assert (await add(db_client, roll_no)).status_code == 422  # type: ignore[arg-type]


@pytest.mark.parametrize("image_url", ["", "not-a-url", "ftp://images.test/1.jpg"])
async def test_an_unusable_image_url_is_refused(db_client: AsyncClient, image_url: str) -> None:
    response = await add(db_client, 2, await classroom(db_client), image_url=image_url)
    assert response.status_code == 422


async def test_keyset_paging_walks_the_roster_in_roll_number_order(db_client: AsyncClient) -> None:
    class_id = await classroom(db_client)
    for roll_no in range(1, 6):
        await add(db_client, roll_no, class_id)

    seen: list[int] = []
    cursor: int | None = None
    while True:
        params: dict[str, object] = {"limit": 2, "class_id": class_id}
        if cursor is not None:
            params["after"] = cursor
        page = (await db_client.get("/api/v1/students", params=params)).json()
        seen.extend(student["roll_no"] for student in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [1, 2, 3, 4, 5]


async def test_the_cursor_is_absent_on_a_short_page(db_client: AsyncClient) -> None:
    # Edge: fewer rows than the limit means there is nothing after them.
    await add(db_client, 1, await classroom(db_client))
    page = (await db_client.get("/api/v1/students", params={"limit": 50})).json()
    assert page["next_cursor"] is None


async def test_deleting_a_student_removes_them(db_client: AsyncClient) -> None:
    created = (await add(db_client, 1, await classroom(db_client))).json()
    deleted = await db_client.delete(f"/api/v1/students/{created['student_id']}")
    assert deleted.status_code == 200
    assert (await db_client.get(f"/api/v1/students/{created['student_id']}")).status_code == 404


async def test_unknown_students_are_404s_everywhere(db_client: AsyncClient) -> None:
    missing = uuid.uuid4()
    assert (await db_client.get(f"/api/v1/students/{missing}")).status_code == 404
    assert (await db_client.delete(f"/api/v1/students/{missing}")).status_code == 404
    assert (await db_client.get(f"/api/v1/students/{missing}/attendance")).status_code == 404
