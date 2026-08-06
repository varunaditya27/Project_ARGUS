"""POST /students/image, and the /media mount that serves what it stored."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.conftest import make_client, make_settings
from tests.helpers import PNG


async def test_upload_stores_the_image_and_serves_it_back(tmp_path: Path) -> None:
    settings = make_settings(
        object_storage_mode="local",
        local_storage_path=tmp_path,
        local_public_base_url="http://testserver/media",
    )
    async with make_client(settings) as client:
        response = await client.post(
            "/api/v1/students/image", files={"image": ("ada.png", PNG, "image/png")}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["url"] == f"http://testserver/media/{body['key']}"

        served = await client.get(f"/media/{body['key']}")
        assert served.status_code == 200
        assert served.content == PNG


async def test_upload_does_not_need_a_database(tmp_path: Path) -> None:
    # Storing an image is pure object storage, so it works before PostgreSQL is up.
    settings = make_settings(object_storage_mode="local", local_storage_path=tmp_path)
    async with make_client(settings) as client:
        response = await client.post(
            "/api/v1/students/image", files={"image": ("ada.png", PNG, "image/png")}
        )
    assert response.status_code == 200


async def test_upload_reports_disabled_storage(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/students/image", files={"image": ("ada.png", PNG, "image/png")}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_not_configured"


async def test_upload_rejects_a_file_that_is_not_an_image(tmp_path: Path) -> None:
    settings = make_settings(object_storage_mode="local", local_storage_path=tmp_path)
    async with make_client(settings) as client:
        response = await client.post(
            "/api/v1/students/image", files={"image": ("notes.txt", b"plain text", "text/plain")}
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


async def test_missing_file_field_is_a_validation_error(tmp_path: Path) -> None:
    settings = make_settings(object_storage_mode="local", local_storage_path=tmp_path)
    async with make_client(settings) as client:
        response = await client.post("/api/v1/students/image")
    assert response.status_code == 422


async def test_media_mount_does_not_serve_outside_its_root(tmp_path: Path) -> None:
    # Edge: traversal in the served path must not reach the parent directory.
    (tmp_path.parent / "secret.txt").write_bytes(b"nope")
    settings = make_settings(object_storage_mode="local", local_storage_path=tmp_path)
    async with make_client(settings) as client:
        response = await client.get("/media/../secret.txt")
    assert response.status_code in (307, 404)
