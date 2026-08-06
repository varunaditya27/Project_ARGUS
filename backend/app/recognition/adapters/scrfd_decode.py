"""SCRFD output decoding.

The graph emits a score map, a bbox-distance map and a 5-point keypoint-distance
map per FPN stride, all relative to anchor centres. These helpers turn them into
absolute boxes and landmarks in the letterboxed frame.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from app.core.errors import DependencyUnavailableError

STRIDES = (8, 16, 32)
#: Outputs are grouped [scores x3, bboxes x3, keypoints x3].
FMC = len(STRIDES)
_ANCHORS_PER_CELL = 2

Decoded = tuple[NDArray[np.float32], NDArray[np.float32], NDArray[np.float32]]


@lru_cache(maxsize=32)
def anchor_centres(height: int, width: int, stride: int) -> NDArray[np.float32]:
    # Anchor grid for one stride level; cached because it only depends on shape.
    grid_y, grid_x = np.mgrid[:height, :width]
    centres = (np.stack([grid_x, grid_y], axis=-1).astype(np.float32) * stride).reshape(-1, 2)
    return np.repeat(centres, _ANCHORS_PER_CELL, axis=0)


def non_max_suppression(
    boxes: NDArray[np.float32], scores: NDArray[np.float32], iou_threshold: float
) -> list[int]:
    # Greedy IoU suppression; returns kept indices in descending score order.
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(x2 - x1, 0) * np.maximum(y2 - y1, 0)
    order = scores.argsort()[::-1]

    kept: list[int] = []
    while order.size > 0:
        best = order[0]
        kept.append(int(best))
        if order.size == 1:
            break
        rest = order[1:]
        inter_w = np.maximum(np.minimum(x2[best], x2[rest]) - np.maximum(x1[best], x1[rest]), 0)
        inter_h = np.maximum(np.minimum(y2[best], y2[rest]) - np.maximum(y1[best], y1[rest]), 0)
        intersection = inter_w * inter_h
        union = areas[best] + areas[rest] - intersection
        iou = np.where(union > 0, intersection / np.maximum(union, 1e-9), 0.0)
        order = rest[iou <= iou_threshold]
    return kept


def decode(
    outputs: list[NDArray[np.float32]], width: int, height: int, score_threshold: float
) -> Decoded:
    # Concatenate every stride level into one set of boxes, scores and landmarks.
    all_boxes: list[NDArray[np.float32]] = []
    all_scores: list[NDArray[np.float32]] = []
    all_landmarks: list[NDArray[np.float32]] = []

    for level, stride in enumerate(STRIDES):
        scores = _squeeze(outputs[level]).reshape(-1)
        selected = np.flatnonzero(scores >= score_threshold)
        if selected.size == 0:
            continue

        box_distances = _squeeze(outputs[level + FMC])[selected] * stride
        kps_distances = _squeeze(outputs[level + FMC * 2])[selected] * stride
        centres = anchor_centres(height // stride, width // stride, stride)
        if centres.shape[0] != _squeeze(outputs[level + FMC]).shape[0]:
            raise DependencyUnavailableError(
                "SCRFD anchor layout does not match the model output.",
                details={"stride": stride, "anchors": int(centres.shape[0])},
            )

        picked = centres[selected]
        all_scores.append(scores[selected])
        all_boxes.append(
            np.stack(
                [
                    picked[:, 0] - box_distances[:, 0],
                    picked[:, 1] - box_distances[:, 1],
                    picked[:, 0] + box_distances[:, 2],
                    picked[:, 1] + box_distances[:, 3],
                ],
                axis=-1,
            )
        )
        all_landmarks.append(kps_distances.reshape(selected.size, -1, 2) + picked[:, None, :])

    if not all_boxes:
        return (
            np.empty((0, 4), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            np.empty((0, 5, 2), dtype=np.float32),
        )
    return (
        np.vstack(all_boxes).astype(np.float32),
        np.concatenate(all_scores).astype(np.float32),
        np.vstack(all_landmarks).astype(np.float32),
    )


def _squeeze(array: NDArray[np.float32]) -> NDArray[np.float32]:
    # Some SCRFD exports keep the batch axis, others drop it.
    return array[0] if array.ndim == 3 else array
