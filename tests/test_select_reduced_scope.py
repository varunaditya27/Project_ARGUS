"""Tests for select_reduced_scope.py's identity/image capping logic."""

from datasets.masking.scripts import select_reduced_scope


def row(identity, filename):
    return {"identity": identity, "filename": filename, "path": f"/x/{identity}/{filename}"}


# checks only the first N identities in alphabetical order survive the cap, later ones are dropped
def test_reduce_rows_keeps_only_the_first_n_identities_alphabetically(monkeypatch):
    monkeypatch.setattr(select_reduced_scope, "MAX_IDENTITIES", 2)
    monkeypatch.setattr(select_reduced_scope, "MAX_IMAGES_PER_IDENTITY", 10)
    rows = [row("Charlie", "0001.jpg"), row("Alice", "0001.jpg"), row("Bob", "0001.jpg")]

    reduced = select_reduced_scope.reduce_rows(rows)

    kept_identities = {r["identity"] for r in reduced}
    assert kept_identities == {"Alice", "Bob"}  # Charlie sorts last, dropped


# checks only the lowest-filename images survive the per-identity image cap
def test_reduce_rows_caps_images_per_identity_keeping_lowest_filenames(monkeypatch):
    monkeypatch.setattr(select_reduced_scope, "MAX_IDENTITIES", 10)
    monkeypatch.setattr(select_reduced_scope, "MAX_IMAGES_PER_IDENTITY", 2)
    rows = [row("Alice", "0003.jpg"), row("Alice", "0001.jpg"), row("Alice", "0002.jpg")]

    reduced = select_reduced_scope.reduce_rows(rows)

    filenames = sorted(r["filename"] for r in reduced)
    assert filenames == ["0001.jpg", "0002.jpg"]
