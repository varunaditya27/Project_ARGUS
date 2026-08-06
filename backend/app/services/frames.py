"""Frame-level helpers shared by the live and offline recognition paths.

Uploads are validated and decoded here, quality gates are applied here, and
matches are turned into attendance observations here, so the recognition service
itself only orchestrates the model calls.
"""

from __future__ import annotations

import datetime as dt

from app.core.config import Settings
from app.core.errors import InvalidRequestError, PayloadTooLargeError
from app.domain import Observation
from app.recognition.alignment import blur_variance, decode_image
from app.recognition.decision import Decision
from app.recognition.ports import DetectedFace, Image

#: One detected face and the decision taken about it.
Analysed = list[tuple[DetectedFace, Decision]]


def decode_upload(payload: bytes, max_bytes: int) -> Image:
    # Validate size then decode; a file is never trusted because of its name.
    if not payload:
        raise InvalidRequestError("The uploaded image is empty.")
    if len(payload) > max_bytes:
        raise PayloadTooLargeError(
            "The uploaded image is too large.",
            details={"max_bytes": max_bytes, "received_bytes": len(payload)},
        )
    try:
        return decode_image(payload)
    except ValueError as exc:
        raise InvalidRequestError("The upload could not be decoded as an image.") from exc


def observations_from(analysed: Analysed, observed_at: dt.datetime) -> list[Observation]:
    # Only matches become attendance evidence.
    return [
        Observation(
            student_id=decision.student_id,
            confidence=decision.similarity or 0.0,
            observed_at=observed_at,
        )
        for _, decision in analysed
        if decision.is_match and decision.student_id is not None
    ]


def enforce_quality(face: DetectedFace, settings: Settings) -> None:
    # Enrollment gate; an uncalibrated gate is skipped, never guessed.
    minimum = settings.enrollment_min_face_pixels
    if minimum is not None and min(face.width, face.height) < minimum:
        raise InvalidRequestError(
            "The detected face is too small; please submit a closer image.",
            details={"min_face_pixels": minimum},
        )


def quality_note(face: DetectedFace, aligned: Image, settings: Settings) -> str | None:
    # Reason to force HUMAN_REVIEW for a low quality probe, or None.
    minimum = settings.enrollment_min_face_pixels
    if minimum is not None and min(face.width, face.height) < minimum:
        return "The detected face is too small for a reliable automatic decision."
    blur_gate = settings.enrollment_min_blur_variance
    if blur_gate is not None and blur_variance(aligned) < blur_gate:
        return "The detected face is too blurred for a reliable automatic decision."
    return None
