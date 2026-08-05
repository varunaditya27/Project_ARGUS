"""Domain vocabularies shared by the database layer, services and API schemas.

The string values are the exact literals documented in ``docs/db.md`` /
``docs/design.md`` and are what lands in the ``TEXT`` status columns.
"""

from __future__ import annotations

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


#: ``attendance.confidence`` is ``FLOAT NOT NULL`` in docs/db.md, so rows created
#: by the session-close absence pass (which involve no recognition at all) carry
#: this sentinel. See docs/database_setup.md -> "Schema mapping decisions".
ABSENT_CONFIDENCE: Final[float] = 0.0

#: Template label of the unmasked enrollment embedding (docs/design.md step 4).
UNMASKED_TEMPLATE: Final[str] = "UNMASKED"
