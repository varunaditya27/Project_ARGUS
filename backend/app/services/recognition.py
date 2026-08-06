"""Enrollment and single-frame recognition.

Every model call goes through app.recognition.ports and every one of them is
pushed onto a worker thread, because onnxruntime inference is CPU-bound and would
otherwise block the event loop for the whole frame.

The only path that can write attendance is a MATCH, which requires calibrated
thresholds, so an uncalibrated deployment records nothing rather than something
wrong.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

import numpy as np

from app.core.config import Settings
from app.core.errors import InvalidRequestError
from app.core.logging import get_logger
from app.core.utils import utc_now
from app.domain import UNMASKED_TEMPLATE
from app.recognition.alignment import align_face
from app.recognition.decision import decide
from app.recognition.ports import DetectedFace, Image
from app.recognition.stack import RecognitionStack
from app.schemas.recognition import EnrollmentResult, FaceDecision, FrameResult
from app.services.attendance import AttendanceService
from app.services.frames import (
    Analysed,
    decode_upload,
    enforce_quality,
    observations_from,
    quality_note,
)
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

    async def enroll(self, student_id: uuid.UUID, payload: bytes) -> EnrollmentResult:
        # Build the unmasked template plus every synthetic masked variant.
        student = await self._students.get(student_id)
        image = decode_upload(payload, self._settings.enrollment_max_image_bytes)

        faces = await self._detect(image)
        if len(faces) != 1:
            raise InvalidRequestError(
                "The enrollment image must contain exactly one face.",
                details={"faces_detected": len(faces)},
            )
        enforce_quality(faces[0], self._settings)
        aligned = align_face(image, faces[0].landmarks)

        variants: dict[str, Image] = {UNMASKED_TEMPLATE: aligned}
        try:
            synthesized = await asyncio.to_thread(self._stack.mask_synthesizer.synthesize, aligned)
        except Exception:
            # Partial or total mask failure is tolerated: the unmasked template
            # alone is still a valid enrollment.
            logger.exception("Mask synthesis failed for student %s", student_id)
            synthesized = {}
        variants.update(synthesized)

        embeddings = await self._embed(list(variants.values()))
        templates = {
            name: np.asarray(embeddings[position], dtype=np.float32)
            for position, name in enumerate(variants)
        }
        stored = await self._stack.template_index.upsert(
            student.student_id, templates, model_version=self._stack.model_version
        )
        return EnrollmentResult(
            student_id=student.student_id, templates_stored=stored, stored_variants=list(templates)
        )

    async def list_templates(self, student_id: uuid.UUID) -> list[str]:
        # Which mask variants are enrolled for this student.
        student = await self._students.get(student_id)
        return await self._stack.template_index.list_templates(student.student_id)

    async def recognize(
        self, payload: bytes, *, session_id: uuid.UUID | None, frame_id: str
    ) -> FrameResult:
        # Recognise one frame and, for an ACTIVE session, buffer the matches.
        image = decode_upload(payload, self._settings.recognition_max_frame_bytes)
        analysed = await self.analyse(image)

        # One instant for the whole frame: every face in it was seen together.
        observations = observations_from(analysed, utc_now())
        recorded: set[uuid.UUID] = set()
        if session_id is not None and observations:
            await self._attendance.record(session_id, observations)
            recorded = {observation.student_id for observation in observations}

        return FrameResult(
            frame_id=frame_id,
            session_id=session_id,
            faces=[
                FaceDecision(
                    bbox=face.bbox,
                    detection_score=face.detection_score,
                    state=decision.state,
                    student_id=decision.student_id,
                    similarity=decision.similarity,
                    reason=decision.reason,
                    attendance_recorded=decision.student_id in recorded,
                )
                for face, decision in analysed
            ],
        )

    async def analyse(self, image: Image) -> Analysed:
        # Detect, align, embed and decide with one embedding batch and one index
        # query for the whole frame.
        faces = await self._detect(image)
        if not faces:
            return []
        crops = await asyncio.to_thread(
            lambda: [align_face(image, face.landmarks) for face in faces]
        )
        embeddings = await self._embed(crops)
        neighbours = await self._stack.template_index.search(
            embeddings, self._settings.chroma_search_k
        )
        return [
            (
                face,
                decide(
                    matches,
                    self._stack.thresholds,
                    quality_note=quality_note(face, crop, self._settings),
                ),
            )
            for face, crop, matches in zip(faces, crops, neighbours, strict=True)
        ]

    async def _detect(self, image: Image) -> list[DetectedFace]:
        # Inference off the event loop.
        return await asyncio.to_thread(self._stack.face_detector.detect, image)

    async def _embed(self, crops: Sequence[Image]):
        # Inference off the event loop.
        return await asyncio.to_thread(self._stack.face_embedder.embed, crops)
