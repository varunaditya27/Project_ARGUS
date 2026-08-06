"""ChromaDB template index.

Chroma stores the 512-D vectors, PostgreSQL stores identities. The metadata keys
are the ones documented in docs/db.md: student_id, mask_type, model_version. The
client is synchronous, so every call runs on a worker thread.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import chromadb
import numpy as np

from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.recognition.ports import ComponentStatus, Embedding, TemplateMatch

logger = get_logger(__name__)

#: Cosine space, so similarity = 1 - distance.
_COLLECTION_METADATA = {"hnsw:space": "cosine"}


class ChromaTemplateIndex:
    def __init__(
        self,
        *,
        collection_name: str,
        persist_path: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._persist_path = persist_path
        self._host = host
        self._port = port
        self._client: Any | None = None
        self._collection: Any | None = None
        self._lock = asyncio.Lock()

    def status(self) -> ComponentStatus:
        # Where the collection lives; connectivity is reported by ping().
        target = self._persist_path or f"{self._host}:{self._port}"
        return ComponentStatus(
            name="template_index",
            configured=True,
            detail=f"chromadb collection={self._collection_name} target={target}",
        )

    def _connect(self) -> Any:
        # Open the client and get or create the cosine collection.
        try:
            self._client = (
                chromadb.PersistentClient(path=self._persist_path)
                if self._persist_path
                else chromadb.HttpClient(host=self._host, port=self._port)
            )
            return self._client.get_or_create_collection(
                name=self._collection_name, metadata=_COLLECTION_METADATA
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                "ChromaDB is not reachable.", details={"driver_error": str(exc)}
            ) from exc

    async def _get_collection(self) -> Any:
        # Connect once, under a lock so concurrent requests cannot both connect.
        if self._collection is None:
            async with self._lock:
                if self._collection is None:
                    self._collection = await asyncio.to_thread(self._connect)
        return self._collection

    async def _call(self, method: str, /, **kwargs: Any) -> Any:
        # Run one blocking collection method on a worker thread.
        collection = await self._get_collection()
        try:
            return await asyncio.to_thread(lambda: getattr(collection, method)(**kwargs))
        except Exception as exc:
            raise DependencyUnavailableError(
                f"ChromaDB {method} failed.", details={"driver_error": str(exc)}
            ) from exc

    async def ping(self) -> None:
        # Health probe: connecting and counting exercises the whole client path.
        await self.count()

    async def count(self) -> int:
        # Number of stored templates.
        return int(await self._call("count"))

    async def search(self, embeddings: Sequence[Embedding], k: int) -> list[list[TemplateMatch]]:
        # One query for the whole frame; results come back in probe order.
        if len(embeddings) == 0:
            return []
        result = await self._call(
            "query",
            query_embeddings=[np.asarray(e, dtype=np.float32).tolist() for e in embeddings],
            n_results=k,
            include=["metadatas", "distances"],
        )
        return [
            _to_matches(metadatas, distances)
            for metadatas, distances in zip(
                result.get("metadatas") or [], result.get("distances") or [], strict=False
            )
        ]

    async def list_templates(self, student_id: uuid.UUID) -> list[str]:
        # mask_type labels stored for one student.
        result = await self._call(
            "get", where={"student_id": str(student_id)}, include=["metadatas"]
        )
        return sorted(
            str((metadata or {}).get("mask_type", "unknown"))
            for metadata in result.get("metadatas") or []
        )

    async def upsert(
        self, student_id: uuid.UUID, templates: Mapping[str, Embedding], *, model_version: str
    ) -> int:
        # Store or replace this student's gallery; ids are stable per mask type.
        if not templates:
            return 0
        mask_types = list(templates)
        await self._call(
            "upsert",
            ids=[f"{student_id}:{mask_type}" for mask_type in mask_types],
            embeddings=[
                np.asarray(templates[mask_type], dtype=np.float32).tolist()
                for mask_type in mask_types
            ],
            metadatas=[
                {
                    "student_id": str(student_id),
                    "mask_type": mask_type,
                    "model_version": model_version,
                }
                for mask_type in mask_types
            ],
        )
        return len(mask_types)

    async def delete_student(self, student_id: uuid.UUID) -> int:
        # Remove every template that could still match a deleted identity.
        existing = await self.list_templates(student_id)
        if existing:
            await self._call("delete", where={"student_id": str(student_id)})
        return len(existing)


def _to_matches(metadatas: Sequence[Any], distances: Sequence[float]) -> list[TemplateMatch]:
    # Turn one probe's neighbours into domain matches; similarity = 1 - distance.
    matches: list[TemplateMatch] = []
    for metadata, distance in zip(metadatas, distances, strict=False):
        student_id = (metadata or {}).get("student_id")
        if student_id is None:
            logger.warning("Chroma returned a template without student_id metadata")
            continue
        matches.append(
            TemplateMatch(
                student_id=uuid.UUID(str(student_id)),
                template_type=str((metadata or {}).get("mask_type", "unknown")),
                similarity=1.0 - float(distance),
            )
        )
    return matches
