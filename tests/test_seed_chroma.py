"""Tests for enrollment/seed_chroma.py - the demo gallery's identity/dedup logic."""

import numpy as np

from enrollment import seed_chroma


# same (dataset, identity) pair always maps to the same uuid, across repeated calls
def test_identity_uuid_is_deterministic():
    first = seed_chroma.identity_uuid("lfw", "Aaron_Peirsol")
    second = seed_chroma.identity_uuid("lfw", "Aaron_Peirsol")
    assert first == second


def test_identity_uuid_differs_by_dataset_or_identity():
    lfw_uuid = seed_chroma.identity_uuid("lfw", "Aaron_Peirsol")
    mfr2_uuid = seed_chroma.identity_uuid("mfr2", "Aaron_Peirsol")
    other_identity = seed_chroma.identity_uuid("lfw", "Someone_Else")
    assert lfw_uuid != mfr2_uuid
    assert lfw_uuid != other_identity


def test_unmasked_rows_tags_every_identity_as_unmasked_template():
    data = {
        "dataset": np.array(["lfw", "mfr2"]),
        "identity": np.array(["alice", "bob"]),
        "embedding": np.zeros((2, 8), dtype=np.float32),
    }
    rows = seed_chroma.unmasked_rows(data)
    assert len(rows) == 2
    assert all(mask_type == seed_chroma.UNMASKED_TEMPLATE for _, mask_type, _, _, _ in rows)


def test_masked_rows_deduplicates_same_identity_same_mask_type():
    # alice has two different source photos both masked as "cloth" - this is the exact
    # scenario that crashed the real seeding run with a DuplicateIDError before the fix
    data = {
        "dataset": np.array(["lfw_subset"] * 3),
        "identity": np.array(["alice", "alice", "bob"]),
        "mask_type": np.array(["cloth", "cloth", "surgical"]),
        "is_masked": np.array([1, 1, 1]),
        "path": np.array(["alice_0002_cloth.jpg", "alice_0001_cloth.jpg", "bob_0001_surgical.jpg"]),
        "embedding": np.arange(3 * 8).reshape(3, 8).astype(np.float32),
    }
    rows = seed_chroma.masked_rows(data)

    alice_rows = [r for r in rows if r[4] == "alice"]
    assert len(alice_rows) == 1
    # lowest path wins, matching eval_sets.py's tie-break convention
    kept_embedding = alice_rows[0][2]
    assert np.array_equal(kept_embedding, data["embedding"][1])


def test_masked_rows_maps_lfw_subset_dataset_name_to_lfw():
    data = {
        "dataset": np.array(["lfw_subset"]),
        "identity": np.array(["alice"]),
        "mask_type": np.array(["cloth"]),
        "is_masked": np.array([1]),
        "path": np.array(["alice_0001_cloth.jpg"]),
        "embedding": np.zeros((1, 8), dtype=np.float32),
    }
    rows = seed_chroma.masked_rows(data)
    assert rows[0][3] == "lfw"


def test_write_identity_map_deduplicates_repeated_student_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_chroma, "IDENTITY_MAP_PATH", str(tmp_path / "map.csv"))
    student_id = seed_chroma.identity_uuid("lfw", "alice")
    rows = [
        (student_id, "UNMASKED", None, "lfw", "alice"),
        (student_id, "cloth", None, "lfw", "alice"),
    ]
    seed_chroma.write_identity_map(rows)

    with open(tmp_path / "map.csv") as f:
        lines = f.read().strip().split("\n")
    assert len(lines) == 2  # header + one row, not one per template
