"""Builds the recognition stack from settings.

Single place where "which adapter is in use" is decided, so swapping a
placeholder for a real model is a one-line change here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.recognition.adapters.chroma_index import ChromaTemplateIndex
from app.recognition.adapters.placeholder import (
    PlaceholderFaceDetector,
    PlaceholderFaceEmbedder,
    PlaceholderMaskSynthesizer,
    UnconfiguredTemplateIndex,
)
from app.recognition.decision import Thresholds
from app.recognition.ports import (
    ComponentStatus,
    FaceDetector,
    FaceEmbedder,
    MaskSynthesizer,
    TemplateIndex,
)


@dataclass(frozen=True, slots=True)
class RecognitionStack:
    detector: FaceDetector
    embedder: FaceEmbedder
    mask_synthesizer: MaskSynthesizer
    index: TemplateIndex
    thresholds: Thresholds
    embedding_dim: int
    mask_variants: tuple[str, ...]

    @property
    def statuses(self) -> list[ComponentStatus]:
        return [
            self.detector.status(),
            self.embedder.status(),
            self.mask_synthesizer.status(),
            self.index.status(),
        ]

    @property
    def ready(self) -> bool:
        """True only when every component is real and the thresholds are calibrated."""
        return all(status.configured for status in self.statuses) and self.thresholds.calibrated

    @property
    def model_version(self) -> str:
        """Version tag written into Chroma metadata for every stored template."""
        embedder = self.embedder.status()
        return f"{embedder.adapter}:{embedder.detail}" if embedder.configured else "unconfigured"


def build_template_index(settings: Settings) -> TemplateIndex:
    if settings.chroma_mode == "persistent":
        assert settings.chroma_path is not None
        return ChromaTemplateIndex(
            collection_name=settings.chroma_collection,
            persist_path=str(settings.chroma_path),
        )
    if settings.chroma_mode == "http":
        return ChromaTemplateIndex(
            collection_name=settings.chroma_collection,
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return UnconfiguredTemplateIndex()


def build_recognition_stack(settings: Settings) -> RecognitionStack:
    return RecognitionStack(
        # Replace these three with the SCRFD / ArcFace / MaskTheFace adapters once
        # they exist; nothing else in the backend needs to change.
        detector=PlaceholderFaceDetector(),
        embedder=PlaceholderFaceEmbedder(),
        mask_synthesizer=PlaceholderMaskSynthesizer(),
        index=build_template_index(settings),
        thresholds=Thresholds(
            match=settings.match_threshold,
            review=settings.review_threshold,
            minimum_margin=settings.minimum_margin,
        ),
        embedding_dim=settings.embedding_dim,
        mask_variants=tuple(settings.mask_variants),
    )
