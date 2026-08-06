"""Tests for evaluation/metrics.py's rank-1 and verification math, all on synthetic vectors."""

import numpy as np

from evaluation import metrics


# random unit vectors, standing in for L2-normalized ArcFace embeddings
def unit_vectors(n, dim=512, seed=0):
    rng = np.random.default_rng(seed)
    vectors = rng.normal(size=(n, dim))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def test_rank1_accuracy_perfect_separation():
    gallery_emb = unit_vectors(5, seed=1)
    gallery_ids = np.array([f"id_{i}" for i in range(5)])
    # probes are the gallery vectors themselves with tiny noise - should
    # always match their own identity, not a neighbour.
    rng = np.random.default_rng(2)
    probe_emb = gallery_emb + rng.normal(scale=0.01, size=gallery_emb.shape)
    probe_emb = probe_emb / np.linalg.norm(probe_emb, axis=1, keepdims=True)
    probe_ids = gallery_ids.copy()

    accuracy = metrics.rank1_accuracy(gallery_emb, gallery_ids, probe_emb, probe_ids)
    assert accuracy == 1.0


def test_rank1_accuracy_detects_wrong_predictions():
    gallery_emb = unit_vectors(3, seed=3)
    gallery_ids = np.array(["a", "b", "c"])
    # probe for "a" is actually closest to gallery "b" - the metric must
    # report this as wrong, not silently pass.
    probe_emb = np.stack([gallery_emb[1], gallery_emb[2]])
    probe_ids = np.array(["a", "c"])

    accuracy = metrics.rank1_accuracy(gallery_emb, gallery_ids, probe_emb, probe_ids)
    assert accuracy == 0.5


def test_verification_scores_shapes_and_membership():
    gallery_emb = unit_vectors(6, seed=4)
    gallery_ids = np.array([f"id_{i}" for i in range(6)])
    probe_emb = gallery_emb[:3]
    probe_ids = gallery_ids[:3]

    genuine, impostor = metrics.verification_scores(gallery_emb, gallery_ids, probe_emb, probe_ids,
                                                      n_impostor_samples=4)
    assert len(genuine) == 3
    assert len(impostor) == 3 * 4
    # genuine scores are self-similarity of unit vectors, must be ~1.0
    assert np.allclose(genuine, 1.0, atol=1e-5)


def test_verification_scores_skips_probes_with_no_gallery_match():
    gallery_emb = unit_vectors(3, seed=5)
    gallery_ids = np.array(["a", "b", "c"])
    probe_emb = unit_vectors(2, seed=6)
    probe_ids = np.array(["a", "stranger"])

    genuine, _ = metrics.verification_scores(gallery_emb, gallery_ids, probe_emb, probe_ids, n_impostor_samples=2)
    assert len(genuine) == 1


def test_roc_auc_perfect_separation_is_one():
    genuine = np.full(20, 0.9)
    impostor = np.full(20, 0.1)
    auc, tar_at_far = metrics.roc_auc_and_tar(genuine, impostor, far_targets=(0.01, 0.5))
    assert auc == 1.0
    assert tar_at_far[0.5] == 1.0


def test_roc_auc_no_separation_is_around_half():
    rng = np.random.default_rng(7)
    genuine = rng.normal(size=500)
    impostor = rng.normal(size=500)
    auc, _ = metrics.roc_auc_and_tar(genuine, impostor)
    assert 0.4 < auc < 0.6
