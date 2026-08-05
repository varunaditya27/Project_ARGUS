"""Enrollment and live recognition orchestration.

Every model call goes through :mod:`app.recognition.ports`. While the SCRFD /
ArcFace / MaskTheFace adapters are placeholders these endpoints fail with 503 and
an explicit reason - they never fabricate a face, an embedding or a similarity.

The only path that can write attendance is a MATCH, which in turn requires
calibrated thresholds, so an uncalibrated deployment records nothing instead of
recording something wrong.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

import numpy as np

from app.core.clock import utc_now
from app.core.config import Settings
from app.core.errors import InvalidRequestError, PayloadTooLargeError
from app.core.logging import get_logger
from app.domain.enums import UNMASKED_TEMPLATE
from app.domain.observation import Observation
from app.recognition.alignment import align_face, blur_variance, decode_image
from app.recognition.decision import Decision, decide
from app.recognition.factory import RecognitionStack
from app.recognition.ports import DetectedFace, Image
from app.schemas.recognition import (
    CandidateOut,
    EnrollmentResult,
    FaceDecisionOut,
    FrameResult,
)
from app.services.attendance import AttendanceService
from app.services.student import StudentService

logger = get_logger(__name__)


class RecognitionService:
    def __init__(
        self,
        *,
        stack: RecognitionStack,
        settings: Settings,
        students: StudentService,
        attendance: AttendanceService,
    ) -> None:
        self._stack = stack
        self._settings = settings
        self._students = students
        self._attendance = attendance

    # -------------------------------------------------------------- enrollment
    async def enroll(self, student_id: uuid.UUID, payload: bytes) -> EnrollmentResult:
        """Create the unmasked template plus the synthetic masked variants."""
        student = await self._students.get(student_id)
        image = self._decode(payload, self._settings.enrollment_max_image_bytes)

        faces = self._stack.detector.detect(image)
        if not faces:
            raise InvalidRequestError("No face was detected in the enrollment image.")
        if len(faces) > 1:
            raise InvalidRequestError(
                "The enrollment image must contain exactly one face.",
                details={"faces_detected": len(faces)},
            )

        face = faces[0]
        self._enforce_quality(face)
        aligned = align_face(image, face.landmarks)

        variants: dict[str, Image] = {UNMASKED_TEMPLATE: aligned}
        failed: list[str] = []
        try:
            synthesized = self._stack.mask_synthesizer.synthesize(aligned)
        except Exception:
            logger.exception("Mask synthesis failed for student %s", student_id)
            synthesized = {}
        for variant in self._stack.mask_variants:
            masked = synthesized.get(variant)
            if masked is None:
                failed.append(variant)
            else:
                variants[variant] = masked

        embeddings = self._stack.embedder.embed(list(variants.values()))
        templates = {
            name: np.asarray(embeddings[position], dtype=np.float32)
            for position, name in enumerate(variants)
        }
        stored = await self._stack.index.upsert(
            student.student_id, templates, model_version=self._stack.model_version
        )
        return EnrollmentResult(
            student_id=student.student_id,
            templates_stored=stored,
            stored_variants=list(templates),
            failed_variants=failed,
        )

    async def list_templates(self, student_id: uuid.UUID) -> list[str]:
        student = await self._students.get(student_id)
        return await self._stack.index.list_templates(student.student_id)

    # ------------------------------------------------------------- recognition
    async def recognize(
        self,
        payload: bytes,
        *,
        session_id: uuid.UUID | None,
        frame_id: str,
        request_id: str | None = None,
    ) -> FrameResult:
        started = time.perf_counter()
        image = self._decode(payload, self._settings.recognition_max_frame_bytes)

        faces = self._stack.detector.detect(image)
        decisions = await self._decide_faces(image, faces)

        # One instant for the whole frame: every face in it was seen together.
        observed_at = utc_now()
        observations = [
            Observation(
                student_id=decision.student_id,
                confidence=decision.similarity if decision.similarity is not None else 0.0,
                observed_at=observed_at,
            )
            for decision in decisions
            if decision.is_match and decision.student_id is not None
        ]
        recorded: set[uuid.UUID] = set()
        if session_id is not None and observations:
            await self._attendance.record(session_id, observations)
            recorded = {observation.student_id for observation in observations}

        return FrameResult(
            request_id=request_id or f"req-{uuid.uuid4().hex[:12]}",
            frame_id=frame_id,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            session_id=session_id,
            faces=[
                self._to_wire(face, decision, decision.student_id in recorded)
                for face, decision in zip(faces, decisions, strict=True)
            ],
        )

    async def _decide_faces(self, image: Image, faces: Sequence[DetectedFace]) -> list[Decision]:
        """One embedding batch and one index query for the whole frame."""
        if not faces:
            return []
        crops = [align_face(image, face.landmarks) for face in faces]
        embeddings = self._stack.embedder.embed(crops)
        neighbours = await self._stack.index.search(embeddings, self._settings.chroma_search_k)
        return [
            decide(
                matches,
                self._stack.thresholds,
                quality_note=self._quality_note(face, crop),
            )
            for face, crop, matches in zip(faces, crops, neighbours, strict=True)
        ]

    # ------------------------------------------------------------------ helpers
    def _decode(self, payload: bytes, max_bytes: int) -> Image:
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
            raise InvalidRequestError(
                "The uploaded file could not be decoded as a JPEG/PNG image."
            ) from exc

    def _enforce_quality(self, face: DetectedFace) -> None:
        """Enrollment-time gates. Uncalibrated gates are skipped, not guessed."""
        minimum = self._settings.enrollment_min_face_pixels
        if minimum is not None and min(face.width, face.height) < minimum:
            raise InvalidRequestError(
                "The detected face is too small; please submit a closer image.",
                details={"min_face_pixels": minimum, "face_size": [face.width, face.height]},
            )

    def _quality_note(self, face: DetectedFace, aligned: Image) -> str | None:
        """Reason to force HUMAN_REVIEW for a low quality probe, or None."""
        minimum = self._settings.enrollment_min_face_pixels
        if minimum is not None and min(face.width, face.height) < minimum:
            return "The detected face is too small for a reliable automatic decision."
        blur_gate = self._settings.enrollment_min_blur_variance
        if blur_gate is not None and blur_variance(aligned) < blur_gate:
            return "The detected face is too blurred for a reliable automatic decision."
        return None

    @staticmethod
    def _to_wire(face: DetectedFace, decision: Decision, recorded: bool) -> FaceDecisionOut:
        return FaceDecisionOut(
            bbox=face.bbox,
            detection_score=face.detection_score,
            state=decision.state,
            student_id=decision.student_id,
            similarity=decision.similarity,
            second_best_similarity=decision.second_best_similarity,
            margin=decision.margin,
            matched_template=decision.matched_template,
            reason=decision.reason,
            attendance_recorded=recorded,
            candidates=[
                CandidateOut(
                    student_id=candidate.student_id,
                    similarity=candidate.similarity,
                    matched_template=candidate.template_type,
                )
                for candidate in decision.candidates
            ],
        )

    @property
    def stack(self) -> RecognitionStack:
        return self._stack
