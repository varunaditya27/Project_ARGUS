"""Tests for evaluation/multi_template.py - the ARGUS multi-template gallery builder."""

import numpy as np

from evaluation import multi_template


# fixed-size unit vectors, standing in for L2-normalized ArcFace embeddings
def unit_vectors(n, dim=8, seed=0):
    rng = np.random.default_rng(seed)
    vectors = rng.normal(size=(n, dim))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def make_data():
    emb = unit_vectors(4, seed=1)
    return {
        "dataset": np.array(["lfw_subset"] * 4),
        "identity": np.array(["alice", "alice", "alice", "bob"]),
        "path": np.array(["alice_0001.jpg", "alice_0001_surgical.jpg", "alice_0002_surgical.jpg", "bob_0001.jpg"]),
        "mask_type": np.array(["unmasked", "surgical", "surgical", "unmasked"]),
        "is_masked": np.array([0, 1, 1, 0]),
        "source_tool": np.array(["none", "masktheface", "masktheface", "none"]),
        "embedding": emb.astype(np.float32),
    }


def test_multi_template_gallery_includes_unmasked_plus_one_template_per_mask_type():
    data = make_data()
    gallery_ids, gallery_emb, excluded_paths = multi_template.pick_multi_template_gallery(
        data, "lfw_subset", "unmasked")

    # alice gets 2 rows (unmasked + 1 surgical template), bob gets 1 (unmasked only, no masked images)
    assert list(gallery_ids).count("alice") == 2
    assert list(gallery_ids).count("bob") == 1
    assert gallery_emb.shape[0] == 3


def test_held_out_probes_exclude_whichever_image_became_a_template():
    data = make_data()
    _, _, excluded_paths = multi_template.pick_multi_template_gallery(data, "lfw_subset", "unmasked")
    ids, emb, mask_types, tools = multi_template.held_out_masked_probes(data, "lfw_subset", excluded_paths)

    # alice_0001_surgical became the template (lowest path), alice_0002_surgical must remain as a probe
    assert len(ids) == 1
    assert ids[0] == "alice"
