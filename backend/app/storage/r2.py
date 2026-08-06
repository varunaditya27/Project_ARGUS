"""Cloudflare R2 adapter.

R2 speaks the S3 API, so the client is plain boto3 pointed at the account's R2
endpoint. boto3 is synchronous and its calls are network-bound, so every call is
pushed to a worker thread - a blocking PUT inside the event loop would stall every
other request while a roster import uploads thousands of images.

Object keys are deterministic: ``{prefix}/{namespace}/{sha256-prefix}.{ext}``.
Re-uploading the same image for the same student overwrites the same object
instead of littering the bucket, which makes a retried import idempotent.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from app.core.errors import DependencyUnavailableError, InvalidRequestError
from app.core.logging import get_logger
from app.storage.ports import StorageStatus, StoredObject, sniff_image_type

logger = get_logger(__name__)

#: Long enough that a collision is not a practical concern, short enough to keep
#: keys readable in logs.
_DIGEST_CHARS = 32


class R2ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        public_base_url: str,
        key_prefix: str,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._public_base_url = public_base_url.rstrip("/")
        self._key_prefix = key_prefix.strip("/")
        self._client: Any | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ wiring
    def status(self) -> StorageStatus:
        return StorageStatus(
            name="object_storage",
            configured=True,
            adapter="cloudflare-r2",
            detail=f"bucket={self._bucket} endpoint={self._endpoint_url}",
        )

    def ensure_configured(self) -> None:
        """Nothing to check: the settings validator guarantees the credentials."""

    def _connect(self) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on the install extra
            raise DependencyUnavailableError(
                "boto3 is not installed. Install the storage extra: pip install -e '.[storage]'."
            ) from exc

        try:
            return boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                # R2 exposes a single pseudo-region and requires SigV4.
                region_name="auto",
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                "The Cloudflare R2 client could not be created.",
                details={"driver_error": str(exc)},
            ) from exc

    async def _get_client(self) -> Any:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = await asyncio.to_thread(self._connect)
        return self._client

    # ------------------------------------------------------------------- writes
    def _key(self, namespace: str, digest: str, extension: str) -> str:
        parts = [part for part in (self._key_prefix, namespace.strip("/")) if part]
        parts.append(f"{digest[:_DIGEST_CHARS]}.{extension}")
        return "/".join(parts)

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        image_type = sniff_image_type(data)
        if image_type is None:
            raise InvalidRequestError(
                "The image could not be recognised as a JPEG, PNG, WEBP, GIF or BMP file.",
                details={"filename": filename, "received_bytes": len(data)},
            )

        key = self._key(namespace, hashlib.sha256(data).hexdigest(), image_type.extension)
        client = await self._get_client()
        # The original archive entry name is kept as metadata so an object in the
        # bucket can always be traced back to the import that produced it.
        metadata = {"original-filename": filename} if filename else {}
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=image_type.media_type,
                Metadata=metadata,
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                "Cloudflare R2 rejected the upload.",
                details={"bucket": self._bucket, "key": key, "driver_error": str(exc)},
            ) from exc

        logger.debug("Uploaded %s (%d bytes) to R2", key, len(data))
        return StoredObject(
            key=key,
            url=f"{self._public_base_url}/{key}",
            media_type=image_type.media_type,
            size_bytes=len(data),
        )
