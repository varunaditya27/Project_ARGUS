"""Placeholder adapters for the vision components that are not implemented yet.

They deliberately contain **no** model, no heuristic and no fabricated output:
every call raises 503 with the exact next step. The rest of the backend
(sessions, capture intervals, absence computation, reporting) is complete and
switches over the moment a real adapter is registered in
:mod:`app.recognition.factory`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from app.core.errors import DependencyNotConfiguredError
from app.recognition.ports import (
    ComponentStatus,
    DetectedFace,
    Embedding,
    Image,
    TemplateMatch,
)

_IMPLEMENT_HERE = "app/recognition/adapters/"


def _unavailable(component: str, requirement: str) -> DependencyNotConfiguredError:
    return DependencyNotConfiguredError(
        f"The {component} is not implemented yet, so this endpoint cannot return a result.",
        details={"component": component, "required": requirement, "implement_in": _IMPLEMENT_HERE},
    )


class PlaceholderFaceDetector:
    """Stands in for SCRFD."""

    _REQUIREMENT = "SCRFD adapter + ARGUS_DETECTOR_MODEL_PATH"

    def status(self) -> ComponentStatus:
        return ComponentStatus(
            name="face_detector",
            configured=False,
            adapter="placeholder",
            detail=f"not implemented; requires {self._REQUIREMENT}",
        )

    def detect(self, image: Image) -> list[DetectedFace]:
        raise _unavailable("face detector (SCRFD)", self._REQUIREMENT)


class PlaceholderFaceEmbedder:
    """Stands in for ArcFace."""

    _REQUIREMENT = "ArcFace adapter + ARGUS_EMBEDDER_MODEL_PATH"

    def status(self) -> ComponentStatus:
        return ComponentStatus(
            name="face_embedder",
            configured=False,
            adapter="placeholder",
            detail=f"not implemented; requires {self._REQUIREMENT}",
        )

    def embed(self, aligned_faces: Sequence[Image]) -> Embedding:
        raise _unavailable("face embedder (ArcFace)", self._REQUIREMENT)


class PlaceholderMaskSynthesizer:
    """Stands in for MaskTheFace / RWMFD synthetic mask generation."""

    _REQUIREMENT = "MaskTheFace adapter + ARGUS_MASK_SYNTHESIZER_ROOT"

    def status(self) -> ComponentStatus:
        return ComponentStatus(
            name="mask_synthesizer",
            configured=False,
            adapter="placeholder",
            detail=f"not implemented; requires {self._REQUIREMENT}",
        )

    def synthesize(self, aligned_face: Image) -> dict[str, Image]:
        raise _unavailable("mask synthesizer (MaskTheFace)", self._REQUIREMENT)


class UnconfiguredTemplateIndex:
    """Used when ARGUS_CHROMA_MODE=disabled."""

    _REQUIREMENT = "ARGUS_CHROMA_MODE=persistent|http"

    def status(self) -> ComponentStatus:
        return ComponentStatus(
            name="template_index",
            configured=False,
            adapter="disabled",
            detail=f"vector index disabled; set {self._REQUIREMENT}",
        )

    def _fail(self) -> DependencyNotConfiguredError:
        return _unavailable("template index (ChromaDB)", self._REQUIREMENT)

    async def ping(self) -> None:
        raise self._fail()

    async def count(self) -> int:
        raise self._fail()

    async def upsert(
        self, student_id: uuid.UUID, templates: Mapping[str, Embedding], *, model_version: str
    ) -> int:
        raise self._fail()

    async def search(self, embeddings: Sequence[Embedding], k: int) -> list[list[TemplateMatch]]:
        raise self._fail()

    async def delete_student(self, student_id: uuid.UUID) -> int:
        raise self._fail()

    async def list_templates(self, student_id: uuid.UUID) -> list[str]:
        raise self._fail()
