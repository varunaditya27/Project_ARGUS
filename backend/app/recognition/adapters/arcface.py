"""ArcFace embedder (InsightFace w600k_r50.onnx).

Takes the 112x112 aligned crops produced by app.recognition.alignment and
returns L2-normalised 512-D embeddings, so a cosine query in Chroma is directly
the similarity the decision layer expects. Faces are embedded in batches: one
multi-face frame, or a whole enrollment gallery, is a single forward pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from app.core.errors import DependencyUnavailableError, InvalidRequestError
from app.recognition.adapters.onnx import OnnxModel
from app.recognition.alignment import OUTPUT_SIZE
from app.recognition.ports import ComponentStatus, Embedding, Image

_INPUT_MEAN = 127.5
_INPUT_STD = 127.5


class ArcFaceEmbedder:
    def __init__(
        self,
        model_path: Path,
        *,
        providers: tuple[str, ...],
        intra_op_threads: int,
        embedding_dim: int,
        max_batch: int = 32,
    ) -> None:
        self._model = OnnxModel(
            component="face_embedder",
            model_path=model_path,
            providers=providers,
            intra_op_threads=intra_op_threads,
            # The buffalo_l export fixes the output batch at 1 while accepting a
            # dynamic input batch, so multi-face frames log a benign shape
            # warning. The output shape is verified below regardless.
            quiet=True,
        )
        self._embedding_dim = embedding_dim
        self._max_batch = max_batch

    def status(self) -> ComponentStatus:
        # Model status plus the embedding width.
        status = self._model.status()
        return ComponentStatus(
            name=status.name,
            configured=status.configured,
            detail=f"arcface {status.detail} dim={self._embedding_dim}",
        )

    def warmup(self) -> None:
        # Load the graph before the first request.
        self._model.warmup()

    def embed(self, aligned_faces: Sequence[Image]) -> Embedding:
        # Split into forward passes of at most max_batch crops.
        if not aligned_faces:
            return np.empty((0, self._embedding_dim), dtype=np.float32)
        return np.vstack(
            [
                self._forward(aligned_faces[start : start + self._max_batch])
                for start in range(0, len(aligned_faces), self._max_batch)
            ]
        )

    def _forward(self, faces: Sequence[Image]) -> Embedding:
        # One forward pass, validated against the configured dimension.
        embeddings = np.asarray(self._model.run(self._to_blob(faces))[0], dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[1] != self._embedding_dim:
            raise DependencyUnavailableError(
                "The embedding model returned an unexpected shape.",
                details={
                    "expected_dim": self._embedding_dim,
                    "received_shape": list(embeddings.shape),
                },
            )
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # A zero vector cannot be normalised; left as zeros it scores 0 against
        # everything, which the decision layer treats as UNKNOWN.
        norms[norms == 0.0] = 1.0
        return (embeddings / norms).astype(np.float32)

    @staticmethod
    def _to_blob(faces: Sequence[Image]) -> NDArray[np.float32]:
        # NCHW float blob, RGB, mean/std normalised.
        prepared = []
        for face in faces:
            if face.ndim != 3 or face.shape[2] != 3:
                raise InvalidRequestError("Aligned faces must be 3-channel BGR images.")
            if face.shape[0] != OUTPUT_SIZE or face.shape[1] != OUTPUT_SIZE:
                face = cv2.resize(face, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv2.INTER_LINEAR)
            prepared.append(face[:, :, ::-1].astype(np.float32))
        batch = (np.stack(prepared) - _INPUT_MEAN) / _INPUT_STD
        return np.ascontiguousarray(batch.transpose(0, 3, 1, 2), dtype=np.float32)
