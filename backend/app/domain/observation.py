"""The unit of evidence that flows from recognition into attendance."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Observation:
    """One accepted recognition of one student inside an active session.

    Many observations of the same student are coalesced before they reach
    PostgreSQL (highest confidence wins, earliest timestamp is kept), so the
    ``attendance`` row stays a single row per ``(session_id, student_id)`` exactly
    as ``docs/db.md`` requires.
    """

    student_id: uuid.UUID
    confidence: float
    observed_at: dt.datetime

    def merge(self, other: Observation) -> Observation:
        return Observation(
            student_id=self.student_id,
            confidence=max(self.confidence, other.confidence),
            observed_at=min(self.observed_at, other.observed_at),
        )
