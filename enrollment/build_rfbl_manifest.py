"""Builds the RFBL manifest: one photo per identity, 460 identities, organizer-provided dataset."""

import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RFBL_DIR = os.path.join(BASE_DIR, "datasets", "RFBL", "RFBL_Register")
OUT_PATH = os.path.join(BASE_DIR, "datasets", "processed", "rfbl_manifest.csv")

FIELDS = ["dataset", "identity", "filename", "path"]


# each RFBL identity folder holds exactly one photo, filename pattern is {flag}_{flag}_{identity}_{index}.jpg
def rows_from_rfbl():
    rows = []
    for identity in sorted(os.listdir(RFBL_DIR)):
        identity_dir = os.path.join(RFBL_DIR, identity)
        if not os.path.isdir(identity_dir):
            continue
        images = sorted(f for f in os.listdir(identity_dir) if f.lower().endswith((".jpg", ".jpeg", ".png")))
        if not images:
            continue
        rows.append({"dataset": "rfbl", "identity": identity, "filename": images[0],
                     "path": os.path.join(identity_dir, images[0])})
    return rows


def write_manifest(rows):
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    rows = rows_from_rfbl()
    write_manifest(rows)
    print(f"rfbl identities: {len(rows)}")
    print(f"written to: {OUT_PATH}")
