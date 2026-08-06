"""Adapter used when ``ARGUS_OBJECT_STORAGE_MODE=disabled``.

It contains no fallback and no placeholder URL: ``students.image_url`` is NOT
NULL and must point at a real object, so a request that needs an upload fails
with 503 and the exact environment variables to set.
"""

from __future__ import annotations

from app.core.errors import DependencyNotConfiguredError
from app.storage.ports import StorageStatus, StoredObject

_REQUIRED_ENV = (
    "ARGUS_OBJECT_STORAGE_MODE=r2",
    "ARGUS_R2_ENDPOINT_URL",
    "ARGUS_R2_BUCKET",
    "ARGUS_R2_ACCESS_KEY_ID",
    "ARGUS_R2_SECRET_ACCESS_KEY",
    "ARGUS_R2_PUBLIC_BASE_URL",
)


class UnconfiguredObjectStorage:
    def status(self) -> StorageStatus:
        return StorageStatus(
            name="object_storage",
            configured=False,
            adapter="disabled",
            detail=f"object storage disabled; set {', '.join(_REQUIRED_ENV)}",
        )

    def ensure_configured(self) -> None:
        raise DependencyNotConfiguredError(
            "Cloudflare R2 is not configured, so enrollment images cannot be uploaded and "
            "students.image_url cannot be filled. Supply an already-hosted image_url per row "
            "or configure object storage.",
            details={"component": "object_storage", "required_env": list(_REQUIRED_ENV)},
        )

    async def put_image(
        self, data: bytes, *, namespace: str, filename: str | None = None
    ) -> StoredObject:
        self.ensure_configured()
        raise AssertionError("unreachable: ensure_configured always raises here")
