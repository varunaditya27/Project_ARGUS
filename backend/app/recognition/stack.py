"""Composition of the vision stack.

The single place that decides which adapter is in use. A component that has no
model file configured is left as None and the accessors below raise 503 naming
the missing setting, so a deployment either runs the real model or refuses to
answer - it never returns a guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import DependencyNotConfiguredError
from app.recognition.adapters.masks import GeometricMaskSynthesizer
from app.recognition.decision import Thresholds
from app.recognition.ports import (
    ComponentStatus,
    FaceDetector,
    FaceEmbedder,
    MaskSynthesizer,
    TemplateIndex,
)

_MISSING = {
    "face_detector": "ARGUS_MODEL_ROOT or ARGUS_DETECTOR_MODEL_PATH (det_10g.onnx)",
    "face_embedder": "ARGUS_MODEL_ROOT or ARGUS_EMBEDDER_MODEL_PATH (w600k_r50.onnx)",
    "template_index": "ARGUS_CHROMA_MODE=persistent|http",
}


def _not_configured(component: str) -> DependencyNotConfiguredError:
    # 503 that names the setting the deployment is missing.
    return DependencyNotConfiguredError(
        f"The {component} is not configured, so this endpoint cannot return a result.",
        details={"component": component, "required": _MISSING[component]},
    )


def _missing_status(component: str) -> ComponentStatus:
    # Status entry for a component that was never built.
    return ComponentStatus(
        name=component, configured=False, detail=f"not configured; set {_MISSING[component]}"
    )


@dataclass(frozen=True, slots=True)
class RecognitionStack:
    mask_synthesizer: MaskSynthesizer
    thresholds: Thresholds
    model_version: str
    detector: FaceDetector | None = None
    embedder: FaceEmbedder | None = None
    index: TemplateIndex | None = None

    @property
    def face_detector(self) -> FaceDetector:
        # The detector, or 503 if no model file is configured.
        if self.detector is None:
            raise _not_configured("face_detector")
        return self.detector

    @property
    def face_embedder(self) -> FaceEmbedder:
        # The embedder, or 503 if no model file is configured.
        if self.embedder is None:
            raise _not_configured("face_embedder")
        return self.embedder

    @property
    def template_index(self) -> TemplateIndex:
        # The vector index, or 503 if Chroma is disabled.
        if self.index is None:
            raise _not_configured("template_index")
        return self.index

    @property
    def statuses(self) -> list[ComponentStatus]:
        # What /models reports, one entry per component.
        return [
            self.detector.status() if self.detector else _missing_status("face_detector"),
            self.embedder.status() if self.embedder else _missing_status("face_embedder"),
            self.mask_synthesizer.status(),
            self.index.status() if self.index else _missing_status("template_index"),
        ]

    @property
    def ready(self) -> bool:
        # True only when every component is real and the thresholds are calibrated.
        return all(status.configured for status in self.statuses) and self.thresholds.calibrated

    def warmup(self) -> None:
        # Load the ONNX graphs so /models reports the truth before traffic.
        for component in (self.detector, self.embedder):
            if component is not None:
                component.warmup()


def build_recognition_stack(settings: Settings) -> RecognitionStack:
    # Build every component the settings actually configure.
    detector_path = settings.model_file(settings.detector_model_path, "det_10g.onnx")
    embedder_path = settings.model_file(settings.embedder_model_path, "w600k_r50.onnx")

    detector: FaceDetector | None = None
    if detector_path is not None:
        from app.recognition.adapters.scrfd import ScrfdFaceDetector

        detector = ScrfdFaceDetector(
            detector_path,
            providers=tuple(settings.onnx_providers),
            intra_op_threads=settings.onnx_intra_op_threads,
            input_size=settings.detection_input_size,
            score_threshold=settings.detection_score_threshold,
            nms_iou=settings.detection_nms_iou,
            max_faces=settings.detection_max_faces,
        )

    embedder: FaceEmbedder | None = None
    if embedder_path is not None:
        from app.recognition.adapters.arcface import ArcFaceEmbedder

        embedder = ArcFaceEmbedder(
            embedder_path,
            providers=tuple(settings.onnx_providers),
            intra_op_threads=settings.onnx_intra_op_threads,
            embedding_dim=settings.embedding_dim,
        )

    return RecognitionStack(
        # Purely geometric, so it needs no model file of its own.
        mask_synthesizer=GeometricMaskSynthesizer(settings.mask_variants),
        thresholds=Thresholds(
            match=settings.match_threshold,
            review=settings.review_threshold,
            minimum_margin=settings.minimum_margin,
        ),
        # Templates produced by different weights must be distinguishable.
        model_version=f"arcface/{embedder_path.name}" if embedder_path else "unconfigured",
        detector=detector,
        embedder=embedder,
        index=_build_index(settings),
    )


def _build_index(settings: Settings) -> TemplateIndex | None:
    # Chroma is optional; disabled leaves the index unset.
    if settings.chroma_mode == "disabled":
        return None
    from app.recognition.adapters.chroma import ChromaTemplateIndex

    if settings.chroma_mode == "persistent":
        assert settings.chroma_path is not None
        return ChromaTemplateIndex(
            collection_name=settings.chroma_collection, persist_path=str(settings.chroma_path)
        )
    return ChromaTemplateIndex(
        collection_name=settings.chroma_collection,
        host=settings.chroma_host,
        port=settings.chroma_port,
    )
