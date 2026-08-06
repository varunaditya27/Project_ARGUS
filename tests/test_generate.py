"""
Integration test - this one loads the real buffalo_l model and runs real
inference, unlike the other test files which are pure logic. Slower
(a few seconds for model load) but it's the only place we actually check
the ArcFace wrapper end to end rather than assuming it works.

Covers docs/testplan.md's AT-03 (no face -> rejected, not crashed) and
AT-05 (damaged/unsupported file -> rejected without crashing) at the
embedding-generation level, ahead of there being an actual enrollment
endpoint to test those against.
"""

import numpy as np
import cv2

from embeddings.generate import get_embedding


def test_get_embedding_on_real_face_is_unit_512d(sample_face_path):
    embedding = get_embedding(sample_face_path)

    assert embedding is not None
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    assert abs(np.linalg.norm(embedding) - 1.0) < 1e-3


def test_get_embedding_same_face_twice_is_identical(sample_face_path):
    # ArcFace inference should be deterministic - same image in, same
    # vector out, not just "close enough".
    first = get_embedding(sample_face_path)
    second = get_embedding(sample_face_path)
    assert np.array_equal(first, second)


def test_get_embedding_returns_none_for_image_with_no_face(tmp_path):
    # AT-03: a real image, just nothing in it that looks like a face.
    no_face_path = tmp_path / "blank.jpg"
    blank_image = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.imwrite(str(no_face_path), blank_image)

    assert get_embedding(str(no_face_path)) is None


def test_get_embedding_returns_none_for_corrupted_file(tmp_path):
    # AT-05: file exists, has a .jpg name, but isn't valid image data -
    # this must not crash the caller.
    corrupted_path = tmp_path / "corrupted.jpg"
    corrupted_path.write_bytes(b"this is not a jpeg file at all")

    assert get_embedding(str(corrupted_path)) is None


def test_get_embedding_returns_none_for_missing_file(tmp_path):
    missing_path = tmp_path / "does_not_exist.jpg"
    assert get_embedding(str(missing_path)) is None
