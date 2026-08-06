"""Fallbacks used when a component has not been configured.

They contain **no** model, no heuristic and no fabricated output: every call
raises 503 naming the setting that is missing. A deployment therefore either runs
the real SCRFD/ArcFace/Chroma stack or refuses to answer - it never guesses.
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


def _unavailable(component: str, requirement: str) -> DependencyNotConfiguredError:
    return DependencyNotConfiguredError(
        f"The {component} is not configured, so this endpoint cannot return a result.",
        details={"component": component, "required": requirement},
    )


class PlaceholderFaceDetector:
    """Used when no SCRFD model file is configured."""

    _REQUIREMENT = "ARGUS_MODEL_ROOT or ARGUS_DETECTOR_MODEL_PATH (det_10g.onnx)"

    def status(self) -> ComponentStatus:
        return ComponentStatus(
            name="face_detector",
            configured=False,
            adapter="placeholder",
            detail=f"no model configured; set {self._REQUIREMENT}",
        )

    def detect(self, image: Image) -> list[DetectedFace]:
        raise _unavailable("face detector (SCRFD)", self._REQUIREMENT)


class PlaceholderFaceEmbedder:
    """Used when no ArcFace model file is configured."""

    _REQUIREMENT = "ARGUS_MODEL_ROOT or ARGUS_EMBEDDER_MODEL_PATH (w600k_r50.onnx)"

    def status(self) -> ComponentStatus:
        return ComponentStatus(
            name="face_embedder",
            configured=False,
            adapter="placeholder",
            detail=f"no model configured; set {self._REQUIREMENT}",
        )

    def embed(self, aligned_faces: Sequence[Image]) -> Embedding:
        raise _unavailable("face embedder (ArcFace)", self._REQUIREMENT)


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
