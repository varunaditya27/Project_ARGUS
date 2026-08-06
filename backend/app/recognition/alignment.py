"""Five-point alignment to the ArcFace 112x112 reference frame.

Enrollment and recognition must align identically or the embeddings are not
comparable, so both go through this module. The reference landmarks are the
standard InsightFace 112x112 template.
"""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

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


def similarity_transform(
    landmarks: NDArray[np.float32],
    reference: NDArray[np.float32] = ARCFACE_REFERENCE_LANDMARKS,
) -> NDArray[np.float32]:
    # Umeyama similarity transform: rotation, uniform scale and translation.
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


def align_face(image: NDArray[np.uint8], landmarks: NDArray[np.float32]) -> NDArray[np.uint8]:
    # Warp a detected face into the canonical ArcFace crop.
    matrix = similarity_transform(landmarks)
    return cv2.warpAffine(image, matrix, (OUTPUT_SIZE, OUTPUT_SIZE), borderValue=(0, 0, 0))


def decode_image(payload: bytes) -> NDArray[np.uint8]:
    # Decode bytes to BGR; a file is never trusted because of its extension.
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("image could not be decoded")
    return image


def blur_variance(aligned_face: NDArray[np.uint8]) -> float:
    # Variance of the Laplacian; lower means blurrier.
    grey = cv2.cvtColor(aligned_face, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())
