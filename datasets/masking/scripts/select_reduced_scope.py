"""Cuts LFW_subset down to the first 400 identities, max 4 images each, for RWMFD/embedding."""

import csv
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FULL_MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset_manifest.csv")
REDUCED_MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "LFW_reduced_manifest.csv")

MAX_IDENTITIES = 400
MAX_IMAGES_PER_IDENTITY = 4


# loads the full 1,680-identity manifest select_subset.py already wrote
def read_full_manifest():
    with open(FULL_MANIFEST_PATH, newline="") as f:
        return list(csv.DictReader(f))


# keeps only the first 400 identities (alphabetical) capped at 4 images each
def reduce_rows(rows):
    by_identity = defaultdict(list)
    for row in rows:
        by_identity[row["identity"]].append(row)

    chosen_identities = sorted(by_identity.keys())[:MAX_IDENTITIES]
    reduced = []
    for identity in chosen_identities:
        identity_rows = sorted(by_identity[identity], key=lambda r: r["filename"])
        reduced.extend(identity_rows[:MAX_IMAGES_PER_IDENTITY])
    return reduced


# writes the reduced identity/filename/path rows out as csv
def write_manifest(rows):
    with open(REDUCED_MANIFEST_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["identity", "filename", "path"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    full_rows = read_full_manifest()
    reduced = reduce_rows(full_rows)
    write_manifest(reduced)
    print(f"identities: {len(set(r['identity'] for r in reduced))}")
    print(f"images: {len(reduced)}")
    print(f"written to: {REDUCED_MANIFEST_PATH}")
