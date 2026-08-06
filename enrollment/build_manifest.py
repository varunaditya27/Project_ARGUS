"""Builds the enrollment manifest: one unmasked photo per identity, LFW (5,749) + MFR2 (53)."""

import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LFW_DIR = os.path.join(BASE_DIR, "datasets", "raw", "LFW", "lfw-deepfunneled", "lfw-deepfunneled")
MFR2_DIR = os.path.join(BASE_DIR, "datasets", "raw", "MFR2", "mfr2")
MFR2_LABELS_PATH = os.path.join(MFR2_DIR, "mfr2_labels.txt")
OUT_PATH = os.path.join(BASE_DIR, "datasets", "processed", "enrollment_manifest.csv")

FIELDS = ["dataset", "identity", "filename", "path"]


# every LFW identity's lowest-numbered photo - full 5,749, no >=2-images filter (that's an eval-only constraint)
def rows_from_lfw():
    rows = []
    for identity in sorted(os.listdir(LFW_DIR)):
        identity_dir = os.path.join(LFW_DIR, identity)
        if not os.path.isdir(identity_dir):
            continue
        images = sorted(f for f in os.listdir(identity_dir) if f.lower().endswith(".jpg"))
        if not images:
            continue
        rows.append({"dataset": "lfw", "identity": identity, "filename": images[0],
                     "path": os.path.join(identity_dir, images[0])})
    return rows


# each MFR2 identity's lowest-indexed "no-mask" photo per mfr2_labels.txt
def rows_from_mfr2():
    lowest_no_mask = {}
    with open(MFR2_LABELS_PATH) as f:
        for line in f:
            identity, index, mask_type = [part.strip() for part in line.strip().split(",")]
            if mask_type != "no-mask":
                continue
            index = int(index)
            if identity not in lowest_no_mask or index < lowest_no_mask[identity]:
                lowest_no_mask[identity] = index

    rows = []
    for identity, index in sorted(lowest_no_mask.items()):
        filename = f"{identity}_{index:04d}.png"
        path = os.path.join(MFR2_DIR, identity, filename)
        if not os.path.exists(path):
            continue
        rows.append({"dataset": "mfr2", "identity": identity, "filename": filename, "path": path})
    return rows


# writes the combined LFW + MFR2 enrollment rows out as one csv
def write_manifest(rows):
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    rows = rows_from_lfw() + rows_from_mfr2()
    write_manifest(rows)
    print(f"lfw identities: {sum(1 for r in rows if r['dataset'] == 'lfw')}")
    print(f"mfr2 identities: {sum(1 for r in rows if r['dataset'] == 'mfr2')}")
    print(f"total: {len(rows)}")
    print(f"written to: {OUT_PATH}")
