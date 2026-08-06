"""Offline attendance runs over a recorded video or an archive of stills.

Both inputs are replayed through the ordinary capture buffer, so absence is
still derived once, at session close, and never inferred from a batch run.
Observations are merged in memory first, so a 5 000 frame video hands the
attendance layer one entry per student instead of one per frame.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from app.core.archives import SafeZipArchive
from app.core.config import Settings
from app.core.errors import InvalidRequestError, PayloadTooLargeError
from app.core.utils import to_naive_utc, utc_now
from app.domain import DecisionState, Observation
from app.recognition.alignment import decode_image
from app.recognition.ports import Image
from app.schemas.recognition import OfflineRunResult
from app.services.attendance import AttendanceService
from app.services.frames import observations_from
from app.services.recognition import RecognitionService
from app.services.video import sample_frames

#: Image types accepted inside an archive.
_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})


class _Run:
    """Counters and merged observations for one offline run."""

    def __init__(self) -> None:
        self.processed = 0
        self.skipped = 0
        self.faces = 0
        self.states: dict[DecisionState, int] = dict.fromkeys(DecisionState, 0)
        self._observations: dict[uuid.UUID, Observation] = {}

    def record(self, states: list[DecisionState], observations: list[Observation]) -> None:
        # Fold one image or frame into the totals.
        self.processed += 1
        self.faces += len(states)
        for state in states:
            self.states[state] += 1
        for observation in observations:
            existing = self._observations.get(observation.student_id)
            self._observations[observation.student_id] = (
                observation if existing is None else existing.merge(observation)
            )

    def observations(self) -> list[Observation]:
        # One entry per distinct student seen during the run.
        return list(self._observations.values())


class OfflineRecognitionService:
    def __init__(
        self,
        *,
        recognition: RecognitionService,
        attendance: AttendanceService,
        settings: Settings,
    ) -> None:
        self._recognition = recognition
        self._attendance = attendance
        self._settings = settings

    async def run_archive(
        self, payload: bytes, *, session_id: uuid.UUID | None, recorded_at: dt.datetime | None
    ) -> OfflineRunResult:
        # Recognise every still image inside an uploaded ZIP.
        run = _Run()
        archive = SafeZipArchive.open(
            payload,
            max_total_bytes=self._settings.batch_max_archive_bytes,
            max_entry_bytes=self._settings.recognition_max_frame_bytes,
            max_files=self._settings.batch_max_files,
            suffixes=_SUFFIXES,
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
                    run.skipped += 1
                    continue
                await self._process(image, base or utc_now(), run)
        finally:
            archive.close()
        return await self._finish(run, session_id)

    async def run_video(
        self, payload: bytes, *, session_id: uuid.UUID | None, recorded_at: dt.datetime | None
    ) -> OfflineRunResult:
        # Sample every Nth frame. With recorded_at each frame is timestamped at
        # recorded_at + frame_index / fps, so the register reflects the recording
        # rather than the moment the file was uploaded.
        if not payload:
            raise InvalidRequestError("The uploaded video is empty.")
        if len(payload) > self._settings.video_max_bytes:
            raise PayloadTooLargeError(
                "The uploaded video is too large.",
                details={"max_bytes": self._settings.video_max_bytes},
            )

        run = _Run()
        base = to_naive_utc(recorded_at) if recorded_at else None
        frames = sample_frames(
            payload,
            stride=self._settings.video_frame_stride,
            max_frames=self._settings.video_max_frames,
        )
        async for index, frame, fps in frames:
            at = base + dt.timedelta(seconds=index / fps) if base else utc_now()
            await self._process(frame, at, run)
        return await self._finish(run, session_id)

    async def _process(self, image: Image, at: dt.datetime, run: _Run) -> None:
        # Recognise one image and fold the result into the run.
        analysed = await self._recognition.analyse(image)
        run.record([decision.state for _, decision in analysed], observations_from(analysed, at))

    async def _finish(self, run: _Run, session_id: uuid.UUID | None) -> OfflineRunResult:
        # Hand the merged observations to the ordinary capture buffer, once.
        observations = run.observations()
        if session_id is not None and observations:
            await self._attendance.record(session_id, observations)
        return OfflineRunResult(
            session_id=session_id,
            processed=run.processed,
            skipped=run.skipped,
            faces_detected=run.faces,
            matched=run.states[DecisionState.MATCH],
            human_review=run.states[DecisionState.HUMAN_REVIEW],
            unknown=run.states[DecisionState.UNKNOWN],
            attendance_observations=len(observations) if session_id is not None else 0,
        )
