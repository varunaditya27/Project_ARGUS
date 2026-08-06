"""Tests for evaluation/calibrate_thresholds.py's threshold/margin math, on synthetic data."""

import numpy as np

from evaluation import calibrate_thresholds


# dim=512 matches eval_sets.pick_gallery's hardcoded empty-gallery fallback shape,
# so the mfr2 branch (no rows in this test data) doesn't hit a matmul dimension mismatch
def unit_vectors(n, dim=512, seed=0):
    rng = np.random.default_rng(seed)
    vectors = rng.normal(size=(n, dim))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


# 3 identities in lfw_subset, each with an unmasked gallery photo and one masked probe;
# mfr2 is left empty since pick_gallery/masked_probes already handle that gracefully
def make_data(probe_noise_scale):
    base = unit_vectors(3, seed=1)
    rng = np.random.default_rng(2)
    probes = base + rng.normal(scale=probe_noise_scale, size=base.shape)
    probes = probes / np.linalg.norm(probes, axis=1, keepdims=True)

    identities = np.array(["a", "b", "c"])
    return {
        "dataset": np.array(["lfw_subset"] * 6),
        "identity": np.concatenate([identities, identities]),
        "mask_type": np.array(["unmasked"] * 3 + ["surgical"] * 3),
        "is_masked": np.array([0, 0, 0, 1, 1, 1]),
        "source_tool": np.array(["none"] * 3 + ["masktheface"] * 3),
        "path": np.array(["a_0001.jpg", "b_0001.jpg", "c_0001.jpg",
                           "a_0001_surgical.jpg", "b_0001_surgical.jpg", "c_0001_surgical.jpg"]),
        "embedding": np.concatenate([base, probes]).astype(np.float32),
    }


# checks genuine (self-match) scores come out higher than impostor scores on well-separated data
def test_pooled_masked_scores_separates_genuine_from_impostor_with_low_noise():
    data = make_data(probe_noise_scale=0.01)
    genuine, impostor = calibrate_thresholds.pooled_masked_scores(data)
    assert len(genuine) == 3
    assert genuine.mean() > impostor.mean()


# checks a target FAR of 0 gives a threshold at or above the single highest impostor score
def test_threshold_at_far_zero_rejects_everything_below_max_impostor():
    genuine = np.array([0.9, 0.8, 0.7])
    impostor = np.array([0.1, 0.2, 0.6])
    threshold = calibrate_thresholds.threshold_at_far(genuine, impostor, target_far=0.0)
    # at FAR=0, the threshold must clear the highest impostor score
    assert threshold > 0.6


# checks top1/top2 margins land in "correct" when the nearest gallery neighbour is the true identity
def test_rank1_margins_splits_correct_and_wrong_by_top1_identity():
    data = make_data(probe_noise_scale=0.01)
    correct_margins, wrong_margins = calibrate_thresholds.rank1_margins(data)
    # low noise means every probe's nearest gallery neighbour should be its own identity
    assert len(correct_margins) == 3
    assert len(wrong_margins) == 0
    assert correct_margins.min() > 0
