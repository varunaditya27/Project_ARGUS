"""
eval_sets.py takes an already-loaded npz-like dict, so tests here build
one directly instead of round-tripping through a real file - faster, and
keeps focus on the splitting logic rather than numpy's own I/O.
"""

import numpy as np

from evaluation import eval_sets


# checks the gallery keeps exactly one photo per identity, choosing the lowest filename
def test_pick_gallery_picks_lowest_filename_per_identity():
    data = {
        "dataset": np.array(["lfw_subset"] * 4),
        "identity": np.array(["alice", "alice", "bob", "bob"]),
        "mask_type": np.array(["unmasked"] * 4),
        "path": np.array(["alice_0002.jpg", "alice_0001.jpg", "bob_0001.jpg", "bob_0003.jpg"]),
        "embedding": np.arange(4 * 8).reshape(4, 8).astype(np.float32),
    }
    ids, emb, paths = eval_sets.pick_gallery(data, "lfw_subset", "unmasked")

    assert set(ids.tolist()) == {"alice", "bob"}
    picked = dict(zip(ids.tolist(), paths.tolist()))
    assert picked["alice"] == "alice_0001.jpg"
    assert picked["bob"] == "bob_0001.jpg"
    assert emb.shape == (2, 8)


# checks a dataset with no matching gallery rows returns an empty, correctly-shaped result
def test_pick_gallery_empty_dataset_does_not_crash():
    data = {
        "dataset": np.array(["mfr2"]),
        "identity": np.array(["someone"]),
        "mask_type": np.array(["unmasked"]),  # no "no-mask" rows -> mfr2 gallery is empty
        "path": np.array(["x.jpg"]),
        "embedding": np.zeros((1, 8), dtype=np.float32),
    }
    ids, emb, paths = eval_sets.pick_gallery(data, "mfr2", "no-mask")
    assert len(ids) == 0
    assert emb.shape == (0, 512)


# checks the probe set never includes whichever photo was picked as the gallery photo
def test_unmasked_probes_excludes_gallery_rows():
    data = {
        "dataset": np.array(["lfw_subset"] * 3),
        "identity": np.array(["alice"] * 3),
        "mask_type": np.array(["unmasked"] * 3),
        "path": np.array(["alice_0001.jpg", "alice_0002.jpg", "alice_0003.jpg"]),
        "embedding": np.arange(3 * 8).reshape(3, 8).astype(np.float32),
    }
    gallery_paths = np.array(["alice_0001.jpg"])
    ids, emb = eval_sets.unmasked_probes(data, "lfw_subset", "unmasked", gallery_paths)

    assert len(ids) == 2
    assert emb.shape == (2, 8)
    # the excluded row's embedding (row 0, values 0-7) must not appear in the probes
    assert not any(np.array_equal(row, data["embedding"][0]) for row in emb)


# checks only masked rows are returned, each tagged with its mask type and source tool
def test_masked_probes_returns_only_masked_rows_with_metadata():
    data = {
        "dataset": np.array(["lfw_subset"] * 2),
        "identity": np.array(["alice", "alice"]),
        "mask_type": np.array(["unmasked", "surgical"]),
        "is_masked": np.array([0, 1]),
        "source_tool": np.array(["none", "masktheface"]),
        "embedding": np.arange(2 * 8).reshape(2, 8).astype(np.float32),
    }
    ids, emb, mask_types, source_tools = eval_sets.masked_probes(data, "lfw_subset")

    assert len(ids) == 1
    assert mask_types[0] == "surgical"
    assert source_tools[0] == "masktheface"


# checks the full LFW gallery/probe split has the right counts and mask types on synthetic data
def test_build_lfw_sets_end_to_end(synthetic_embeddings):
    sets = eval_sets.build_lfw_sets(synthetic_embeddings)

    assert len(sets["gallery_ids"]) == 10
    assert len(sets["unmasked_probe_ids"]) == 10  # one probe per identity
    assert len(sets["masked_probe_ids"]) == 10
    assert set(sets["masked_probe_types"].tolist()) == {"surgical"}
