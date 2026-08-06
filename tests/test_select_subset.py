"""Tests for select_subset.py's identity filtering and symlink-building logic."""

import os

from datasets.masking.scripts import select_subset


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def test_list_identities_with_min_images_drops_single_image_identities(tmp_path):
    touch(tmp_path / "Alice" / "Alice_0001.jpg")
    touch(tmp_path / "Alice" / "Alice_0002.jpg")
    touch(tmp_path / "Bob" / "Bob_0001.jpg")  # only one image - should be dropped

    identities = select_subset.list_identities_with_min_images(str(tmp_path), min_images=2)

    names = [name for name, _ in identities]
    assert names == ["Alice"]


def test_list_identities_with_min_images_ignores_non_jpg_files(tmp_path):
    touch(tmp_path / "Alice" / "Alice_0001.jpg")
    touch(tmp_path / "Alice" / "Alice_0002.jpg")
    touch(tmp_path / "Alice" / "notes.txt")  # not a jpg, must not count towards the minimum

    identities = select_subset.list_identities_with_min_images(str(tmp_path), min_images=2)

    assert identities == [("Alice", ["Alice_0001.jpg", "Alice_0002.jpg"])]


def test_list_identities_with_min_images_ignores_stray_files_in_src_dir(tmp_path):
    touch(tmp_path / "Alice" / "Alice_0001.jpg")
    touch(tmp_path / "Alice" / "Alice_0002.jpg")
    touch(tmp_path / "readme.txt")  # a file directly in src_dir, not an identity folder

    identities = select_subset.list_identities_with_min_images(str(tmp_path), min_images=2)

    assert [name for name, _ in identities] == ["Alice"]


def test_build_subset_symlinks_every_image_and_returns_manifest_rows(tmp_path, monkeypatch):
    lfw_src = tmp_path / "raw"
    subset_dir = tmp_path / "subset"
    touch(lfw_src / "Alice" / "Alice_0001.jpg")
    monkeypatch.setattr(select_subset, "LFW_SRC", str(lfw_src))
    monkeypatch.setattr(select_subset, "SUBSET_DIR", str(subset_dir))

    rows = select_subset.build_subset([("Alice", ["Alice_0001.jpg"])])

    assert rows == [{
        "identity": "Alice", "filename": "Alice_0001.jpg",
        "path": str(subset_dir / "Alice" / "Alice_0001.jpg"),
    }]
    assert os.path.islink(subset_dir / "Alice" / "Alice_0001.jpg")


def test_build_subset_does_not_recreate_an_existing_symlink(tmp_path, monkeypatch):
    lfw_src = tmp_path / "raw"
    subset_dir = tmp_path / "subset"
    touch(lfw_src / "Alice" / "Alice_0001.jpg")
    monkeypatch.setattr(select_subset, "LFW_SRC", str(lfw_src))
    monkeypatch.setattr(select_subset, "SUBSET_DIR", str(subset_dir))

    select_subset.build_subset([("Alice", ["Alice_0001.jpg"])])
    # running it again must not raise FileExistsError on the symlink
    select_subset.build_subset([("Alice", ["Alice_0001.jpg"])])
