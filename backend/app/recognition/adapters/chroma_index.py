"""ChromaDB template index.

Chroma stores the 512-D vectors; PostgreSQL stores identities. Metadata keys are
the ones documented in ``docs/db.md``: ``student_id``, ``mask_type``,
``model_version``.

The Chroma client is synchronous, so every call is pushed to a worker thread -
a blocking k-NN search inside the event loop would stall every other request.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger
from app.recognition.ports import ComponentStatus, Embedding, TemplateMatch

logger = get_logger(__name__)

#: Cosine space, matching "similarity = 1 - cosine_distance" in docs/design.md.
_COLLECTION_METADATA = {"hnsw:space": "cosine"}


def _template_id(student_id: uuid.UUID, mask_type: str) -> str:
    return f"{student_id}:{mask_type}"


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
        self._collection: Any | None = None
        self._client: Any | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ wiring
    def status(self) -> ComponentStatus:
        target = self._persist_path or f"{self._host}:{self._port}"
        return ComponentStatus(
            name="template_index",
            configured=True,
            adapter="chromadb",
            detail=f"collection={self._collection_name} target={target}",
        )

    def _connect(self) -> Any:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - depends on the install extra
            raise DependencyUnavailableError(
                "chromadb is not installed. Install the recognition extra: "
                "pip install -e '.[recognition]'."
            ) from exc

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
        if self._collection is None:
            async with self._lock:
                if self._collection is None:
                    self._collection = await asyncio.to_thread(self._connect)
        return self._collection

    async def _call(self, method: str, /, **kwargs: Any) -> Any:
        collection = await self._get_collection()
        try:
            return await asyncio.to_thread(lambda: getattr(collection, method)(**kwargs))
        except Exception as exc:
            raise DependencyUnavailableError(
                f"ChromaDB {method} failed.", details={"driver_error": str(exc)}
            ) from exc

    # ------------------------------------------------------------------- reads
    async def ping(self) -> None:
        await self._get_collection()
        assert self._client is not None
        try:
            await asyncio.to_thread(self._client.heartbeat)
        except Exception as exc:
            raise DependencyUnavailableError(
                "ChromaDB heartbeat failed.", details={"driver_error": str(exc)}
            ) from exc

    async def count(self) -> int:
        return int(await self._call("count"))

    async def search(self, embeddings: Sequence[Embedding], k: int) -> list[list[TemplateMatch]]:
        if len(embeddings) == 0:
            return []
        result = await self._call(
            "query",
            query_embeddings=[
                np.asarray(embedding, dtype=np.float32).tolist() for embedding in embeddings
            ],
            n_results=k,
            include=["metadatas", "distances"],
        )
        metadatas = result.get("metadatas") or []
        distances = result.get("distances") or []
        return [
            self._to_matches(probe_metadatas, probe_distances)
            for probe_metadatas, probe_distances in zip(metadatas, distances, strict=False)
        ]

    @staticmethod
    def _to_matches(metadatas: Sequence[Any], distances: Sequence[float]) -> list[TemplateMatch]:
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
                    #: docs/design.md: similarity = 1 - cosine_distance.
                    similarity=1.0 - float(distance),
                )
            )
        return matches

    async def list_templates(self, student_id: uuid.UUID) -> list[str]:
        result = await self._call(
            "get", where={"student_id": str(student_id)}, include=["metadatas"]
        )
        metadatas = result.get("metadatas") or []
        return sorted(str((metadata or {}).get("mask_type", "unknown")) for metadata in metadatas)

    # ------------------------------------------------------------------ writes
    async def upsert(
        self, student_id: uuid.UUID, templates: Mapping[str, Embedding], *, model_version: str
    ) -> int:
        if not templates:
            return 0
        mask_types = list(templates)
        await self._call(
            "upsert",
            ids=[_template_id(student_id, mask_type) for mask_type in mask_types],
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
        existing = await self.list_templates(student_id)
        if existing:
            await self._call("delete", where={"student_id": str(student_id)})
        return len(existing)
