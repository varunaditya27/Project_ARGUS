"""Walks every image source and writes one flat CSV: dataset, identity, mask type, is_masked."""

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


# yields (identity, filename, path) for every image under an identity-subfoldered directory
def walk_flat_images(root_dir):
    for identity in sorted(os.listdir(root_dir)):
        identity_dir = os.path.join(root_dir, identity)
        if not os.path.isdir(identity_dir):
            continue
        for filename in sorted(os.listdir(identity_dir)):
            yield identity, filename, os.path.join(identity_dir, filename)


# set of (identity, filename) pairs that made it into the 400-identity reduced scope
def load_reduced_scope():
    with open(REDUCED_MANIFEST_PATH, newline="") as f:
        return {(row["identity"], row["filename"]) for row in csv.DictReader(f)}


# unmasked LFW images, filtered down to the reduced scope
def rows_from_lfw_gallery(reduced_scope):
    rows = []
    for identity, filename, path in walk_flat_images(LFW_SUBSET_DIR):
        if (identity, filename) not in reduced_scope:
            continue
        rows.append({"dataset": "lfw_subset", "identity": identity, "filename": filename,
                     "path": path, "source_tool": "none", "mask_type": "unmasked", "is_masked": 0})
    return rows


# masked LFW images, parsing mask type out of filenames like Aaron_Peirsol_0001_surgical_blue.jpg
def rows_from_masktheface(reduced_scope):
    rows = []
    for identity, filename, path in walk_flat_images(LFW_MTF_DIR):
        stem = os.path.splitext(filename)[0]
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


# RWMFD-masked images, parsing the color variant out of the filename suffix
def rows_from_rwmfd():
    rows = []
    for identity, filename, path in walk_flat_images(LFW_RWMFD_DIR):
        stem = os.path.splitext(filename)[0]
        mask_type = stem.split("_rwmfd_", 1)[-1]
        mask_type = "rwmfd_" + mask_type
        rows.append({"dataset": "lfw_subset", "identity": identity, "filename": filename,
                     "path": path, "source_tool": "rwmfd", "mask_type": mask_type, "is_masked": 1})
    return rows


# maps (identity, image index) -> mask type from mfr2_labels.txt
def read_mfr2_labels():
    labels = {}
    with open(MFR2_LABELS_PATH) as f:
        for line in f:
            identity, index, mask_type = [part.strip() for part in line.strip().split(",")]
            labels[(identity, int(index))] = mask_type
    return labels


# MFR2's real masked/unmasked images, labeled from mfr2_labels.txt
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


# writes the combined rows from all four sources out as one csv
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
