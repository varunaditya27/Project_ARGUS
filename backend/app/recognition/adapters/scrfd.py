"""SCRFD face detector (InsightFace ``det_10g.onnx``).

The graph emits, for each of the three FPN strides (8, 16, 32), a score map, a
bbox-distance map and a 5-point keypoint-distance map, all relative to anchor
centres. This module turns those into absolute boxes and landmarks in the
coordinates of the *original* image:

1. letterbox the image into the network's square input, remembering the scale,
2. decode every stride level, keeping only anchors above the score threshold,
3. NMS across levels,
4. divide by the letterbox scale to get back to original pixels.

The 5 landmarks it returns are exactly what :mod:`app.recognition.alignment`
needs, so detection and alignment stay consistent between enrollment and
recognition.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.core.errors import DependencyUnavailableError
from app.recognition.adapters.onnx_model import OnnxModel
from app.recognition.alignment import require_cv2
from app.recognition.ports import ComponentStatus, DetectedFace, Image

#: SCRFD preprocessing constants (must match the values the model was exported with).
_INPUT_MEAN = 127.5
_INPUT_STD = 128.0

_FEATURE_STRIDES = (8, 16, 32)
_ANCHORS_PER_CELL = 2
#: Number of stride levels; outputs are grouped [scores x3, bboxes x3, kps x3].
_FMC = len(_FEATURE_STRIDES)


def _distance_to_boxes(centres: NDArray[np.float32], distances: NDArray[np.float32]):
    """Anchor centre + (left, top, right, bottom) distances -> (x1, y1, x2, y2)."""
    x1 = centres[:, 0] - distances[:, 0]
    y1 = centres[:, 1] - distances[:, 1]
    x2 = centres[:, 0] + distances[:, 2]
    y2 = centres[:, 1] + distances[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance_to_points(centres: NDArray[np.float32], distances: NDArray[np.float32]):
    """Anchor centre + per-landmark (dx, dy) pairs -> absolute landmark points."""
    offsets = distances.reshape(distances.shape[0], -1, 2)
    return offsets + centres[:, None, :]


def non_max_suppression(
    boxes: NDArray[np.float32], scores: NDArray[np.float32], iou_threshold: float
) -> list[int]:
    """Greedy IoU suppression; returns kept indices in descending score order."""
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


class ScrfdFaceDetector:
    def __init__(
        self,
        model_path: Path,
        *,
        providers: tuple[str, ...],
        intra_op_threads: int,
        input_size: int,
        score_threshold: float,
        nms_iou: float,
        max_faces: int,
    ) -> None:
        self._model = OnnxModel(
            component="face_detector",
            model_path=model_path,
            providers=providers,
            intra_op_threads=intra_op_threads,
        )
        self._configured_input_size = input_size
        self._score_threshold = score_threshold
        self._nms_iou = nms_iou
        self._max_faces = max_faces
        self._anchor_cache: dict[tuple[int, int, int], NDArray[np.float32]] = {}

    # ------------------------------------------------------------------ wiring
    def status(self) -> ComponentStatus:
        status = self._model.status()
        return ComponentStatus(
            name=status.name,
            configured=status.configured,
            adapter="scrfd-onnx",
            detail=f"{status.detail} score>={self._score_threshold} nms_iou={self._nms_iou}",
        )

    def warmup(self) -> None:
        self._model.warmup()

    def _input_size(self) -> tuple[int, int]:
        """Fixed size baked into the graph if there is one, otherwise the config."""
        shape = self._model.input_shape()
        height, width = shape[2], shape[3]
        if isinstance(height, int) and isinstance(width, int) and height > 0 and width > 0:
            return width, height
        size = self._configured_input_size
        return size, size

    # --------------------------------------------------------------- inference
    def detect(self, image: Image) -> list[DetectedFace]:
        if image.ndim != 3 or image.shape[2] != 3:
            raise DependencyUnavailableError("The detector expects a 3-channel BGR image.")

        width, height = self._input_size()
        padded, scale = self._letterbox(image, width, height)
        blob = self._to_blob(padded)
        outputs = self._model.run(blob)
        if len(outputs) < _FMC * 3:
            raise DependencyUnavailableError(
                "Unexpected SCRFD output layout; this adapter needs a keypoint-enabled model "
                "such as det_10g.onnx.",
                details={"outputs": len(outputs)},
            )

        boxes, scores, landmarks = self._decode(outputs, width, height)
        if boxes.size == 0:
            return []

        keep = non_max_suppression(boxes, scores, self._nms_iou)[: self._max_faces]
        image_height, image_width = image.shape[:2]
        faces: list[DetectedFace] = []
        for index in keep:
            box = boxes[index] / scale
            points = (landmarks[index] / scale).astype(np.float32)
            x1 = int(max(0.0, min(box[0], image_width - 1)))
            y1 = int(max(0.0, min(box[1], image_height - 1)))
            x2 = int(max(0.0, min(box[2], image_width - 1)))
            y2 = int(max(0.0, min(box[3], image_height - 1)))
            if x2 <= x1 or y2 <= y1:
                continue
            faces.append(
                DetectedFace(
                    bbox=(x1, y1, x2, y2),
                    detection_score=float(scores[index]),
                    landmarks=points,
                )
            )
        return faces

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _letterbox(image: Image, width: int, height: int) -> tuple[Image, float]:
        """Scale-preserving fit into a width x height canvas, anchored top-left."""
        cv2 = require_cv2()
        source_height, source_width = image.shape[:2]
        scale = min(width / source_width, height / source_height)
        new_width = max(1, round(source_width * scale))
        new_height = max(1, round(source_height * scale))
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        canvas[:new_height, :new_width] = resized
        return canvas, scale

    @staticmethod
    def _to_blob(image: Image) -> NDArray[np.float32]:
        """NCHW float blob, RGB, mean/std normalised - same as cv2.dnn.blobFromImage."""
        rgb = image[:, :, ::-1].astype(np.float32)
        normalised = (rgb - _INPUT_MEAN) / _INPUT_STD
        return np.ascontiguousarray(normalised.transpose(2, 0, 1)[None], dtype=np.float32)

    def _anchor_centres(self, height: int, width: int, stride: int) -> NDArray[np.float32]:
        key = (height, width, stride)
        cached = self._anchor_cache.get(key)
        if cached is not None:
            return cached
        grid_y, grid_x = np.mgrid[:height, :width]
        centres = np.stack([grid_x, grid_y], axis=-1).astype(np.float32) * stride
        centres = centres.reshape(-1, 2)
        if _ANCHORS_PER_CELL > 1:
            centres = np.repeat(centres, _ANCHORS_PER_CELL, axis=0)
        self._anchor_cache[key] = centres
        return centres

    def _decode(
        self, outputs: list[NDArray[np.float32]], width: int, height: int
    ) -> tuple[NDArray[np.float32], NDArray[np.float32], NDArray[np.float32]]:
        all_boxes: list[NDArray[np.float32]] = []
        all_scores: list[NDArray[np.float32]] = []
        all_landmarks: list[NDArray[np.float32]] = []

        for level, stride in enumerate(_FEATURE_STRIDES):
            scores = self._squeeze_batch(outputs[level]).reshape(-1)
            box_distances = self._squeeze_batch(outputs[level + _FMC]) * stride
            kps_distances = self._squeeze_batch(outputs[level + _FMC * 2]) * stride

            selected = np.flatnonzero(scores >= self._score_threshold)
            if selected.size == 0:
                continue

            centres = self._anchor_centres(height // stride, width // stride, stride)
            if centres.shape[0] != box_distances.shape[0]:
                raise DependencyUnavailableError(
                    "SCRFD anchor layout does not match the model output.",
                    details={
                        "stride": stride,
                        "anchors": int(centres.shape[0]),
                        "predictions": int(box_distances.shape[0]),
                    },
                )

            all_scores.append(scores[selected])
            all_boxes.append(_distance_to_boxes(centres[selected], box_distances[selected]))
            all_landmarks.append(_distance_to_points(centres[selected], kps_distances[selected]))

        if not all_boxes:
            empty = np.empty((0, 4), dtype=np.float32)
            return empty, np.empty((0,), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32)
        return (
            np.vstack(all_boxes).astype(np.float32),
            np.concatenate(all_scores).astype(np.float32),
            np.vstack(all_landmarks).astype(np.float32),
        )

    @staticmethod
    def _squeeze_batch(array: NDArray[np.float32]) -> NDArray[np.float32]:
        """Some SCRFD exports keep the batch axis, others drop it."""
        return array[0] if array.ndim == 3 else array
