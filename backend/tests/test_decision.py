"""Decision policy tests (docs/design.md -> Decision Logic)."""

from __future__ import annotations

import uuid

import pytest

from app.domain.enums import DecisionState
from app.recognition.decision import Thresholds, decide, rank_identities
from app.recognition.ports import TemplateMatch

RAYYAN = uuid.UUID("11111111-1111-1111-1111-111111111111")
VARUN = uuid.UUID("22222222-2222-2222-2222-222222222222")

CALIBRATED = Thresholds(match=0.65, review=0.45, minimum_margin=0.08)
UNCALIBRATED = Thresholds(match=None, review=None, minimum_margin=None)


def match(student_id: uuid.UUID, template: str, similarity: float) -> TemplateMatch:
    return TemplateMatch(student_id=student_id, template_type=template, similarity=similarity)


def test_identity_scores_as_its_best_template() -> None:
    ranked = rank_identities(
        [
            match(RAYYAN, "surgical_blue", 0.71),
            match(RAYYAN, "UNMASKED", 0.65),
            match(VARUN, "cloth_black", 0.57),
        ]
    )
    assert [(c.student_id, c.similarity, c.template_type) for c in ranked] == [
        (RAYYAN, 0.71, "surgical_blue"),
        (VARUN, 0.57, "cloth_black"),
    ]


def test_no_neighbours_is_unknown() -> None:
    decision = decide([], CALIBRATED)
    assert decision.state is DecisionState.UNKNOWN
    assert decision.student_id is None


def test_uncalibrated_thresholds_can_never_match() -> None:
    decision = decide([match(RAYYAN, "UNMASKED", 0.99)], UNCALIBRATED)
    assert decision.state is DecisionState.HUMAN_REVIEW
    assert "not calibrated" in decision.reason
    assert decision.student_id == RAYYAN


def test_match_requires_score_and_margin() -> None:
    decision = decide(
        [match(RAYYAN, "surgical_blue", 0.71), match(VARUN, "cloth_black", 0.57)], CALIBRATED
    )
    assert decision.state is DecisionState.MATCH
    assert decision.matched_template == "surgical_blue"
    assert decision.margin == pytest.approx(0.14)


def test_close_runner_up_forces_review() -> None:
    decision = decide([match(RAYYAN, "UNMASKED", 0.71), match(VARUN, "UNMASKED", 0.70)], CALIBRATED)
    assert decision.state is DecisionState.HUMAN_REVIEW
    assert "runner-up" in decision.reason


def test_between_review_and_match_is_review() -> None:
    decision = decide([match(RAYYAN, "UNMASKED", 0.50)], CALIBRATED)
    assert decision.state is DecisionState.HUMAN_REVIEW


def test_stranger_is_unknown_not_nearest_neighbour() -> None:
    decision = decide([match(RAYYAN, "UNMASKED", 0.31)], CALIBRATED)
    assert decision.state is DecisionState.UNKNOWN
    assert decision.student_id == RAYYAN  # reported as the best candidate, not as a match


def test_single_candidate_has_no_margin_to_fail() -> None:
    decision = decide([match(RAYYAN, "UNMASKED", 0.90)], CALIBRATED)
    assert decision.state is DecisionState.MATCH
    assert decision.margin is None
    assert decision.second_best_similarity is None


def test_quality_note_downgrades_a_would_be_match() -> None:
    decision = decide([match(RAYYAN, "UNMASKED", 0.90)], CALIBRATED, quality_note="face too small")
    assert decision.state is DecisionState.HUMAN_REVIEW
    assert decision.reason == "face too small"
