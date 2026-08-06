"""Synthetic mask variants: the gallery is only as good as these are varied."""

from __future__ import annotations

import numpy as np
import pytest

from app.recognition.adapters.masks import MASK_STYLES, GeometricMaskSynthesizer
from app.recognition.alignment import OUTPUT_SIZE

ALL_VARIANTS = tuple(MASK_STYLES)


def aligned_face(size: int = OUTPUT_SIZE) -> np.ndarray:
    # A flat grey crop is enough: what matters is which pixels change.
    return np.full((size, size, 3), 128, dtype=np.uint8)


def test_every_configured_variant_is_rendered() -> None:
    rendered = GeometricMaskSynthesizer(ALL_VARIANTS).synthesize(aligned_face())
    assert set(rendered) == set(ALL_VARIANTS)
    assert all(image.shape == (OUTPUT_SIZE, OUTPUT_SIZE, 3) for image in rendered.values())


def test_only_the_requested_variants_are_rendered() -> None:
    rendered = GeometricMaskSynthesizer(["n95"]).synthesize(aligned_face())
    assert set(rendered) == {"n95"}


def test_the_variants_differ_from_each_other() -> None:
    # Six identical masks would mean six copies of one template in Chroma.
    rendered = GeometricMaskSynthesizer(ALL_VARIANTS).synthesize(aligned_face())
    flattened = {name: image.tobytes() for name, image in rendered.items()}
    assert len(set(flattened.values())) == len(ALL_VARIANTS)


def test_rendering_is_deterministic() -> None:
    # Re-enrolling the same photograph must not churn the stored vectors.
    first = GeometricMaskSynthesizer(ALL_VARIANTS).synthesize(aligned_face())
    second = GeometricMaskSynthesizer(ALL_VARIANTS).synthesize(aligned_face())
    assert all(np.array_equal(first[name], second[name]) for name in first)


@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_the_eye_region_is_never_covered(variant: str) -> None:
    # The recogniser leans on the periocular region; a mask that rides over it
    # would poison the template it is supposed to enrich.
    face = aligned_face()
    rendered = GeometricMaskSynthesizer([variant]).synthesize(face)[variant]
    eyes = slice(0, int(OUTPUT_SIZE * 0.35))
    assert np.array_equal(rendered[eyes], face[eyes])


@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_the_chin_is_always_covered(variant: str) -> None:
    face = aligned_face()
    rendered = GeometricMaskSynthesizer([variant]).synthesize(face)[variant]
    chin = rendered[int(OUTPUT_SIZE * 0.85) :]
    assert not np.array_equal(chin, face[int(OUTPUT_SIZE * 0.85) :])


def test_an_unknown_variant_is_reported_and_skipped() -> None:
    synthesizer = GeometricMaskSynthesizer(["n95", "chainmail"])
    status = synthesizer.status()
    assert status.configured is True
    assert "chainmail" in status.detail
    assert set(synthesizer.synthesize(aligned_face())) == {"n95"}


def test_no_known_variant_leaves_the_component_unconfigured() -> None:
    # Edge: a typo in ARGUS_MASK_VARIANTS must not silently disable masking.
    status = GeometricMaskSynthesizer(["chainmail"]).status()
    assert status.configured is False


def test_a_larger_crop_is_handled_by_scaling() -> None:
    # Edge: the synthesizer is written in canonical 112px units.
    rendered = GeometricMaskSynthesizer(["n95"]).synthesize(aligned_face(size=224))["n95"]
    assert rendered.shape == (224, 224, 3)
