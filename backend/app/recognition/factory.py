"""Builds the recognition stack from settings.

Single place where "which adapter is in use" is decided. A component falls back
to its placeholder only when the corresponding model file is not configured, so a
deployment either runs the real model or fails loudly - never something in
between.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.recognition.adapters.arcface import ArcFaceEmbedder
from app.recognition.adapters.chroma_index import ChromaTemplateIndex
from app.recognition.adapters.mask_synthesis import GeometricMaskSynthesizer
from app.recognition.adapters.placeholder import (
    PlaceholderFaceDetector,
    PlaceholderFaceEmbedder,
    UnconfiguredTemplateIndex,
)
from app.recognition.adapters.scrfd import ScrfdFaceDetector
from app.recognition.decision import Thresholds
from app.recognition.ports import (
    ComponentStatus,
    FaceDetector,
    FaceEmbedder,
    MaskSynthesizer,
    TemplateIndex,
)

logger = get_logger(__name__)


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
        """Version tag written into Chroma metadata for every stored template.

        Templates produced by different model files must be distinguishable, so
        the tag is the adapter plus the model file name rather than a constant.
        """
        embedder = self.embedder.status()
        if not embedder.configured:
            return "unconfigured"
        model_file = embedder.detail.split(" ", 1)[0]
        return f"{embedder.adapter}/{model_file}"

    def warmup(self) -> None:
        """Load every configured model so /health reports the truth before traffic."""
        for component in (self.detector, self.embedder):
            warmup = getattr(component, "warmup", None)
            if callable(warmup):
                warmup()


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


def build_face_detector(settings: Settings) -> FaceDetector:
    path = settings.resolved_detector_path
    if path is None:
        logger.warning(
            "No detector model configured; set ARGUS_MODEL_ROOT or "
            "ARGUS_DETECTOR_MODEL_PATH to enable face detection"
        )
        return PlaceholderFaceDetector()
    return ScrfdFaceDetector(
        path,
        providers=tuple(settings.onnx_providers),
        intra_op_threads=settings.onnx_intra_op_threads,
        input_size=settings.detection_input_size,
        score_threshold=settings.detection_score_threshold,
        nms_iou=settings.detection_nms_iou,
        max_faces=settings.detection_max_faces,
    )


def build_face_embedder(settings: Settings) -> FaceEmbedder:
    path = settings.resolved_embedder_path
    if path is None:
        logger.warning(
            "No embedding model configured; set ARGUS_MODEL_ROOT or "
            "ARGUS_EMBEDDER_MODEL_PATH to enable recognition"
        )
        return PlaceholderFaceEmbedder()
    return ArcFaceEmbedder(
        path,
        providers=tuple(settings.onnx_providers),
        intra_op_threads=settings.onnx_intra_op_threads,
        embedding_dim=settings.embedding_dim,
    )


def build_recognition_stack(settings: Settings) -> RecognitionStack:
    return RecognitionStack(
        detector=build_face_detector(settings),
        embedder=build_face_embedder(settings),
        # Purely geometric, so it needs no model file of its own.
        mask_synthesizer=GeometricMaskSynthesizer(settings.mask_variants),
        index=build_template_index(settings),
        thresholds=Thresholds(
            match=settings.match_threshold,
            review=settings.review_threshold,
            minimum_margin=settings.minimum_margin,
        ),
        embedding_dim=settings.embedding_dim,
        mask_variants=tuple(settings.mask_variants),
    )
