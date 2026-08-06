"""
Wraps InsightFace's buffalo_l pack (SCRFD detector + ArcFace recognizer) so the rest of the pipeline just calls get_embedding(image_path) and gets
back a 512-d L2-normalized vector, or None if no face was found.

Loading the model is expensive (reads 5 onnx files), so we load it once at module import time and every script that needs embeddings imports
this module rather than building its own FaceAnalysis instance.
"""

import os
import cv2
import numpy as np
import onnxruntime

# FaceAnalysis loads 5 separate onnx sessions (detection, 2 landmark models,
# genderage, recognition), and onnxruntime defaults each one's intra-op
# thread pool to every CPU core. That's up to ~5x the core count all
# fighting over the same cores for what is, per call, a single small
# image - pure scheduling overhead, not real parallelism. insightface
# doesn't expose a way to pass sess_options through FaceAnalysis, so we
# patch the default in before any session gets created.
_original_session_init = onnxruntime.InferenceSession.__init__


def _capped_thread_session_init(self, path_or_bytes, sess_options=None, **kwargs):
    if sess_options is None:
        sess_options = onnxruntime.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
    _original_session_init(self, path_or_bytes, sess_options=sess_options, **kwargs)


onnxruntime.InferenceSession.__init__ = _capped_thread_session_init

from insightface.app import FaceAnalysis  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")

_app = None


def get_app():
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", root=BASE_DIR, providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=-1, det_size=(640, 640))
    return _app


def pick_largest_face(faces):
    if not faces:
        return None
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))


def get_embedding(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return None

    app = get_app()
    faces = app.get(image)
    face = pick_largest_face(faces)
    if face is None:
        return None

    embedding = face.normed_embedding
    return embedding.astype(np.float32)
