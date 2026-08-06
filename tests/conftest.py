import os

import numpy as np
import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture
def sample_face_path():
    return os.path.join(FIXTURES_DIR, "sample_face.jpg")


@pytest.fixture
def synthetic_embeddings():
    """
    Builds a small, deterministic set of embeddings that behaves like a
    real embeddings.npz would: distinct random unit vectors per identity,
    each with a lightly-perturbed unmasked probe and a heavily-perturbed
    masked probe, so rank-1/verification math has something real to
    separate rather than degenerate all-identical vectors.
    """
    rng = np.random.default_rng(0)
    identities = [f"person_{i}" for i in range(10)]

    paths, dataset, identity, source_tool, mask_type, is_masked, embedding = [], [], [], [], [], [], []

    def add_row(path, ident, tool, mtype, masked, vector):
        paths.append(path)
        dataset.append("lfw_subset")
        identity.append(ident)
        source_tool.append(tool)
        mask_type.append(mtype)
        is_masked.append(masked)
        embedding.append(vector / np.linalg.norm(vector))

    for ident in identities:
        base = rng.normal(size=512)
        add_row(f"{ident}_0001.jpg", ident, "none", "unmasked", 0, base)

        probe_unmasked = base + rng.normal(scale=0.05, size=512)
        add_row(f"{ident}_0002.jpg", ident, "none", "unmasked", 0, probe_unmasked)

        probe_masked = base + rng.normal(scale=0.2, size=512)
        add_row(f"{ident}_0001_surgical.jpg", ident, "masktheface", "surgical", 1, probe_masked)

    return {
        "path": np.array(paths),
        "dataset": np.array(dataset),
        "identity": np.array(identity),
        "source_tool": np.array(source_tool),
        "mask_type": np.array(mask_type),
        "is_masked": np.array(is_masked),
        "embedding": np.stack(embedding).astype(np.float32),
    }
