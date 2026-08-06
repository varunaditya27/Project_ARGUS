"""Interfaces between the attendance backend and the vision stack.

The backend depends on these protocols only; the concrete adapters live in
app.recognition.adapters, which keeps the attendance logic testable without
onnxruntime or Chroma installed.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]
Embedding = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class DetectedFace:
    #: (x1, y1, x2, y2) in pixels.
    bbox: tuple[int, int, int, int]
    detection_score: float
    #: 5x2: left eye, right eye, nose, left mouth corner, right mouth corner.
    landmarks: NDArray[np.float32]

    @property
    def width(self) -> int:
        # Detected box width in pixels.
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        # Detected box height in pixels.
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
    detail: str


class FaceDetector(Protocol):
    def status(self) -> ComponentStatus: ...

    def warmup(self) -> None: ...

    def detect(self, image: Image) -> list[DetectedFace]:
        """Every face found in a BGR image."""


class FaceEmbedder(Protocol):
    def status(self) -> ComponentStatus: ...

    def warmup(self) -> None: ...

    def embed(self, aligned_faces: Sequence[Image]) -> Embedding:
        """One L2-normalised embedding row per aligned face."""


class MaskSynthesizer(Protocol):
    def status(self) -> ComponentStatus: ...

    def synthesize(self, aligned_face: Image) -> dict[str, Image]:
        """{variant_name: masked_face}; partial failure is allowed."""


class TemplateIndex(Protocol):
    def status(self) -> ComponentStatus: ...

    async def ping(self) -> None: ...

    async def count(self) -> int: ...

    async def upsert(
        self, student_id: uuid.UUID, templates: Mapping[str, Embedding], *, model_version: str
    ) -> int:
        """Store or replace {mask_type: embedding} for one student."""

    async def search(self, embeddings: Sequence[Embedding], k: int) -> list[list[TemplateMatch]]:
        """Nearest templates per probe, in probe order; batched per frame."""

    async def delete_student(self, student_id: uuid.UUID) -> int: ...

    async def list_templates(self, student_id: uuid.UUID) -> list[str]: ...
