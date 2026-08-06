"""SCRFD output decoding and NMS maths (pure numpy, no ONNX model needed)."""

from __future__ import annotations

import numpy as np

from app.recognition.adapters import scrfd_decode


# checks the higher-scoring of two overlapping boxes survives, the lower one is suppressed
def test_nms_keeps_highest_score_when_boxes_overlap() -> None:
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float32)
    scores = np.array([0.9, 0.95, 0.5], dtype=np.float32)
    kept = scrfd_decode.non_max_suppression(boxes, scores, iou_threshold=0.5)
    assert kept == [1, 2]  # box 1 (higher score) suppresses overlapping box 0


# checks two boxes with no overlap both survive suppression independently
def test_nms_keeps_non_overlapping_boxes_separately() -> None:
    boxes = np.array([[0, 0, 10, 10], [50, 50, 60, 60]], dtype=np.float32)
    scores = np.array([0.9, 0.8], dtype=np.float32)
    kept = scrfd_decode.non_max_suppression(boxes, scores, iou_threshold=0.5)
    assert sorted(kept) == [0, 1]


# checks kept indices come back ordered highest-score-first, not in their original input order
def test_nms_returns_indices_in_descending_score_order() -> None:
    boxes = np.array([[0, 0, 10, 10], [20, 20, 30, 30], [40, 40, 50, 50]], dtype=np.float32)
    scores = np.array([0.3, 0.9, 0.6], dtype=np.float32)
    kept = scrfd_decode.non_max_suppression(boxes, scores, iou_threshold=0.5)
    assert kept == [1, 2, 0]


# per-stride (scores, boxes, keypoints) triple, matching SCRFD's raw output shape before decoding
def empty_level_outputs(
    height: int, width: int, stride: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    anchors = (height // stride) * (width // stride) * 2
    scores = np.zeros(anchors, dtype=np.float32)
    boxes = np.zeros((anchors, 4), dtype=np.float32)
    keypoints = np.zeros((anchors, 10), dtype=np.float32)
    return scores, boxes, keypoints


# checks an all-zero-score output (no detections) decodes to correctly-shaped empty arrays
def test_decode_returns_empty_when_no_score_clears_the_threshold() -> None:
    height, width = 32, 32
    outputs = [empty_level_outputs(height, width, stride)[0] for stride in scrfd_decode.STRIDES]
    outputs += [empty_level_outputs(height, width, stride)[1] for stride in scrfd_decode.STRIDES]
    outputs += [empty_level_outputs(height, width, stride)[2] for stride in scrfd_decode.STRIDES]

    boxes, scores, landmarks = scrfd_decode.decode(outputs, width, height, score_threshold=0.5)
    assert boxes.shape == (0, 4)
    assert scores.shape == (0,)
    assert landmarks.shape == (0, 5, 2)


# checks one anchor's raw distance outputs decode into the correct absolute pixel box, hand-verified
def test_decode_converts_one_anchor_s_distances_into_an_absolute_box() -> None:
    height, width, stride = 32, 32, 8
    # anchor 0 sits at grid cell (0, 0) for this shape/stride, so its centre is pixel (0, 0)
    scores, boxes, keypoints = empty_level_outputs(height, width, stride)
    scores[0] = 0.9
    boxes[0] = [1, 2, 3, 4]  # left/top/right/bottom distances from the centre, in stride units

    outputs = [scores, np.zeros_like(scores), np.zeros_like(scores)]
    outputs += [boxes, np.zeros_like(boxes), np.zeros_like(boxes)]
    outputs += [keypoints, np.zeros_like(keypoints), np.zeros_like(keypoints)]

    decoded_boxes, decoded_scores, _ = scrfd_decode.decode(
        outputs, width, height, score_threshold=0.5
    )

    np.testing.assert_allclose(decoded_scores, [0.9], atol=1e-6)
    # centre (0,0), distances scaled by stride=8: left=8, top=16, right=24, bottom=32
    np.testing.assert_array_equal(decoded_boxes[0], [-8, -16, 24, 32])
