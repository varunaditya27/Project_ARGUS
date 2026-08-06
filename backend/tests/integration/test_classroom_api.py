"""Classroom endpoints over HTTP, against a real database."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import requires_database

pytestmark = [pytest.mark.database, requires_database]

VALID = {"class_name": "CSE-A", "department": "CSE", "semester": 5, "strength": 60}


async def create(client: AsyncClient, **overrides: object) -> dict:
    response = await client.post("/api/v1/classrooms", json={**VALID, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_created_classroom_reads_back(db_client: AsyncClient) -> None:
    created = await create(db_client)
    fetched = await db_client.get(f"/api/v1/classrooms/{created['class_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["class_name"] == "CSE-A"


async def test_the_detail_view_counts_the_real_roster_not_the_declared_strength(
    db_client: AsyncClient,
) -> None:
    # strength is what the timetable claims; roster_count is what attendance uses.
    classroom = await create(db_client, strength=60)
    for roll_no in (1, 2):
        await db_client.post(
            "/api/v1/students",
            json={
                "student_name": f"Student {roll_no}",
                "roll_no": roll_no,
                "class_id": classroom["class_id"],
                "image_url": f"https://images.example.test/{roll_no}.jpg",
            },
        )
    detail = (await db_client.get(f"/api/v1/classrooms/{classroom['class_id']}")).json()
    assert (detail["strength"], detail["roster_count"]) == (60, 2)


async def test_listing_filters_by_department_and_semester(db_client: AsyncClient) -> None:
    await create(db_client, class_name="CSE-A", department="CSE", semester=5)
    await create(db_client, class_name="ECE-B", department="ECE", semester=3)

    cse = (await db_client.get("/api/v1/classrooms", params={"department": "CSE"})).json()
    assert [room["class_name"] for room in cse["items"]] == ["CSE-A"]

    third = (await db_client.get("/api/v1/classrooms", params={"semester": 3})).json()
    assert [room["class_name"] for room in third["items"]] == ["ECE-B"]


async def test_offset_paging_walks_the_list_without_repeats(db_client: AsyncClient) -> None:
    for index in range(5):
        await create(db_client, class_name=f"Room {index}")
    first = (await db_client.get("/api/v1/classrooms", params={"limit": 2})).json()
    second = (await db_client.get("/api/v1/classrooms", params={"limit": 2, "offset": 2})).json()
    assert len(first["items"]) == len(second["items"]) == 2
    assert not {room["class_id"] for room in first["items"]} & {
        room["class_id"] for room in second["items"]
    }


async def test_an_offset_past_the_end_returns_an_empty_page(db_client: AsyncClient) -> None:
    # Edge: paging past the last row is empty, not an error.
    await create(db_client)
    page = (await db_client.get("/api/v1/classrooms", params={"offset": 500})).json()
    assert page["items"] == []


async def test_an_unknown_classroom_is_a_404(db_client: AsyncClient) -> None:
    response = await db_client.get(f"/api/v1/classrooms/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_a_malformed_uuid_is_a_validation_error(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/classrooms/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    "invalid",
    [
        {"class_name": ""},
        {"department": ""},
        {"semester": 0},
        {"semester": 13},
        {"strength": -1},
    ],
)
async def test_out_of_range_fields_are_refused(db_client: AsyncClient, invalid: dict) -> None:
    response = await db_client.post("/api/v1/classrooms", json={**VALID, **invalid})
    assert response.status_code == 422


async def test_a_page_size_beyond_the_cap_is_refused(db_client: AsyncClient) -> None:
    # Edge: the cap exists so one request cannot pull 20 000 rows.
    response = await db_client.get("/api/v1/classrooms", params={"limit": 5000})
    assert response.status_code == 422
