"""Recognition wire format."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.domain import DecisionState
from app.schemas.common import ApiModel


class FaceDecision(ApiModel):
    bbox: tuple[int, int, int, int]
    detection_score: float = Field(ge=0.0, le=1.0)
    state: DecisionState
    student_id: uuid.UUID | None = None
    similarity: float | None = None
    reason: str
    #: True when this decision was buffered as an attendance observation.
    attendance_recorded: bool = False


class FrameResult(ApiModel):
    frame_id: str
    session_id: uuid.UUID | None = None
    faces: list[FaceDecision]


class OfflineRunResult(ApiModel):
    """Outcome of a run over a recorded video or an archive of stills."""

    session_id: uuid.UUID | None = None
    processed: int
    skipped: int
    faces_detected: int
    matched: int
    human_review: int
    unknown: int
    #: Distinct students handed to the capture buffer. Absence is still only
    #: computed when the session is closed.
    attendance_observations: int


class EnrollmentResult(ApiModel):
    student_id: uuid.UUID
    templates_stored: int
    stored_variants: list[str]


class ComponentStatusOut(ApiModel):
    name: str
    configured: bool
    detail: str


class ThresholdsOut(ApiModel):
    match_threshold: float | None
    review_threshold: float | None
    minimum_margin: float | None


class ModelsResponse(ApiModel):
    components: list[ComponentStatusOut]
    thresholds: ThresholdsOut
    #: False while any component or threshold is missing; the API then never
    #: marks attendance automatically.
    recognition_ready: bool
