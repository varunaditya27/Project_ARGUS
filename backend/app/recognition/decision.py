"""MATCH / HUMAN_REVIEW / UNKNOWN policy.

Pure functions, no I/O. Two invariants: the nearest neighbour never implies a
match, because the index always returns the closest vector even for a stranger;
and while the thresholds are uncalibrated the layer cannot return MATCH at all,
so attendance stays empty rather than being filled from guessed numbers.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain import DecisionState
from app.recognition.ports import TemplateMatch


@dataclass(frozen=True, slots=True)
class Thresholds:
    match: float | None
    review: float | None
    minimum_margin: float | None

    @property
    def calibrated(self) -> bool:
        # All three must be set before an automatic match is possible.
        return None not in (self.match, self.review, self.minimum_margin)


@dataclass(frozen=True, slots=True)
class Candidate:
    student_id: uuid.UUID
    similarity: float
    template_type: str


@dataclass(frozen=True, slots=True)
class Decision:
    state: DecisionState
    reason: str
    student_id: uuid.UUID | None = None
    similarity: float | None = None

    @property
    def is_match(self) -> bool:
        # Only a MATCH may write attendance.
        return self.state is DecisionState.MATCH


def rank_identities(matches: Iterable[TemplateMatch]) -> list[Candidate]:
    # Collapse template hits to identities: an identity scores as its best template.
    best: dict[uuid.UUID, Candidate] = {}
    for match in matches:
        current = best.get(match.student_id)
        if current is None or match.similarity > current.similarity:
            best[match.student_id] = Candidate(
                student_id=match.student_id,
                similarity=match.similarity,
                template_type=match.template_type,
            )
    return sorted(best.values(), key=lambda c: c.similarity, reverse=True)


def decide(
    matches: Iterable[TemplateMatch], thresholds: Thresholds, *, quality_note: str | None = None
) -> Decision:
    # Apply the documented policy to one probe's neighbours.
    candidates = rank_identities(matches)
    if not candidates:
        return Decision(
            state=DecisionState.UNKNOWN,
            reason="No enrolled template was returned for this probe.",
        )

    best = candidates[0]
    second = candidates[1].similarity if len(candidates) > 1 else None
    # With a single competing identity there is no margin, so the similarity
    # threshold carries the decision on its own.
    margin = None if second is None else best.similarity - second
    common = {"student_id": best.student_id, "similarity": best.similarity}

    if not thresholds.calibrated:
        return Decision(
            state=DecisionState.HUMAN_REVIEW,
            reason="Recognition thresholds are not calibrated yet.",
            **common,
        )
    assert thresholds.match is not None
    assert thresholds.review is not None
    assert thresholds.minimum_margin is not None

    if quality_note is not None:
        return Decision(state=DecisionState.HUMAN_REVIEW, reason=quality_note, **common)

    margin_ok = margin is None or margin >= thresholds.minimum_margin
    if best.similarity >= thresholds.match and margin_ok:
        return Decision(
            state=DecisionState.MATCH,
            reason="Similarity and identity margin passed the calibrated thresholds.",
            **common,
        )
    if best.similarity >= thresholds.review:
        return Decision(
            state=DecisionState.HUMAN_REVIEW,
            reason=(
                "Best identity is too close to the runner-up."
                if not margin_ok
                else "Similarity reached the review threshold but not the match threshold."
            ),
            **common,
        )
    return Decision(
        state=DecisionState.UNKNOWN,
        reason="No enrolled identity reached the review threshold.",
        **common,
    )
