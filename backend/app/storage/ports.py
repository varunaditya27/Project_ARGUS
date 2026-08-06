"""Interface to the object store that holds enrollment images.

docs/db.md makes students.image_url NOT NULL and points it at Cloudflare R2, so
every write path that creates a student needs an upload first. The backend
depends on this protocol only, which keeps the roster import testable without
boto3, credentials or a network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImageType:
    media_type: str
    extension: str


@dataclass(frozen=True, slots=True)
class StoredObject:
    #: Object key inside the bucket, kept so an orphaned upload can be named in
    #: the logs when the database write that should have referenced it fails.
    key: str
    url: str


#: Accepted enrollment image formats, keyed by their leading magic bytes.
_MAGIC: tuple[tuple[bytes, ImageType], ...] = (
    (b"\xff\xd8\xff", ImageType("image/jpeg", "jpg")),
    (b"\x89PNG\r\n\x1a\n", ImageType("image/png", "png")),
    (b"GIF87a", ImageType("image/gif", "gif")),
    (b"GIF89a", ImageType("image/gif", "gif")),
    (b"BM", ImageType("image/bmp", "bmp")),
)
_WEBP = ImageType("image/webp", "webp")


def sniff_image_type(data: bytes) -> ImageType | None:
    # Identify an image from its leading bytes; None when it is not one. Magic
    # bytes only, so validating thousands of archive entries stays cheap.
    for magic, image_type in _MAGIC:
        if data.startswith(magic):
            return image_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _WEBP
    return None


class ObjectStorage(Protocol):
    def describe(self) -> str: ...

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        """Upload image bytes and return the publicly readable object."""
