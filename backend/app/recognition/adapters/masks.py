"""Synthetic mask variants for the enrollment gallery.

Masks are drawn in the canonical aligned frame, where the eyes, nose tip and
mouth corners already sit at fixed coordinates, so the outline follows geometry
that is true by construction and the same photograph always yields the same
templates. The variants differ in colour, coverage height, fold structure and
grain, which is what makes the stored templates span a range of occlusions.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from app.recognition.alignment import ARCFACE_REFERENCE_LANDMARKS, OUTPUT_SIZE
from app.recognition.ports import ComponentStatus, Image


@dataclass(frozen=True, slots=True)
class MaskStyle:
    """One synthetic mask, described in canonical 112x112 pixels."""

    name: str
    #: Fabric colour, BGR.
    colour: tuple[int, int, int]
    #: Top edge relative to the nose tip; positive leaves the nose exposed.
    top_offset: float
    #: How much higher the mask sits at the cheeks than at the centre.
    side_lift: float
    #: Horizontal folds, as on a pleated surgical mask.
    pleats: int
    #: Vertical centre seam, as on a moulded respirator.
    seam: bool
    #: Amplitude of the deterministic fabric grain.
    grain: float


#: Names match the defaults in Settings.mask_variants.
MASK_STYLES: dict[str, MaskStyle] = {
    style.name: style
    for style in (
        MaskStyle("surgical_blue", (196, 171, 122), -7.0, 13.0, 3, False, 4.0),
        MaskStyle("surgical_white", (238, 240, 241), -6.0, 12.0, 3, False, 3.0),
        MaskStyle("cloth_black", (42, 40, 38), -9.0, 16.0, 0, True, 6.0),
        MaskStyle("cloth_colored", (96, 126, 178), -8.0, 15.0, 0, True, 7.0),
        MaskStyle("n95", (233, 233, 236), -11.0, 9.0, 0, True, 5.0),
        MaskStyle("improper_low", (196, 171, 122), 9.0, 4.0, 2, False, 4.0),
    )
}


class GeometricMaskSynthesizer:
    """Renders the configured mask variants onto an aligned face."""

    def __init__(self, variants: Sequence[str]) -> None:
        self._requested = tuple(variants)
        self._styles = tuple(MASK_STYLES[name] for name in self._requested if name in MASK_STYLES)

    def status(self) -> ComponentStatus:
        # Purely geometric, so it is configured as soon as a known variant is asked for.
        unknown = [name for name in self._requested if name not in MASK_STYLES]
        detail = f"geometric variants={[style.name for style in self._styles]}"
        return ComponentStatus(
            name="mask_synthesizer",
            configured=bool(self._styles),
            detail=f"{detail} unknown={unknown}" if unknown else detail,
        )

    def synthesize(self, aligned_face: Image) -> dict[str, Image]:
        # One rendered variant per configured style.
        return {style.name: self._render(aligned_face, style) for style in self._styles}

    def _render(self, aligned_face: Image, style: MaskStyle) -> Image:
        # Blend fabric over the face using a feathered coverage mask.
        size = aligned_face.shape[0]
        scale = size / OUTPUT_SIZE
        reference = ARCFACE_REFERENCE_LANDMARKS * scale
        nose_x, nose_y = float(reference[2][0]), float(reference[2][1])
        eye_y = float((reference[0][1] + reference[1][1]) / 2.0)

        top_y = nose_y + style.top_offset * scale
        # Never ride up over the eyes: that would occlude the periocular region
        # the recogniser depends on.
        side_y = max(eye_y + 4.0 * scale, top_y - style.side_lift * scale)

        alpha = _coverage(size, nose_x, top_y, side_y)[..., None]
        fabric = _fabric(size, style, top_y)
        blended = aligned_face.astype(np.float32) * (1.0 - alpha) + fabric * alpha
        result = np.clip(blended, 0, 255).astype(np.uint8)
        _draw_straps(result, style, side_y, size)
        return result


def _coverage(size: int, nose_x: float, top_y: float, side_y: float) -> NDArray[np.float32]:
    # Soft alpha mask: curved top edge, everything below it covered.
    span = size * 0.18
    shoulder_y = top_y - (top_y - side_y) * 0.35
    polygon = np.array(
        [
            [0, side_y],
            [nose_x - span, shoulder_y],
            [nose_x, top_y],
            [nose_x + span, shoulder_y],
            [size, side_y],
            [size, size],
            [0, size],
        ],
        dtype=np.int32,
    )
    # Anti-aliased drawing is 8-bit only, so rasterise then convert and feather.
    stencil = np.zeros((size, size), dtype=np.uint8)
    cv2.fillPoly(stencil, [polygon], 255, lineType=cv2.LINE_AA)
    alpha = stencil.astype(np.float32) / 255.0
    return cv2.GaussianBlur(alpha, (0, 0), max(0.6, 0.8 * size / OUTPUT_SIZE))


def _fabric(size: int, style: MaskStyle, top_y: float) -> NDArray[np.float32]:
    # Base colour with vertical shading, folds and a deterministic grain.
    scale = size / OUTPUT_SIZE
    gradient = np.linspace(1.06, 0.82, size, dtype=np.float32)[:, None, None]
    shaded = np.clip(np.float32(style.colour) * gradient, 0, 255).astype(np.uint8)
    fabric = np.ascontiguousarray(np.broadcast_to(shaded, (size, size, 3)))

    if style.pleats:
        spacing = (size - top_y) / (style.pleats + 1)
        fold = tuple(int(channel * 0.86) for channel in style.colour)
        for index in range(1, style.pleats + 1):
            y = int(top_y + spacing * index)
            cv2.line(fabric, (0, y), (size, y), fold, max(1, round(1.4 * scale)), cv2.LINE_AA)
    if style.seam:
        x = size // 2
        seam = tuple(int(channel * 0.9) for channel in style.colour)
        cv2.line(fabric, (x, int(top_y)), (x, size), seam, max(1, round(1.2 * scale)), cv2.LINE_AA)

    result = fabric.astype(np.float32)
    if style.grain:
        # Seeded from a stable hash so enrollment is reproducible across runs.
        rng = np.random.default_rng(zlib.crc32(style.name.encode()))
        result += rng.normal(0.0, style.grain, size=(size, size, 1)).astype(np.float32)
    return result


def _draw_straps(image: Image, style: MaskStyle, side_y: float, size: int) -> None:
    # Ear loops running off both edges of the crop.
    colour = tuple(int(channel * 0.75) for channel in style.colour)
    thickness = max(1, round(size / OUTPUT_SIZE * 1.5))
    y = int(side_y)
    drop = int(y + size * 0.05)
    cv2.line(image, (0, y), (int(size * 0.12), drop), colour, thickness, cv2.LINE_AA)
    cv2.line(image, (size, y), (int(size * 0.88), drop), colour, thickness, cv2.LINE_AA)
