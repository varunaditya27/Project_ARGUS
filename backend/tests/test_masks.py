"""Geometric mask synthesis (no ONNX model needed - it's pure drawing over a known frame)."""

from __future__ import annotations

import numpy as np

from app.recognition.adapters.masks import MASK_STYLES, GeometricMaskSynthesizer
from app.recognition.alignment import OUTPUT_SIZE


def aligned_face() -> np.ndarray:
    return np.full((OUTPUT_SIZE, OUTPUT_SIZE, 3), 200, dtype=np.uint8)


# checks synthesize() returns one rendered image per requested, recognized mask style
def test_synthesize_returns_one_image_per_requested_known_variant() -> None:
    synth = GeometricMaskSynthesizer(["surgical_blue", "n95"])
    variants = synth.synthesize(aligned_face())
    assert set(variants) == {"surgical_blue", "n95"}
    for image in variants.values():
        assert image.shape == (OUTPUT_SIZE, OUTPUT_SIZE, 3)


# checks a variant name not in MASK_STYLES is skipped instead of raising a KeyError
def test_unknown_variant_names_are_silently_dropped() -> None:
    synth = GeometricMaskSynthesizer(["surgical_blue", "not_a_real_mask"])
    variants = synth.synthesize(aligned_face())
    assert set(variants) == {"surgical_blue"}


def test_status_reports_unknown_variant_names() -> None:
    synth = GeometricMaskSynthesizer(["not_a_real_mask"])
    status = synth.status()
    assert status.configured is False
    assert "not_a_real_mask" in status.detail


def test_synthesize_is_deterministic_for_the_same_input() -> None:
    synth = GeometricMaskSynthesizer(["cloth_black"])
    face = aligned_face()
    first = synth.synthesize(face)["cloth_black"]
    second = synth.synthesize(face)["cloth_black"]
    np.testing.assert_array_equal(first, second)


def test_mask_covers_lower_face_and_leaves_top_rows_untouched() -> None:
    synth = GeometricMaskSynthesizer(["surgical_blue"])
    face = aligned_face()
    result = synth.synthesize(face)["surgical_blue"]
    # the top few rows are above every style's coverage area (eyes and forehead)
    np.testing.assert_array_equal(result[:5], face[:5])
    # the bottom rows are always covered for every style in MASK_STYLES
    assert not np.array_equal(result[-1], face[-1])


def test_every_configured_style_renders_without_crashing() -> None:
    synth = GeometricMaskSynthesizer(list(MASK_STYLES))
    variants = synth.synthesize(aligned_face())
    assert set(variants) == set(MASK_STYLES)
