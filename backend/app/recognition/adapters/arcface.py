"""ArcFace embedder (InsightFace ``w600k_r50.onnx``).

Takes 112x112 aligned crops produced by :mod:`app.recognition.alignment` and
returns L2-normalised 512-D embeddings, so a dot product in ChromaDB is the
cosine similarity the decision layer expects.

Faces are embedded in batches: one frame with several faces, or a whole
enrollment (unmasked + every synthetic mask variant), is a single forward pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.core.errors import DependencyUnavailableError, InvalidRequestError
from app.recognition.adapters.onnx_model import OnnxModel
from app.recognition.alignment import OUTPUT_SIZE, require_cv2
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
            # buffalo_l's w600k_r50 export fixes the output batch at 1 while its
            # input batch is dynamic, so every multi-face frame would otherwise
            # log a shape warning. The outputs are verified against the declared
            # dimension below regardless.
            quiet=True,
        )
        self._embedding_dim = embedding_dim
        self._max_batch = max_batch

    def status(self) -> ComponentStatus:
        status = self._model.status()
        return ComponentStatus(
            name=status.name,
            configured=status.configured,
            adapter="arcface-onnx",
            detail=f"{status.detail} dim={self._embedding_dim}",
        )

    def warmup(self) -> None:
        self._model.warmup()

    def embed(self, aligned_faces: Sequence[Image]) -> Embedding:
        if not aligned_faces:
            return np.empty((0, self._embedding_dim), dtype=np.float32)

        chunks = [
            self._forward(aligned_faces[start : start + self._max_batch])
            for start in range(0, len(aligned_faces), self._max_batch)
        ]
        return np.vstack(chunks)

    def _forward(self, faces: Sequence[Image]) -> Embedding:
        blob = self._to_blob(faces)
        outputs = self._model.run(blob)
        embeddings = np.asarray(outputs[0], dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[1] != self._embedding_dim:
            raise DependencyUnavailableError(
                "The embedding model returned an unexpected shape.",
                details={
                    "expected_dim": self._embedding_dim,
                    "received_shape": list(embeddings.shape),
                },
            )
        return self._l2_normalise(embeddings)

    @staticmethod
    def _to_blob(faces: Sequence[Image]) -> NDArray[np.float32]:
        cv2 = require_cv2()
        prepared = []
        for face in faces:
            if face.ndim != 3 or face.shape[2] != 3:
                raise InvalidRequestError("Aligned faces must be 3-channel BGR images.")
            if face.shape[0] != OUTPUT_SIZE or face.shape[1] != OUTPUT_SIZE:
                face = cv2.resize(face, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv2.INTER_LINEAR)
            prepared.append(face[:, :, ::-1].astype(np.float32))
        batch = (np.stack(prepared) - _INPUT_MEAN) / _INPUT_STD
        return np.ascontiguousarray(batch.transpose(0, 3, 1, 2), dtype=np.float32)

    @staticmethod
    def _l2_normalise(embeddings: NDArray[np.float32]) -> Embedding:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # A zero vector cannot be normalised; leaving it as zeros makes it score 0
        # against everything, which the decision layer treats as UNKNOWN.
        norms[norms == 0.0] = 1.0
        return (embeddings / norms).astype(np.float32)
