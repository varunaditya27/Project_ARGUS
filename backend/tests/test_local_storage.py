"""Filesystem object storage and the enrollment image upload endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.errors import InvalidRequestError
from app.storage.local import LocalObjectStorage
from tests.conftest import make_client, make_settings
from tests.helpers import PNG


def make_storage(root: Path) -> LocalObjectStorage:
    return LocalObjectStorage(
        root=root, public_base_url="http://localhost:8000/media", key_prefix="enrollment"
    )


async def test_image_is_written_and_addressable_by_its_url(tmp_path: Path) -> None:
    stored = await make_storage(tmp_path).put_image(PNG, namespace="uploads", filename="ada.png")
    assert stored.key.startswith("enrollment/uploads/") and stored.key.endswith(".png")
    assert stored.url == f"http://localhost:8000/media/{stored.key}"
    assert (tmp_path / stored.key).read_bytes() == PNG


async def test_the_same_image_reuses_its_key(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    first = await storage.put_image(PNG, namespace="uploads", filename="ada.png")
    second = await storage.put_image(PNG, namespace="uploads", filename="copy.png")
    assert first.key == second.key
    assert len(list((tmp_path / "enrollment/uploads").iterdir())) == 1


async def test_bytes_that_are_not_an_image_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidRequestError):
        await make_storage(tmp_path).put_image(
            b"not a picture", namespace="uploads", filename="notes.txt"
        )
    assert not (tmp_path / "enrollment").exists()


async def test_upload_endpoint_stores_the_image_and_serves_it_back(tmp_path: Path) -> None:
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


async def test_upload_endpoint_reports_disabled_storage(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/students/image", files={"image": ("ada.png", PNG, "image/png")}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_not_configured"


async def test_uploads_do_not_need_a_database(tmp_path: Path) -> None:
    # Storing an image is pure object storage, so it works before PostgreSQL is up.
    settings = make_settings(object_storage_mode="local", local_storage_path=tmp_path)
    async with make_client(settings) as client:
        response = await client.post(
            "/api/v1/students/image", files={"image": ("ada.png", PNG, "image/png")}
        )
    assert response.status_code == 200
