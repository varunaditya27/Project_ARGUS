"""Session endpoints over HTTP: the lifecycle a client actually drives."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import requires_database

pytestmark = [pytest.mark.database, requires_database]

LECTURE = {
    "subject": "Computer Vision",
    "faculty": "Dr. Placeholder",
    "date": "2026-08-06",
    "start_time": "09:00:00",
    "end_time": "10:00:00",
}


async def classroom(client: AsyncClient, name: str = "CSE-A") -> str:
    response = await client.post(
        "/api/v1/classrooms",
        json={"class_name": name, "department": "CSE", "semester": 5, "strength": 3},
    )
    return response.json()["class_id"]


async def open_session(client: AsyncClient, class_id: str, **overrides: object):
    return await client.post(
        "/api/v1/sessions", json={**LECTURE, "class_id": class_id, **overrides}
    )


async def test_opening_a_session_returns_it_active(db_client: AsyncClient) -> None:
    response = await open_session(db_client, await classroom(db_client))
    assert response.status_code == 201
    assert response.json()["status"] == "ACTIVE"


async def test_a_classroom_cannot_hold_two_active_sessions(db_client: AsyncClient) -> None:
    class_id = await classroom(db_client)
    await open_session(db_client, class_id)
    second = await open_session(db_client, class_id, subject="Second lecture")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_a_new_session_opens_once_the_first_closes(db_client: AsyncClient) -> None:
    class_id = await classroom(db_client)
    first = (await open_session(db_client, class_id)).json()
    await db_client.post(f"/api/v1/sessions/{first['session_id']}/close")
    assert (await open_session(db_client, class_id, subject="Second")).status_code == 201


async def test_two_classrooms_run_in_parallel(db_client: AsyncClient) -> None:
    # The one-active rule is per classroom, not global.
    assert (await open_session(db_client, await classroom(db_client, "A"))).status_code == 201
    assert (await open_session(db_client, await classroom(db_client, "B"))).status_code == 201


async def test_listing_filters_by_status_and_date(db_client: AsyncClient) -> None:
    class_id = await classroom(db_client)
    first = (await open_session(db_client, class_id)).json()
    await db_client.post(f"/api/v1/sessions/{first['session_id']}/close")
    await open_session(db_client, class_id, subject="Later", date="2026-08-07")

    active = (await db_client.get("/api/v1/sessions", params={"status": "ACTIVE"})).json()
    assert [item["subject"] for item in active["items"]] == ["Later"]

    early = (await db_client.get("/api/v1/sessions", params={"date_to": "2026-08-06"})).json()
    assert [item["subject"] for item in early["items"]] == ["Computer Vision"]


async def test_an_unknown_status_filter_is_refused(db_client: AsyncClient) -> None:
    response = await db_client.get("/api/v1/sessions", params={"status": "PENDING"})
    assert response.status_code == 422


async def test_a_session_that_ends_before_it_starts_is_refused(db_client: AsyncClient) -> None:
    response = await open_session(
        db_client, await classroom(db_client), start_time="10:00:00", end_time="09:00:00"
    )
    assert response.status_code == 422
    assert "end_time" in response.text


async def test_a_zero_length_session_is_refused(db_client: AsyncClient) -> None:
    # Edge of the same rule: the window must be positive, not merely non-negative.
    response = await open_session(
        db_client, await classroom(db_client), start_time="09:00:00", end_time="09:00:00"
    )
    assert response.status_code == 422


async def test_a_session_for_an_unknown_classroom_is_refused(db_client: AsyncClient) -> None:
    response = await open_session(db_client, str(uuid.uuid4()))
    assert response.status_code in (409, 422)


async def test_reading_and_closing_an_unknown_session_are_404s(db_client: AsyncClient) -> None:
    missing = uuid.uuid4()
    assert (await db_client.get(f"/api/v1/sessions/{missing}")).status_code == 404
    assert (await db_client.post(f"/api/v1/sessions/{missing}/close")).status_code == 404


async def test_closing_twice_is_a_conflict(db_client: AsyncClient) -> None:
    session = (await open_session(db_client, await classroom(db_client))).json()
    close = f"/api/v1/sessions/{session['session_id']}/close"
    assert (await db_client.post(close)).status_code == 200
    assert (await db_client.post(close)).status_code == 409
