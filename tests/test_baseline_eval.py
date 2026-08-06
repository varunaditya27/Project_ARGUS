"""Tests for evaluation/baseline_eval.py's empty-set handling and per-mask-type grouping."""

import numpy as np

from evaluation import baseline_eval


def unit_vectors(n, dim=8, seed=0):
    rng = np.random.default_rng(seed)
    vectors = rng.normal(size=(n, dim))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


# checks an empty probe set returns None instead of crashing on empty arrays
def test_evaluate_split_returns_none_for_empty_probe_set():
    gallery_emb = unit_vectors(3, seed=1)
    gallery_ids = np.array(["a", "b", "c"])
    result = baseline_eval.evaluate_split(gallery_ids, gallery_emb, np.array([]), np.empty((0, 8)))
    assert result is None


# checks a real gallery/probe split reports the expected rank-1 accuracy and probe count
def test_evaluate_split_reports_rank1_and_auc_for_a_real_split():
    gallery_emb = unit_vectors(3, seed=1)
    gallery_ids = np.array(["a", "b", "c"])
    probe_emb = gallery_emb.copy()
    probe_ids = gallery_ids.copy()

    result = baseline_eval.evaluate_split(gallery_ids, gallery_emb, probe_ids, probe_emb)

    assert result["n_probes"] == 3
    assert result["rank1_accuracy"] == 1.0


# checks results are grouped correctly by mask type, one entry per type present in the probes
def test_evaluate_by_mask_type_groups_results_and_skips_empty_groups():
    gallery_emb = unit_vectors(2, seed=2)
    gallery_ids = np.array(["a", "b"])
    probe_emb = gallery_emb.copy()
    probe_ids = gallery_ids.copy()
    mask_types = np.array(["surgical", "cloth"])

    results = baseline_eval.evaluate_by_mask_type(gallery_ids, gallery_emb, probe_ids, probe_emb, mask_types)

    assert set(results.keys()) == {"surgical", "cloth"}
    assert results["surgical"]["n_probes"] == 1
