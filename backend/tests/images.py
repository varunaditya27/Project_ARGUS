"""Image builders for the tests that run the real vision stack.

Everything derives from the one public portrait the repository ships, so no
test depends on a face that is not in version control. The occluded and blurred
probes are constructed here rather than committed as binaries, which keeps the
transformation visible and reviewable.
"""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from tests.conftest import SAMPLE_FACE

Frame = NDArray[np.uint8]


def sample_face_bytes() -> bytes:
    # The portrait exactly as stored, for enrollment.
    return SAMPLE_FACE.read_bytes()


def decode(data: bytes) -> Frame:
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None, "the sample face could not be decoded"
    return frame


def encode(frame: Frame) -> bytes:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    assert ok, "the frame could not be encoded"
    return bytes(buffer)


def sample_face() -> Frame:
    return decode(sample_face_bytes())


def blank(width: int = 640, height: int = 480, value: int = 200) -> bytes:
    # A valid JPEG with no face in it.
    return encode(np.full((height, width, 3), value, dtype=np.uint8))


def two_faces(gap: int = 40) -> bytes:
    # The same portrait twice on one canvas: two detections, one frame.
    face = sample_face()
    height, width = face.shape[:2]
    canvas = np.full((height + 2 * gap, width * 2 + 3 * gap, 3), 210, dtype=np.uint8)
    canvas[gap : gap + height, gap : gap + width] = face
    canvas[gap : gap + height, 2 * gap + width : 2 * gap + 2 * width] = face
    return encode(canvas)


def blurred(sigma: float = 9.0) -> bytes:
    # Heavy defocus: still a face, but not one worth deciding on.
    return encode(cv2.GaussianBlur(sample_face(), (0, 0), sigma))


def tiny(scale: float = 0.12) -> bytes:
    # A face far too small to carry identity, pasted back into a full frame.
    face = sample_face()
    small = cv2.resize(face, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    canvas = np.full_like(face, 210)
    canvas[: small.shape[0], : small.shape[1]] = small
    return encode(canvas)


def occluded(bbox: tuple[int, int, int, int], coverage: float = 0.45) -> bytes:
    """The portrait with its lower face covered, standing in for a worn mask.

    A flat rectangle is deliberately cruder than the enrollment synthesizer:
    the probe must not be drawn by the same code that built the gallery, or the
    test would only prove that a function is deterministic.
    """
    frame = sample_face()
    x1, y1, x2, y2 = bbox
    top = int(y2 - (y2 - y1) * coverage)
    cv2.rectangle(frame, (x1, top), (x2, y2), (150, 140, 130), thickness=-1)
    return encode(frame)


def corrupt() -> bytes:
    # Right magic bytes, truncated payload: decoding must fail cleanly.
    return sample_face_bytes()[:64]
