"""Wraps InsightFace's buffalo_l pack: get_embedding(image_path) -> 512-d unit vector, or None."""

import os
import cv2
import numpy as np
import onnxruntime
from insightface.app import FaceAnalysis

# importing FaceAnalysis only defines the class - it doesn't create an onnx
# session until get_app() below calls FaceAnalysis(...).prepare(), so patching
# InferenceSession.__init__ here, after the import, still runs in time
_original_session_init = onnxruntime.InferenceSession.__init__


# caps each onnx session to 1 thread - default spawns a pool per core x 5 sessions, which was 2x slower
def _capped_thread_session_init(self, path_or_bytes, sess_options=None, **kwargs):
    if sess_options is None:
        sess_options = onnxruntime.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
    _original_session_init(self, path_or_bytes, sess_options=sess_options, **kwargs)


onnxruntime.InferenceSession.__init__ = _capped_thread_session_init

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_app = None


# lazy singleton so the model loads once, not once per get_embedding() call
def get_app():
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l", root=BASE_DIR, providers=["CPUExecutionProvider"])
        # det_size=160 (not the default 640) - tightly cropped inputs like RWMFD/MFR2 broke detection at 640
        _app.prepare(ctx_id=-1, det_size=(160, 160))
    return _app


# picks the biggest face when a detector finds more than one, ignores the rest
def pick_largest_face(faces):
    if not faces:
        return None
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))


# runs detection + recognition on one image, returns None if no face was found
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
