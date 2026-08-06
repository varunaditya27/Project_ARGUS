"""Filesystem object storage: keys, content addressing and rejections."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.errors import InvalidRequestError
from app.storage.local import LocalObjectStorage
from app.storage.ports import sniff_image_type
from tests.helpers import JPEG, PNG


def make_storage(root: Path, *, prefix: str = "enrollment") -> LocalObjectStorage:
    return LocalObjectStorage(
        root=root, public_base_url="http://localhost:8000/media", key_prefix=prefix
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


async def test_different_images_get_different_keys(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    png = await storage.put_image(PNG, namespace="uploads", filename="a.png")
    jpeg = await storage.put_image(JPEG, namespace="uploads", filename="b.jpg")
    assert png.key != jpeg.key
    assert jpeg.key.endswith(".jpg")


async def test_an_empty_prefix_leaves_no_leading_slash(tmp_path: Path) -> None:
    # Edge: a deployment that puts images at the bucket root.
    stored = await make_storage(tmp_path, prefix="").put_image(PNG, namespace="uploads")
    assert stored.key.startswith("uploads/")
    assert stored.url == f"http://localhost:8000/media/{stored.key}"


async def test_bytes_that_are_not_an_image_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidRequestError):
        await make_storage(tmp_path).put_image(
            b"not a picture", namespace="uploads", filename="notes.txt"
        )
    assert not (tmp_path / "enrollment").exists()


async def test_empty_upload_is_rejected(tmp_path: Path) -> None:
    # Edge: a zero-byte file has no magic bytes to identify.
    with pytest.raises(InvalidRequestError):
        await make_storage(tmp_path).put_image(b"", namespace="uploads", filename="empty.png")


async def test_no_staging_file_survives_a_write(tmp_path: Path) -> None:
    # The image lands via a .part file that must be renamed away.
    stored = await make_storage(tmp_path).put_image(PNG, namespace="uploads", filename="ada.png")
    written = os.listdir((tmp_path / stored.key).parent)
    assert [name for name in written if name.endswith(".part")] == []


@pytest.mark.parametrize(
    ("data", "extension"),
    [
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "jpg"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "png"),
        (b"GIF89a" + b"\x00" * 8, "gif"),
        (b"BM" + b"\x00" * 8, "bmp"),
        (b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 4, "webp"),
    ],
)
def test_every_accepted_format_is_identified(data: bytes, extension: str) -> None:
    image_type = sniff_image_type(data)
    assert image_type is not None
    assert image_type.extension == extension


@pytest.mark.parametrize("data", [b"", b"RIFF____NOTWEBP", b"\x89PN", b"<html>"])
def test_lookalikes_are_not_mistaken_for_images(data: bytes) -> None:
    # Edge: a truncated PNG header and a RIFF container that is not WEBP.
    assert sniff_image_type(data) is None
