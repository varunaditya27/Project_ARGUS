"""Enrollment and recognition orchestration.

Every model call goes through :mod:`app.recognition.ports`, and every one of them
is pushed onto a worker thread: onnxruntime inference is CPU-bound and would
otherwise block the event loop for the whole frame.

Four input shapes feed the same core (detect -> align -> embed -> search ->
decide -> observe): a single still, a live WebSocket stream, a recorded video and
an archive of stills. Offline inputs are replayed through the ordinary capture
buffer, so absence is still derived once, at session close, and never inferred
from a batch run.

The only path that can write attendance is a MATCH, which requires calibrated
thresholds, so an uncalibrated deployment records nothing instead of recording
something wrong.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import tempfile
import time
import uuid
from collections.abc import Sequence

import numpy as np

from app.core.archives import SafeZipArchive
from app.core.clock import to_naive_utc, utc_now
from app.core.config import Settings
from app.core.errors import InvalidRequestError, PayloadTooLargeError
from app.core.logging import get_logger
from app.domain.enums import UNMASKED_TEMPLATE, DecisionState
from app.domain.observation import Observation
from app.recognition.alignment import align_face, blur_variance, decode_image, require_cv2
from app.recognition.decision import Decision, decide
from app.recognition.factory import RecognitionStack
from app.recognition.ports import DetectedFace, Image
from app.schemas.recognition import (
    BatchItemResult,
    BatchRecognitionResult,
    CandidateOut,
    EnrollmentResult,
    FaceDecisionOut,
    FrameResult,
)
from app.services.attendance import AttendanceService
from app.services.student import StudentService

logger = get_logger(__name__)

#: Image types accepted inside a batch archive.
_BATCH_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
#: Sampled frames decoded per thread hop while walking a video.
_VIDEO_CHUNK = 8
#: Cap on the per-item detail returned for an offline run.
_MAX_REPORTED_ITEMS = 1_000


class _OfflineRun:
    """Accumulates a video/archive run.

    Observations are merged in memory first (same rule as the capture buffer:
    strongest confidence, earliest sighting) so a 5 000 frame video hands the
    attendance layer one entry per student instead of one per frame.
    """

    def __init__(self) -> None:
        self.processed = 0
        self.skipped_count = 0
        self.faces = 0
        self.matched = 0
        self.review = 0
        self.unknown = 0
        self.truncated = False
        self.items: list[BatchItemResult] = []
        self._observations: dict[uuid.UUID, Observation] = {}

    def observe(self, observation: Observation) -> None:
        existing = self._observations.get(observation.student_id)
        self._observations[observation.student_id] = (
            observation if existing is None else existing.merge(observation)
        )

    def observations(self) -> list[Observation]:
        return list(self._observations.values())

    def record(self, source: str, decisions: Sequence[Decision]) -> None:
        self.processed += 1
        self.faces += len(decisions)
        states = [decision.state for decision in decisions]
        matched = states.count(DecisionState.MATCH)
        review = states.count(DecisionState.HUMAN_REVIEW)
        unknown = states.count(DecisionState.UNKNOWN)
        self.matched += matched
        self.review += review
        self.unknown += unknown
        self._append(
            BatchItemResult(
                source=source,
                faces=len(decisions),
                matched=matched,
                human_review=review,
                unknown=unknown,
            )
        )

    def skip(self, source: str, reason: str) -> None:
        self.skipped_count += 1
        self._append(BatchItemResult(source=source, error=reason))

    def _append(self, item: BatchItemResult) -> None:
        if len(self.items) < _MAX_REPORTED_ITEMS:
            self.items.append(item)
        else:
            self.truncated = True


class _VideoReader:
    """Sequential frame reader.

    Frames are read in order rather than seeked to: ``CAP_PROP_POS_FRAMES`` is
    unreliable on compressed formats, and sequential decoding is what the codec
    is optimised for anyway.
    """

    def __init__(self, capture, fps: float) -> None:
        self._capture = capture
        self._index = -1
        self.fps = fps

    @classmethod
    def open(cls, path: str) -> _VideoReader:
        cv2 = require_cv2()
        capture = cv2.VideoCapture(path)
        if not capture.isOpened():
            capture.release()
            raise InvalidRequestError(
                "The uploaded video could not be opened. Supported containers depend on the "
                "OpenCV build (MP4/AVI/MKV are typical)."
            )
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        # A malformed header can report 0 or NaN; fall back to a nominal rate so
        # frame timestamps stay monotonic instead of dividing by zero.
        if not fps or fps != fps or fps <= 0:
            fps = 25.0
        return cls(capture, fps)

    def read_chunk(self, stride: int, limit: int) -> list[tuple[int, Image]]:
        frames: list[tuple[int, Image]] = []
        while len(frames) < limit:
            ok, frame = self._capture.read()
            if not ok:
                break
            self._index += 1
            if self._index % stride == 0:
                frames.append((self._index, frame))
        return frames

    def release(self) -> None:
        self._capture.release()


def _write_temp_video(payload: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix="argus-video-", suffix=".bin", delete=False) as handle:
        handle.write(payload)
        return handle.name


def _remove_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:  # pragma: no cover - best effort cleanup
        logger.warning("Could not delete temporary video %s", path)


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

        faces = await self._detect(image)
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
            synthesized = await asyncio.to_thread(self._stack.mask_synthesizer.synthesize, aligned)
        except Exception:
            # Mask synthesis is allowed to fail partially or completely; the
            # unmasked template alone still makes a valid enrollment.
            logger.exception("Mask synthesis failed for student %s", student_id)
            synthesized = {}
        for variant in self._stack.mask_variants:
            masked = synthesized.get(variant)
            if masked is None:
                failed.append(variant)
            else:
                variants[variant] = masked

        embeddings = await self._embed(list(variants.values()))
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

        faces = await self._detect(image)
        decisions = await self._decide_faces(image, faces)

        # One instant for the whole frame: every face in it was seen together.
        observations = self._observations(decisions, utc_now())
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
        crops = await asyncio.to_thread(
            lambda: [align_face(image, face.landmarks) for face in faces]
        )
        embeddings = await self._embed(crops)
        neighbours = await self._stack.index.search(embeddings, self._settings.chroma_search_k)
        return [
            decide(
                matches,
                self._stack.thresholds,
                quality_note=self._quality_note(face, crop),
            )
            for face, crop, matches in zip(faces, crops, neighbours, strict=True)
        ]

    # -------------------------------------------------------------- offline runs
    async def recognize_batch(
        self,
        payload: bytes,
        *,
        session_id: uuid.UUID | None,
        recorded_at: dt.datetime | None = None,
    ) -> BatchRecognitionResult:
        """Recognise every still image inside an uploaded ZIP archive."""
        started = time.perf_counter()
        run = _OfflineRun()
        archive = SafeZipArchive.open(
            payload,
            max_total_bytes=self._settings.batch_max_archive_bytes,
            max_entry_bytes=self._settings.recognition_max_frame_bytes,
            max_files=self._settings.batch_max_files,
            suffixes=_BATCH_SUFFIXES,
        )
        base = to_naive_utc(recorded_at) if recorded_at else None
        try:
            entries = archive.iter_entries()
            while True:
                # Decompression is blocking work; pull one entry per thread hop.
                entry = await asyncio.to_thread(next, entries, None)
                if entry is None:
                    break
                try:
                    image = decode_image(entry.payload)
                except ValueError:
                    run.skip(entry.filename, "not a decodable image")
                    continue
                await self._process_offline(image, entry.filename, base or utc_now(), run)
        finally:
            archive.close()

        return await self._finish_offline(run, session_id, started)

    async def recognize_video(
        self,
        payload: bytes,
        *,
        session_id: uuid.UUID | None,
        recorded_at: dt.datetime | None = None,
    ) -> BatchRecognitionResult:
        """Recognise a recorded video, sampling every Nth frame.

        When ``recorded_at`` is given, each sampled frame is timestamped at
        ``recorded_at + frame_index / fps`` so the attendance register reflects
        when a student actually appeared in the recording rather than when the
        file happened to be uploaded.
        """
        if not payload:
            raise InvalidRequestError("The uploaded video is empty.")
        if len(payload) > self._settings.video_max_bytes:
            raise PayloadTooLargeError(
                "The uploaded video is too large.",
                details={
                    "max_bytes": self._settings.video_max_bytes,
                    "received_bytes": len(payload),
                },
            )

        started = time.perf_counter()
        run = _OfflineRun()
        base = to_naive_utc(recorded_at) if recorded_at else None
        path = await asyncio.to_thread(_write_temp_video, payload)
        try:
            reader = await asyncio.to_thread(_VideoReader.open, path)
            try:
                remaining = self._settings.video_max_frames
                while remaining > 0:
                    chunk = await asyncio.to_thread(
                        reader.read_chunk,
                        self._settings.video_frame_stride,
                        min(_VIDEO_CHUNK, remaining),
                    )
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    for index, frame in chunk:
                        at = base + dt.timedelta(seconds=index / reader.fps) if base else utc_now()
                        await self._process_offline(frame, f"frame-{index:06d}", at, run)
            finally:
                await asyncio.to_thread(reader.release)
        finally:
            await asyncio.to_thread(_remove_quietly, path)

        return await self._finish_offline(run, session_id, started)

    async def _process_offline(
        self, image: Image, source: str, at: dt.datetime, run: _OfflineRun
    ) -> None:
        faces = await self._detect(image)
        decisions = await self._decide_faces(image, faces)
        for observation in self._observations(decisions, at):
            run.observe(observation)
        run.record(source, decisions)

    async def _finish_offline(
        self, run: _OfflineRun, session_id: uuid.UUID | None, started: float
    ) -> BatchRecognitionResult:
        """Hand the run's observations to the ordinary capture buffer, once."""
        observations = run.observations()
        if session_id is not None and observations:
            await self._attendance.record(session_id, observations)
        return BatchRecognitionResult(
            request_id=f"req-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            processed=run.processed,
            skipped=run.skipped_count,
            faces_detected=run.faces,
            matched=run.matched,
            human_review=run.review,
            unknown=run.unknown,
            attendance_observations=len(observations) if session_id is not None else 0,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            items=run.items,
            items_truncated=run.truncated,
        )

    # ------------------------------------------------------------------ helpers
    async def _detect(self, image: Image) -> list[DetectedFace]:
        return await asyncio.to_thread(self._stack.detector.detect, image)

    async def _embed(self, crops: Sequence[Image]):
        return await asyncio.to_thread(self._stack.embedder.embed, crops)

    @staticmethod
    def _observations(decisions: Sequence[Decision], observed_at: dt.datetime) -> list[Observation]:
        return [
            Observation(
                student_id=decision.student_id,
                confidence=decision.similarity if decision.similarity is not None else 0.0,
                observed_at=observed_at,
            )
            for decision in decisions
            if decision.is_match and decision.student_id is not None
        ]

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
