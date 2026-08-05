"""Five-point face alignment to the ArcFace 112x112 reference frame.

Enrollment and recognition must align identically, otherwise the embeddings are
not comparable (docs/design.md, enrollment step 3). The reference landmark set
below is the standard ArcFace/InsightFace 112x112 template.

OpenCV is imported lazily: the attendance API runs without the recognition
extra installed, and only this module needs it.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.core.errors import DependencyNotConfiguredError

OUTPUT_SIZE = 112

ARCFACE_REFERENCE_LANDMARKS: NDArray[np.float32] = np.array(
    [
        [38.2946, 51.6963],  # left eye
        [73.5318, 51.5014],  # right eye
        [56.0252, 71.7366],  # nose
        [41.5493, 92.3655],  # left mouth corner
        [70.7299, 92.2041],  # right mouth corner
    ],
    dtype=np.float32,
)


def _require_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on the install extra
        raise DependencyNotConfiguredError(
            "OpenCV is required for face alignment. Install the recognition extra: "
            "pip install -e '.[recognition]'."
        ) from exc
    return cv2


def similarity_transform(
    landmarks: NDArray[np.float32],
    reference: NDArray[np.float32] = ARCFACE_REFERENCE_LANDMARKS,
) -> NDArray[np.float32]:
    """Umeyama similarity transform (rotation + uniform scale + translation)."""
    if landmarks.shape != reference.shape:
        raise ValueError(f"expected landmarks of shape {reference.shape}, got {landmarks.shape}")

    src = np.asarray(landmarks, dtype=np.float64)
    dst = np.asarray(reference, dtype=np.float64)
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_centered, dst_centered = src - src_mean, dst - dst_mean

    covariance = dst_centered.T @ src_centered / src.shape[0]
    u, singular_values, vt = np.linalg.svd(covariance)
    correction = np.eye(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        correction[1, 1] = -1.0

    rotation = u @ correction @ vt
    variance = src_centered.var(axis=0).sum()
    scale = 1.0 if variance == 0 else float(singular_values @ np.diag(correction)) / variance

    matrix = np.zeros((2, 3), dtype=np.float64)
    matrix[:, :2] = scale * rotation
    matrix[:, 2] = dst_mean - scale * rotation @ src_mean
    return matrix.astype(np.float32)


def align_face(
    image: NDArray[np.uint8],
    landmarks: NDArray[np.float32],
    *,
    output_size: int = OUTPUT_SIZE,
) -> NDArray[np.uint8]:
    """Warp a detected face into the canonical ArcFace crop."""
    cv2 = _require_cv2()
    matrix = similarity_transform(landmarks)
    if output_size != OUTPUT_SIZE:
        matrix = matrix * (output_size / OUTPUT_SIZE)
    return cv2.warpAffine(image, matrix, (output_size, output_size), borderValue=(0, 0, 0))


def decode_image(payload: bytes) -> NDArray[np.uint8]:
    """Decode bytes into a BGR image, rejecting anything OpenCV cannot read.

    A file is never trusted because of its extension (docs/design.md, step 1).
    """
    cv2 = _require_cv2()
    buffer = np.frombuffer(payload, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("image could not be decoded")
    return image


def blur_variance(aligned_face: NDArray[np.uint8]) -> float:
    """Variance of the Laplacian -- lower means blurrier."""
    cv2 = _require_cv2()
    grey = cv2.cvtColor(aligned_face, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())
