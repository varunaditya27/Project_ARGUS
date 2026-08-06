"""Alignment maths (no OpenCV needed for the transform itself)."""

from __future__ import annotations

import numpy as np

from app.recognition.alignment import ARCFACE_REFERENCE_LANDMARKS, similarity_transform


def apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    homogeneous = np.hstack([points, np.ones((points.shape[0], 1), dtype=points.dtype)])
    return homogeneous @ matrix.T


def test_reference_landmarks_map_to_themselves() -> None:
    matrix = similarity_transform(ARCFACE_REFERENCE_LANDMARKS)
    np.testing.assert_allclose(
        apply(matrix, ARCFACE_REFERENCE_LANDMARKS), ARCFACE_REFERENCE_LANDMARKS, atol=1e-4
    )


def test_scaled_and_shifted_face_is_normalised_back() -> None:
    landmarks = ARCFACE_REFERENCE_LANDMARKS * 2.0 + np.array([40.0, 25.0], dtype=np.float32)
    matrix = similarity_transform(landmarks)
    np.testing.assert_allclose(apply(matrix, landmarks), ARCFACE_REFERENCE_LANDMARKS, atol=1e-3)


def test_rotated_face_is_normalised_back() -> None:
    angle = np.deg2rad(17.0)
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]], dtype=np.float32
    )
    landmarks = (ARCFACE_REFERENCE_LANDMARKS @ rotation.T) * 1.4
    matrix = similarity_transform(landmarks)
    np.testing.assert_allclose(apply(matrix, landmarks), ARCFACE_REFERENCE_LANDMARKS, atol=1e-3)
