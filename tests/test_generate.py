"""Integration test for embeddings/generate.py - loads the real model, covers testplan.md's AT-03/AT-05."""

import numpy as np
import cv2

from embeddings.generate import get_embedding


# checks a real photo produces a 512-d, L2-normalized float32 embedding
def test_get_embedding_on_real_face_is_unit_512d(sample_face_path):
    embedding = get_embedding(sample_face_path)

    assert embedding is not None
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    assert abs(np.linalg.norm(embedding) - 1.0) < 1e-3


# checks ArcFace inference is deterministic - same image in, exact same vector out
def test_get_embedding_same_face_twice_is_identical(sample_face_path):
    first = get_embedding(sample_face_path)
    second = get_embedding(sample_face_path)
    assert np.array_equal(first, second)


# checks a real image with no face in it (AT-03) is rejected, not crashed on
def test_get_embedding_returns_none_for_image_with_no_face(tmp_path):
    no_face_path = tmp_path / "blank.jpg"
    blank_image = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.imwrite(str(no_face_path), blank_image)

    assert get_embedding(str(no_face_path)) is None


# checks a corrupted file with a .jpg name (AT-05) is rejected, not crashed on
def test_get_embedding_returns_none_for_corrupted_file(tmp_path):
    corrupted_path = tmp_path / "corrupted.jpg"
    corrupted_path.write_bytes(b"this is not a jpeg file at all")

    assert get_embedding(str(corrupted_path)) is None


# checks a path that doesn't exist on disk is rejected, not crashed on
def test_get_embedding_returns_none_for_missing_file(tmp_path):
    missing_path = tmp_path / "does_not_exist.jpg"
    assert get_embedding(str(missing_path)) is None
