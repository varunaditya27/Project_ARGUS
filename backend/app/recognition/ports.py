"""Interfaces between the attendance backend and the vision stack.

The backend never imports a model directly: it depends on these protocols and the
concrete adapters live in :mod:`app.recognition.adapters`. That keeps the
attendance logic testable without SCRFD/ArcFace/Chroma installed, and lets the
model work land as a self-contained adapter.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]
Embedding = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class DetectedFace:
    #: (x1, y1, x2, y2) in pixels.
    bbox: tuple[int, int, int, int]
    detection_score: float
    #: 5x2 array: left eye, right eye, nose, left mouth corner, right mouth corner.
    landmarks: NDArray[np.float32]

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    """One neighbour returned by the vector index."""

    student_id: uuid.UUID
    template_type: str
    similarity: float


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    name: str
    configured: bool
    adapter: str
    detail: str


@runtime_checkable
class FaceDetector(Protocol):
    def status(self) -> ComponentStatus: ...

    def detect(self, image: Image) -> list[DetectedFace]:
        """Return every face found in a BGR image."""


@runtime_checkable
class FaceEmbedder(Protocol):
    def status(self) -> ComponentStatus: ...

    def embed(self, aligned_faces: Sequence[Image]) -> Embedding:
        """Return one L2-normalised embedding row per aligned face."""


@runtime_checkable
class MaskSynthesizer(Protocol):
    def status(self) -> ComponentStatus: ...

    def synthesize(self, aligned_face: Image) -> dict[str, Image]:
        """Return ``{variant_name: masked_face}``; partial failure is allowed."""


@runtime_checkable
class TemplateIndex(Protocol):
    def status(self) -> ComponentStatus: ...

    async def ping(self) -> None: ...

    async def count(self) -> int: ...

    async def upsert(
        self, student_id: uuid.UUID, templates: Mapping[str, Embedding], *, model_version: str
    ) -> int:
        """Store/replace ``{mask_type: embedding}`` for a student."""

    async def search(self, embeddings: Sequence[Embedding], k: int) -> list[list[TemplateMatch]]:
        """Nearest templates for each probe, in probe order.

        Batched because one frame can hold several faces (acceptance test AT-10);
        the index is queried once per frame instead of once per face.
        """

    async def delete_student(self, student_id: uuid.UUID) -> int: ...

    async def list_templates(self, student_id: uuid.UUID) -> list[str]: ...
