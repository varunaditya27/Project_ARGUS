"""Synthetic mask generation for the enrollment gallery.

ARGUS enrolls an unmasked photograph and stores extra templates showing how that
person's embedding shifts under different masks (docs/design.md). This renderer
produces those variants.

It draws in the **canonical aligned frame**, not in the original photograph. After
:func:`app.recognition.alignment.align_face` every face sits at the same 112x112
reference position, so the eyes, nose tip and mouth corners are at known fixed
coordinates - the mask outline is therefore derived from geometry that is true by
construction rather than estimated per image. That also makes the output
deterministic: the same enrollment photograph always yields the same templates.

Each variant differs in colour, coverage height, fold structure and fabric noise,
which is what makes the stored templates span a range of occlusion patterns
instead of six copies of one shape.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.recognition.alignment import ARCFACE_REFERENCE_LANDMARKS, OUTPUT_SIZE, require_cv2
from app.recognition.ports import ComponentStatus, Image


@dataclass(frozen=True, slots=True)
class MaskStyle:
    """One synthetic mask, described in canonical 112x112 pixels."""

    name: str
    #: Fabric colour, BGR.
    colour: tuple[int, int, int]
    #: Top edge relative to the nose tip: negative covers the nose, positive
    #: leaves it exposed (a badly worn mask).
    top_offset: float
    #: How much higher the mask sits at the cheeks than at the centre.
    side_lift: float
    #: Horizontal folds, as on a pleated surgical mask.
    pleats: int
    #: Vertical centre seam, as on a moulded respirator.
    centre_seam: bool
    #: Ear loops drawn towards the crop edges.
    straps: bool
    #: Amplitude of the deterministic fabric grain.
    grain: float


#: Variant names match the defaults in ``Settings.mask_variants`` / docs/design.md.
MASK_STYLES: dict[str, MaskStyle] = {
    "surgical_blue": MaskStyle(
        name="surgical_blue",
        colour=(196, 171, 122),
        top_offset=-7.0,
        side_lift=13.0,
        pleats=3,
        centre_seam=False,
        straps=True,
        grain=4.0,
    ),
    "surgical_white": MaskStyle(
        name="surgical_white",
        colour=(238, 240, 241),
        top_offset=-6.0,
        side_lift=12.0,
        pleats=3,
        centre_seam=False,
        straps=True,
        grain=3.0,
    ),
    "cloth_black": MaskStyle(
        name="cloth_black",
        colour=(42, 40, 38),
        top_offset=-9.0,
        side_lift=16.0,
        pleats=0,
        centre_seam=True,
        straps=True,
        grain=6.0,
    ),
    "cloth_colored": MaskStyle(
        name="cloth_colored",
        colour=(96, 126, 178),
        top_offset=-8.0,
        side_lift=15.0,
        pleats=0,
        centre_seam=True,
        straps=True,
        grain=7.0,
    ),
    "n95": MaskStyle(
        name="n95",
        colour=(233, 233, 236),
        top_offset=-11.0,
        side_lift=9.0,
        pleats=0,
        centre_seam=True,
        straps=True,
        grain=5.0,
    ),
    "improper_low": MaskStyle(
        name="improper_low",
        colour=(196, 171, 122),
        top_offset=9.0,
        side_lift=4.0,
        pleats=2,
        centre_seam=False,
        straps=True,
        grain=4.0,
    ),
}


class GeometricMaskSynthesizer:
    """Renders the configured mask variants onto an aligned face."""

    def __init__(self, variants: Sequence[str]) -> None:
        self._requested = tuple(variants)
        self._styles = tuple(MASK_STYLES[name] for name in self._requested if name in MASK_STYLES)

    def status(self) -> ComponentStatus:
        unknown = [name for name in self._requested if name not in MASK_STYLES]
        detail = f"variants={[style.name for style in self._styles]}"
        if unknown:
            detail = f"{detail} unknown={unknown}"
        return ComponentStatus(
            name="mask_synthesizer",
            configured=bool(self._styles),
            adapter="geometric-aligned-frame",
            detail=detail,
        )

    def synthesize(self, aligned_face: Image) -> dict[str, Image]:
        return {style.name: self._render(aligned_face, style) for style in self._styles}

    # ----------------------------------------------------------------- drawing
    def _render(self, aligned_face: Image, style: MaskStyle) -> Image:
        cv2 = require_cv2()
        size = aligned_face.shape[0]
        scale = size / OUTPUT_SIZE
        reference = ARCFACE_REFERENCE_LANDMARKS * scale
        nose_x, nose_y = float(reference[2][0]), float(reference[2][1])
        eye_y = float((reference[0][1] + reference[1][1]) / 2.0)

        top_y = nose_y + style.top_offset * scale
        # Never ride up over the eyes - that would occlude the periocular region
        # the recogniser depends on.
        side_y = max(eye_y + 4.0 * scale, top_y - style.side_lift * scale)

        alpha = self._coverage(cv2, size, nose_x, top_y, side_y)
        fabric = self._fabric(cv2, size, style, top_y, scale)

        blended = aligned_face.astype(np.float32) * (1.0 - alpha[..., None])
        blended += fabric * alpha[..., None]
        result = np.clip(blended, 0, 255).astype(np.uint8)

        if style.straps:
            self._draw_straps(cv2, result, style, side_y, size)
        return result

    @staticmethod
    def _coverage(
        cv2, size: int, nose_x: float, top_y: float, side_y: float
    ) -> NDArray[np.float32]:
        """Soft alpha mask: curved top edge, everything below it covered."""
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
        # Anti-aliased drawing is 8-bit only, so rasterise then convert.
        stencil = np.zeros((size, size), dtype=np.uint8)
        cv2.fillPoly(stencil, [polygon], 255, lineType=cv2.LINE_AA)
        alpha = stencil.astype(np.float32) / 255.0
        # Feather the edge so the boundary is not a hard synthetic step.
        return cv2.GaussianBlur(alpha, (0, 0), max(0.6, 0.8 * size / OUTPUT_SIZE))

    @staticmethod
    def _fabric(cv2, size: int, style: MaskStyle, top_y: float, scale: float):
        """Base colour plus shading, folds and a deterministic grain."""
        # Vertical falloff: the fabric is lit at the top and shadowed under the chin.
        gradient = np.linspace(1.06, 0.82, size, dtype=np.float32)[:, None, None]
        shaded = np.clip(np.float32(style.colour) * gradient, 0, 255).astype(np.uint8)
        fabric = np.ascontiguousarray(np.broadcast_to(shaded, (size, size, 3)))

        if style.pleats:
            spacing = (size - top_y) / (style.pleats + 1)
            thickness = max(1, round(1.4 * scale))
            fold = tuple(int(channel * 0.86) for channel in style.colour)
            for index in range(1, style.pleats + 1):
                y = int(top_y + spacing * index)
                cv2.line(fabric, (0, y), (size, y), fold, thickness, lineType=cv2.LINE_AA)

        if style.centre_seam:
            x = size // 2
            seam = tuple(int(channel * 0.9) for channel in style.colour)
            cv2.line(
                fabric,
                (x, int(top_y)),
                (x, size),
                seam,
                max(1, round(1.2 * scale)),
                lineType=cv2.LINE_AA,
            )

        result = fabric.astype(np.float32)
        if style.grain:
            # Seeded from a stable hash so enrollment is reproducible across runs.
            rng = np.random.default_rng(zlib.crc32(style.name.encode()))
            result += rng.normal(0.0, style.grain, size=(size, size, 1)).astype(np.float32)
        return result

    @staticmethod
    def _draw_straps(cv2, image: Image, style: MaskStyle, side_y: float, size: int) -> None:
        colour = tuple(int(c * 0.75) for c in style.colour)
        thickness = max(1, round(size / OUTPUT_SIZE * 1.5))
        y = int(side_y)
        cv2.line(
            image,
            (0, y),
            (int(size * 0.12), int(y + size * 0.05)),
            colour,
            thickness,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            image,
            (size, y),
            (int(size * 0.88), int(y + size * 0.05)),
            colour,
            thickness,
            lineType=cv2.LINE_AA,
        )
