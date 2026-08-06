"""Tests for build_manifest.py's filename parsing - covers AT-02 from docs/testplan.md."""

import os

from datasets.masking.scripts import build_manifest as bm


# creates an empty file at path, making parent dirs as needed
def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def test_masktheface_parses_single_word_and_multi_word_mask_types(tmp_path, monkeypatch):
    mtf_dir = tmp_path / "masked"
    touch(mtf_dir / "Alice_Smith" / "Alice_Smith_0001_cloth.jpg")
    touch(mtf_dir / "Alice_Smith" / "Alice_Smith_0001_surgical_blue.jpg")
    monkeypatch.setattr(bm, "LFW_MTF_DIR", str(mtf_dir))

    reduced_scope = {("Alice_Smith", "Alice_Smith_0001.jpg")}
    rows = bm.rows_from_masktheface(reduced_scope)

    mask_types = {r["mask_type"] for r in rows}
    assert mask_types == {"cloth", "surgical_blue"}
    assert all(r["is_masked"] == 1 and r["source_tool"] == "masktheface" for r in rows)


def test_masktheface_drops_types_outside_keep_list(tmp_path, monkeypatch):
    mtf_dir = tmp_path / "masked"
    touch(mtf_dir / "Bob_Jones" / "Bob_Jones_0001_gas.jpg")  # "gas" is not in KEEP_MASKTHEFACE_TYPES
    monkeypatch.setattr(bm, "LFW_MTF_DIR", str(mtf_dir))

    reduced_scope = {("Bob_Jones", "Bob_Jones_0001.jpg")}
    rows = bm.rows_from_masktheface(reduced_scope)

    assert rows == []


def test_masktheface_drops_images_outside_reduced_scope(tmp_path, monkeypatch):
    mtf_dir = tmp_path / "masked"
    touch(mtf_dir / "Carl_Lee" / "Carl_Lee_0005_N95.jpg")
    monkeypatch.setattr(bm, "LFW_MTF_DIR", str(mtf_dir))

    # reduced scope only includes 0001-0004 per select_reduced_scope.py's cap - 0005 should never appear
    reduced_scope = {("Carl_Lee", "Carl_Lee_0001.jpg")}
    rows = bm.rows_from_masktheface(reduced_scope)

    assert rows == []


def test_mfr2_labels_map_no_mask_to_unmasked_flag(tmp_path, monkeypatch):
    mfr2_dir = tmp_path / "mfr2"
    touch(mfr2_dir / "Dana_Kim" / "Dana_Kim_0001.png")
    touch(mfr2_dir / "Dana_Kim" / "Dana_Kim_0002.png")
    labels_path = tmp_path / "mfr2_labels.txt"
    labels_path.write_text("Dana_Kim, 1, surgical_white\nDana_Kim, 2, no-mask\n")

    monkeypatch.setattr(bm, "MFR2_DIR", str(mfr2_dir))
    monkeypatch.setattr(bm, "MFR2_LABELS_PATH", str(labels_path))

    rows = bm.rows_from_mfr2()
    by_filename = {r["filename"]: r for r in rows}

    assert by_filename["Dana_Kim_0001.png"]["is_masked"] == 1
    assert by_filename["Dana_Kim_0001.png"]["mask_type"] == "surgical_white"
    assert by_filename["Dana_Kim_0002.png"]["is_masked"] == 0
    assert by_filename["Dana_Kim_0002.png"]["mask_type"] == "no-mask"


def test_mfr2_missing_label_falls_back_to_unknown(tmp_path, monkeypatch):
    mfr2_dir = tmp_path / "mfr2"
    touch(mfr2_dir / "Eve_Wu" / "Eve_Wu_0001.png")
    labels_path = tmp_path / "mfr2_labels.txt"
    labels_path.write_text("")  # no label for Eve_Wu at all

    monkeypatch.setattr(bm, "MFR2_DIR", str(mfr2_dir))
    monkeypatch.setattr(bm, "MFR2_LABELS_PATH", str(labels_path))

    rows = bm.rows_from_mfr2()
    assert rows[0]["mask_type"] == "unknown"
    assert rows[0]["is_masked"] == 1  # unknown defaults to masked, not silently treated as clean
