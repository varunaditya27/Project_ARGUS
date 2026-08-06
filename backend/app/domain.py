"""Vocabulary shared by the database layer, services and API schemas.

The string values are the literals documented in docs/db.md and are what lands
in the TEXT status columns.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class AttendanceStatus(StrEnum):
    PRESENT = "Present"
    ABSENT = "Absent"


class DecisionState(StrEnum):
    MATCH = "MATCH"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    UNKNOWN = "UNKNOWN"


#: attendance.confidence is NOT NULL, so rows written by the absence pass - which
#: involve no recognition - carry this sentinel.
ABSENT_CONFIDENCE: Final[float] = 0.0

#: Template label of the unmasked enrollment embedding.
UNMASKED_TEMPLATE: Final[str] = "UNMASKED"


@dataclass(frozen=True, slots=True)
class Observation:
    """One accepted recognition of one student inside an active session."""

    student_id: uuid.UUID
    confidence: float
    observed_at: dt.datetime

    def merge(self, other: Observation) -> Observation:
        # Same rule as the ON CONFLICT clause: strongest score, earliest sighting.
        return Observation(
            student_id=self.student_id,
            confidence=max(self.confidence, other.confidence),
            observed_at=min(self.observed_at, other.observed_at),
        )
