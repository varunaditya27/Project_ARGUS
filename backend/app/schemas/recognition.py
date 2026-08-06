"""Recognition wire format (mirrors the Pydantic models in docs/design.md)."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.domain.enums import DecisionState
from app.schemas.common import ApiModel


class CandidateOut(ApiModel):
    student_id: uuid.UUID
    similarity: float = Field(ge=-1.0, le=1.0)
    matched_template: str


class FaceDecisionOut(ApiModel):
    bbox: tuple[int, int, int, int]
    detection_score: float = Field(ge=0.0, le=1.0)
    state: DecisionState
    student_id: uuid.UUID | None = None
    similarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    second_best_similarity: float | None = None
    margin: float | None = None
    matched_template: str | None = None
    reason: str
    #: True when this decision created/updated an attendance observation.
    attendance_recorded: bool = False
    candidates: list[CandidateOut] = Field(default_factory=list)


class FrameResult(ApiModel):
    request_id: str
    frame_id: str
    latency_ms: float = Field(ge=0)
    session_id: uuid.UUID | None = None
    faces: list[FaceDecisionOut]


class BatchItemResult(ApiModel):
    """One archive entry or one sampled video frame."""

    source: str
    faces: int = 0
    matched: int = 0
    human_review: int = 0
    unknown: int = 0
    error: str | None = None


class BatchRecognitionResult(ApiModel):
    """Outcome of an offline run over a video or an archive of stills."""

    request_id: str
    session_id: uuid.UUID | None = None
    processed: int
    skipped: int
    faces_detected: int
    matched: int
    human_review: int
    unknown: int
    attendance_observations: int = Field(
        description="Distinct students handed to the capture buffer for this session. Absence is "
        "still only computed when the session is closed."
    )
    latency_ms: float = Field(ge=0)
    items: list[BatchItemResult]
    items_truncated: bool = Field(
        default=False, description="True when per-item detail was capped for response size."
    )


class EnrollmentResult(ApiModel):
    student_id: uuid.UUID
    templates_stored: int
    stored_variants: list[str]
    failed_variants: list[str] = Field(
        default_factory=list,
        description="Mask variants that could not be generated. Enrollment still succeeds as long "
        "as the UNMASKED template was created (docs/design.md).",
    )


class ComponentStatusOut(ApiModel):
    name: str
    configured: bool
    adapter: str
    detail: str


class ThresholdsOut(ApiModel):
    match_threshold: float | None
    review_threshold: float | None
    minimum_margin: float | None
    calibrated: bool = Field(
        description="False until all three are set. While false the API can only return "
        "HUMAN_REVIEW/UNKNOWN and never marks attendance automatically."
    )


class ModelsResponse(ApiModel):
    components: list[ComponentStatusOut]
    thresholds: ThresholdsOut
    embedding_dim: int
    mask_variants: list[str]
    recognition_ready: bool
