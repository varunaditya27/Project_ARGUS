"""Interface between the backend and the object store that holds enrollment images.

``docs/db.md`` makes ``students.image_url`` NOT NULL and points it at Cloudflare
R2, so every write path that creates a student needs an upload first. The backend
depends on this protocol only; the boto3 client lives in :mod:`app.storage.r2`
and the unconfigured adapter in :mod:`app.storage.disabled`. That keeps the
roster import testable without boto3, credentials or a network.

The status descriptor mirrors :class:`app.recognition.ports.ComponentStatus` but
is declared here rather than imported: object storage must not depend on the
vision stack (and therefore on numpy/onnxruntime) to answer "am I wired up?".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StorageStatus:
    name: str
    configured: bool
    adapter: str
    detail: str


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
    media_type: str
    size_bytes: int


#: Formats accepted for an enrollment image, keyed by their leading magic bytes.
_MAGIC: tuple[tuple[bytes, ImageType], ...] = (
    (b"\xff\xd8\xff", ImageType("image/jpeg", "jpg")),
    (b"\x89PNG\r\n\x1a\n", ImageType("image/png", "png")),
    (b"GIF87a", ImageType("image/gif", "gif")),
    (b"GIF89a", ImageType("image/gif", "gif")),
    (b"BM", ImageType("image/bmp", "bmp")),
)
_WEBP = ImageType("image/webp", "webp")


def sniff_image_type(data: bytes) -> ImageType | None:
    """Identify an image from its leading bytes; ``None`` when it is not an image.

    Magic bytes only, deliberately: the import path validates thousands of
    archive entries and must not pull OpenCV in to do it. A file that passes here
    is a picture of a known container format -- whether it holds a usable face is
    decided later by the enrollment path.
    """
    for magic, image_type in _MAGIC:
        if data.startswith(magic):
            return image_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _WEBP
    return None


@runtime_checkable
class ObjectStorage(Protocol):
    def status(self) -> StorageStatus: ...

    def ensure_configured(self) -> None:
        """Raise ``DependencyNotConfiguredError`` when uploads cannot be performed.

        Callers use this to fail a request *before* doing any other work, instead
        of discovering the misconfiguration halfway through a 20 000 row import.
        """

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        """Upload image bytes and return the publicly readable object.

        ``namespace`` groups the object (the import path passes the student UUID);
        ``filename`` is the original name, recorded alongside the object so it can
        be traced back to the archive entry it came from. Raises
        ``InvalidRequestError`` when ``data`` is not a recognisable image and
        ``DependencyUnavailableError`` when the store rejects the upload.
        """
