"""Filesystem adapter for enrollment images.

Same contract as the R2 adapter, but the bytes land in a directory the API also
serves, so a deployment can enroll students without cloud credentials. Keys stay
content-addressed - {prefix}/{namespace}/{sha256}.{ext} - so a retried upload
overwrites instead of accumulating copies.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from app.core.errors import DependencyUnavailableError, InvalidRequestError
from app.storage.ports import StoredObject, sniff_image_type

_DIGEST_CHARS = 32


class LocalObjectStorage:
    def __init__(self, *, root: Path, public_base_url: str, key_prefix: str) -> None:
        self._root = Path(root)
        self._public_base_url = public_base_url.rstrip("/")
        self._key_prefix = key_prefix.strip("/")

    def describe(self) -> str:
        # Shown in the startup log and the health payload.
        return f"local-filesystem root={self._root}"

    def _key(self, namespace: str, digest: str, extension: str) -> str:
        # {prefix}/{namespace}/{digest}.{ext}, skipping empty segments.
        parts = [part for part in (self._key_prefix, namespace.strip("/")) if part]
        parts.append(f"{digest[:_DIGEST_CHARS]}.{extension}")
        return "/".join(parts)

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        # Verify the bytes are an image, then write under a content-addressed key.
        image_type = sniff_image_type(data)
        if image_type is None:
            raise InvalidRequestError(
                "The image could not be recognised as a JPEG, PNG, WEBP, GIF or BMP file.",
                details={"filename": filename},
            )
        key = self._key(namespace, hashlib.sha256(data).hexdigest(), image_type.extension)
        try:
            await asyncio.to_thread(self._write, key, data)
        except OSError as exc:
            raise DependencyUnavailableError(
                "The image could not be written to local storage.",
                details={"key": key, "driver_error": str(exc)},
            ) from exc
        return StoredObject(key=key, url=f"{self._public_base_url}/{key}")

    def _write(self, key: str, data: bytes) -> None:
        # Write via a temporary file so a reader never sees a half-written image.
        destination = self._root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_suffix(destination.suffix + ".part")
        staging.write_bytes(data)
        staging.replace(destination)
