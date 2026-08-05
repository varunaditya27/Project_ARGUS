"""MATCH / HUMAN_REVIEW / UNKNOWN decision layer (docs/design.md).

Pure functions, no I/O, so the policy is unit-testable on its own.

Two invariants:

* Nearest neighbour never implies MATCH -- Chroma always returns the closest
  vector, including for a stranger.
* While the thresholds are uncalibrated (``null`` in docs/design.md) the layer
  cannot return MATCH at all. Attendance therefore stays empty rather than being
  populated from guessed thresholds.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.domain.enums import DecisionState
from app.recognition.ports import TemplateMatch


@dataclass(frozen=True, slots=True)
class Thresholds:
    match: float | None
    review: float | None
    minimum_margin: float | None

    @property
    def calibrated(self) -> bool:
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
    second_best_similarity: float | None = None
    margin: float | None = None
    matched_template: str | None = None
    candidates: Sequence[Candidate] = field(default_factory=tuple)

    @property
    def is_match(self) -> bool:
        return self.state is DecisionState.MATCH


def rank_identities(matches: Iterable[TemplateMatch]) -> list[Candidate]:
    """Collapse template hits to identities: an identity scores as its best template."""
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
    matches: Iterable[TemplateMatch],
    thresholds: Thresholds,
    *,
    quality_note: str | None = None,
) -> Decision:
    """Apply the documented decision policy to one probe's neighbours."""
    candidates = rank_identities(matches)
    if not candidates:
        return Decision(
            state=DecisionState.UNKNOWN,
            reason="No enrolled template was returned for this probe.",
        )

    best = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    second = runner_up.similarity if runner_up else None
    # With a single competing identity there is no margin to compute; the
    # threshold check is then carried entirely by the similarity score.
    margin = None if second is None else best.similarity - second

    common = {
        "student_id": best.student_id,
        "similarity": best.similarity,
        "second_best_similarity": second,
        "margin": margin,
        "matched_template": best.template_type,
        "candidates": tuple(candidates),
    }

    if not thresholds.calibrated:
        return Decision(
            state=DecisionState.HUMAN_REVIEW,
            reason=(
                "Recognition thresholds are not calibrated yet "
                "(ARGUS_MATCH_THRESHOLD / ARGUS_REVIEW_THRESHOLD / ARGUS_MINIMUM_MARGIN)."
            ),
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
    # review <= match is enforced by Settings, so anything at or above the review
    # threshold that did not MATCH is either margin-blocked or score-blocked.
    if best.similarity >= thresholds.review:
        reason = (
            "Best identity is too close to the runner-up."
            if not margin_ok
            else "Similarity reached the review threshold but not the match threshold."
        )
        return Decision(state=DecisionState.HUMAN_REVIEW, reason=reason, **common)
    return Decision(
        state=DecisionState.UNKNOWN,
        reason="No enrolled identity reached the review threshold.",
        **common,
    )
