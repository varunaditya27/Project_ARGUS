"""SCRFD face detector (InsightFace det_10g.onnx).

Letterbox the image into the network input, decode every stride level, run NMS
across levels, then divide by the letterbox scale to get back to original pixels.
The 5 landmarks returned are exactly what app.recognition.alignment expects.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from app.core.errors import DependencyUnavailableError
from app.recognition.adapters import scrfd_decode
from app.recognition.adapters.onnx import OnnxModel
from app.recognition.ports import ComponentStatus, DetectedFace, Image

#: Preprocessing constants the model was exported with.
_INPUT_MEAN = 127.5
_INPUT_STD = 128.0

#: Second attempt when the configured size finds nothing. Webcam frames and
#: normal photos are scene-scale and always succeed on the first pass at the
#: configured size (640 by default); this exists for already-tightly-cropped
#: uploads (e.g. RWMFD/MFR2-style images with no margin around the face),
#: where letterboxing into 640 upsamples them past the point SCRFD's anchors
#: still match. Same value verified against both during backend integration.
_FALLBACK_INPUT_SIZE = 160


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

    def status(self) -> ComponentStatus:
        # Model status plus the score threshold in force.
        status = self._model.status()
        return ComponentStatus(
            name=status.name,
            configured=status.configured,
            detail=f"scrfd {status.detail} score>={self._score_threshold}",
        )

    def warmup(self) -> None:
        # Load the graph before the first request.
        self._model.warmup()

    def detect(self, image: Image) -> list[DetectedFace]:
        # Scene-scale images (webcam, normal photos) always succeed at the configured
        # size. A second pass at a smaller size only runs when the first finds nothing,
        # so this costs nothing extra for the common case.
        if image.ndim != 3 or image.shape[2] != 3:
            raise DependencyUnavailableError("The detector expects a 3-channel BGR image.")

        width, height = self._input_size()
        faces = self._detect_at_size(image, width, height)
        if faces or (width, height) == (_FALLBACK_INPUT_SIZE, _FALLBACK_INPUT_SIZE):
            return faces
        return self._detect_at_size(image, _FALLBACK_INPUT_SIZE, _FALLBACK_INPUT_SIZE)

    def _detect_at_size(self, image: Image, width: int, height: int) -> list[DetectedFace]:
        # One letterbox-run-decode pass at a specific input size.
        padded, scale = self._letterbox(image, width, height)
        outputs = self._model.run(self._to_blob(padded))
        if len(outputs) < scrfd_decode.FMC * 3:
            raise DependencyUnavailableError(
                "Unexpected SCRFD output layout; a keypoint-enabled model such as det_10g.onnx "
                "is required.",
                details={"outputs": len(outputs)},
            )

        boxes, scores, landmarks = scrfd_decode.decode(
            outputs, width, height, self._score_threshold
        )
        if boxes.size == 0:
            return []

        keep = scrfd_decode.non_max_suppression(boxes, scores, self._nms_iou)[: self._max_faces]
        return self._to_faces(image.shape[:2], boxes, scores, landmarks, keep, scale)

    def _input_size(self) -> tuple[int, int]:
        # The size baked into the graph if it has one, otherwise the configured size.
        shape = self._model.input_shape()
        height, width = shape[2], shape[3]
        if isinstance(height, int) and isinstance(width, int) and height > 0 and width > 0:
            return width, height
        return self._configured_input_size, self._configured_input_size

    @staticmethod
    def _letterbox(image: Image, width: int, height: int) -> tuple[Image, float]:
        # Scale-preserving fit into the network canvas, anchored top-left.
        source_height, source_width = image.shape[:2]
        scale = min(width / source_width, height / source_height)
        resized = cv2.resize(
            image,
            (max(1, round(source_width * scale)), max(1, round(source_height * scale))),
            interpolation=cv2.INTER_LINEAR,
        )
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        return canvas, scale

    @staticmethod
    def _to_blob(image: Image) -> NDArray[np.float32]:
        # NCHW float blob, RGB, mean/std normalised.
        rgb = image[:, :, ::-1].astype(np.float32)
        normalised = (rgb - _INPUT_MEAN) / _INPUT_STD
        return np.ascontiguousarray(normalised.transpose(2, 0, 1)[None], dtype=np.float32)

    @staticmethod
    def _to_faces(
        image_shape: tuple[int, int],
        boxes: NDArray[np.float32],
        scores: NDArray[np.float32],
        landmarks: NDArray[np.float32],
        keep: list[int],
        scale: float,
    ) -> list[DetectedFace]:
        # Rescale to original pixels and clip to the image bounds.
        image_height, image_width = image_shape
        faces: list[DetectedFace] = []
        for index in keep:
            box = boxes[index] / scale
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
                    landmarks=(landmarks[index] / scale).astype(np.float32),
                )
            )
        return faces
