"""Tests for enrollment/build_embeddings_local.py's skip logic, with get_embedding faked out."""

import csv

import numpy as np

from enrollment import build_embeddings_local


# a minimal enrollment manifest row
def manifest_row(path, identity="alice"):
    return {"path": path, "dataset": "lfw", "identity": identity, "filename": f"{identity}.jpg"}


# checks a row where no face was detected is dropped from the saved output, not saved as garbage
def test_build_skips_rows_where_get_embedding_returns_none(monkeypatch, tmp_path):
    rows = [manifest_row("a.jpg", "alice"), manifest_row("b.jpg", "bob")]
    out_path = tmp_path / "out.npz"
    monkeypatch.setattr(build_embeddings_local, "read_manifest", lambda path: rows)
    monkeypatch.setattr(build_embeddings_local, "OUT_PATH", str(out_path))
    monkeypatch.setattr(build_embeddings_local, "get_embedding",
                         lambda path: None if path == "b.jpg" else np.ones(4, dtype=np.float32))

    build_embeddings_local.build()

    saved = np.load(out_path)
    assert list(saved["identity"]) == ["alice"]


# checks the manifest CSV is parsed into the expected list-of-dicts row format
def test_read_manifest_parses_csv_rows(tmp_path):
    manifest_path = tmp_path / "manifest.csv"
    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["dataset", "identity", "filename", "path"])
        writer.writeheader()
        writer.writerow({"dataset": "lfw", "identity": "alice", "filename": "alice.jpg", "path": "/x/alice.jpg"})

    rows = build_embeddings_local.read_manifest(str(manifest_path))
    assert rows == [{"dataset": "lfw", "identity": "alice", "filename": "alice.jpg", "path": "/x/alice.jpg"}]
