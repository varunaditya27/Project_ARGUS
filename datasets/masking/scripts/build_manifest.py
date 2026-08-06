"""
Walks every image source we care about and writes one flat CSV describing
every image: which dataset it's from, whose face it is, whether it's
masked, which tool made the mask (if any), and the mask type.

This is what embeddings/ and evaluation/ read from - they don't need to
know about folder layouts, they just read rows out of this file.

Run after select_reduced_scope.py, run_masktheface.py and run_rwmfd.py
have all finished.

Scope note: MaskTheFace ran over the full 1,680-identity LFW_subset
before we realized the embedding step couldn't keep up with that volume
on this machine (see select_reduced_scope.py). Rather than redo the
masking, we just filter its output down to the same 400-identity /
1,160-image slice everything else uses, and only keep 5 of its 9 mask
types to match the reduced time budget.
"""

import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LFW_SUBSET_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset")
LFW_MTF_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset_masked")
LFW_RWMFD_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset_rwmfd")
MFR2_DIR = os.path.join(BASE_DIR, "datasets", "raw", "MFR2", "mfr2")
MFR2_LABELS_PATH = os.path.join(MFR2_DIR, "mfr2_labels.txt")
REDUCED_MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "LFW_reduced_manifest.csv")
OUT_PATH = os.path.join(BASE_DIR, "datasets", "processed", "full_manifest.csv")

FIELDS = ["dataset", "identity", "filename", "path", "source_tool", "mask_type", "is_masked"]
KEEP_MASKTHEFACE_TYPES = {"surgical", "surgical_blue", "N95", "KN95", "cloth"}


def walk_flat_images(root_dir):
    for identity in sorted(os.listdir(root_dir)):
        identity_dir = os.path.join(root_dir, identity)
        if not os.path.isdir(identity_dir):
            continue
        for filename in sorted(os.listdir(identity_dir)):
            yield identity, filename, os.path.join(identity_dir, filename)


def load_reduced_scope():
    with open(REDUCED_MANIFEST_PATH, newline="") as f:
        return {(row["identity"], row["filename"]) for row in csv.DictReader(f)}


def rows_from_lfw_gallery(reduced_scope):
    rows = []
    for identity, filename, path in walk_flat_images(LFW_SUBSET_DIR):
        if (identity, filename) not in reduced_scope:
            continue
        rows.append({"dataset": "lfw_subset", "identity": identity, "filename": filename,
                     "path": path, "source_tool": "none", "mask_type": "unmasked", "is_masked": 0})
    return rows


def rows_from_masktheface(reduced_scope):
    rows = []
    for identity, filename, path in walk_flat_images(LFW_MTF_DIR):
        stem = os.path.splitext(filename)[0]
        # filenames look like Aaron_Peirsol_0001_surgical_blue.jpg, so the
        # mask type is everything after the 4-digit numeric suffix.
        parts = stem.split("_")
        mask_type = "unknown"
        base_filename = None
        for i, part in enumerate(parts):
            if part.isdigit():
                mask_type = "_".join(parts[i + 1:])
                base_filename = "_".join(parts[:i + 1]) + ".jpg"
                break
        if mask_type not in KEEP_MASKTHEFACE_TYPES:
            continue
        if (identity, base_filename) not in reduced_scope:
            continue
        rows.append({"dataset": "lfw_subset", "identity": identity, "filename": filename,
                     "path": path, "source_tool": "masktheface", "mask_type": mask_type, "is_masked": 1})
    return rows


def rows_from_rwmfd():
    rows = []
    for identity, filename, path in walk_flat_images(LFW_RWMFD_DIR):
        stem = os.path.splitext(filename)[0]
        mask_type = stem.split("_rwmfd_", 1)[-1]
        mask_type = "rwmfd_" + mask_type
        rows.append({"dataset": "lfw_subset", "identity": identity, "filename": filename,
                     "path": path, "source_tool": "rwmfd", "mask_type": mask_type, "is_masked": 1})
    return rows


def read_mfr2_labels():
    labels = {}
    with open(MFR2_LABELS_PATH) as f:
        for line in f:
            identity, index, mask_type = [part.strip() for part in line.strip().split(",")]
            labels[(identity, int(index))] = mask_type
    return labels


def rows_from_mfr2():
    labels = read_mfr2_labels()
    rows = []
    for identity, filename, path in walk_flat_images(MFR2_DIR):
        if not filename.lower().endswith(".png"):
            continue
        stem = os.path.splitext(filename)[0]
        index = int(stem.rsplit("_", 1)[-1])
        mask_type = labels.get((identity, index), "unknown")
        is_masked = 0 if mask_type == "no-mask" else 1
        rows.append({"dataset": "mfr2", "identity": identity, "filename": filename,
                     "path": path, "source_tool": "real", "mask_type": mask_type, "is_masked": is_masked})
    return rows


def write_manifest(rows):
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    reduced_scope = load_reduced_scope()
    rows = (rows_from_lfw_gallery(reduced_scope) + rows_from_masktheface(reduced_scope)
            + rows_from_rwmfd() + rows_from_mfr2())
    write_manifest(rows)
    print(f"total rows: {len(rows)}")
    print(f"written to: {OUT_PATH}")
