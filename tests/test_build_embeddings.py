"""Tests for embeddings/build_embeddings.py's resume/skip logic, with get_embedding faked out."""

import numpy as np

from embeddings import build_embeddings


def manifest_row(path, identity="alice"):
    return {"path": path, "dataset": "lfw_subset", "identity": identity,
            "source_tool": "none", "mask_type": "unmasked", "is_masked": "0"}


def test_build_skips_rows_where_get_embedding_returns_none(monkeypatch, tmp_path):
    rows = [manifest_row("a.jpg"), manifest_row("b.jpg"), manifest_row("c.jpg")]
    monkeypatch.setattr(build_embeddings, "read_manifest", lambda path: rows)
    monkeypatch.setattr(build_embeddings, "get_embedding",
                         lambda path: None if path == "b.jpg" else np.ones(4, dtype=np.float32))

    out_path = str(tmp_path / "out.npz")
    build_embeddings.build("unused.csv", out_path, resume=False)

    saved = np.load(out_path)
    assert list(saved["path"]) == ["a.jpg", "c.jpg"]


def test_build_with_resume_reuses_existing_embeddings_without_recomputing(monkeypatch, tmp_path):
    out_path = str(tmp_path / "out.npz")
    rows = [manifest_row("a.jpg")]
    build_embeddings.save(rows, [np.full(4, 9.0, dtype=np.float32)], out_path)

    calls = []
    monkeypatch.setattr(build_embeddings, "read_manifest", lambda path: rows)
    monkeypatch.setattr(build_embeddings, "get_embedding", lambda path: calls.append(path) or np.zeros(4))

    build_embeddings.build("unused.csv", out_path, resume=True)

    assert calls == []  # get_embedding never called - the existing row was reused
    saved = np.load(out_path)
    assert np.array_equal(saved["embedding"][0], np.full(4, 9.0, dtype=np.float32))


def test_load_existing_returns_empty_dict_when_no_prior_output(tmp_path):
    existing = build_embeddings.load_existing(str(tmp_path / "does_not_exist.npz"))
    assert existing == {}
