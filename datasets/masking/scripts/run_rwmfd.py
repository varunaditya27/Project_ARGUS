"""
Runs the vendored RWMFD wear-a-mask tool over datasets/processed/LFW_reduced_manifest.csv
(400 identities, capped at 4 images each - see select_reduced_scope.py for
why we're not running this over the full 1,680-identity subset: this tool
re-detects the face per mask color, benchmarked at ~0.45s/call, so the
full subset would take ~4.6 hours here). We keep 2 of its 4 textures
(blue, black) rather than all 4, for the same time-budget reason.

Output: datasets/processed/LFW_subset_rwmfd/<identity>/<stem>_<variant>.jpg
Note this tool also re-crops and resizes to 128x128 as part of its own
alignment step (see wearmask.FaceMasker.mask) - that's the vendored
tool's behaviour, not something we're choosing here.
"""

import csv
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RWMFD_DIR = os.path.join(BASE_DIR, "datasets", "masking", "rwmfd")
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "LFW_reduced_manifest.csv")
OUT_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset_rwmfd")

sys.path.insert(0, RWMFD_DIR)
from wearmask import FaceMasker, BLUE_IMAGE_PATH, BLACK_IMAGE_PATH  # noqa: E402

VARIANTS = {
    "rwmfd_blue": BLUE_IMAGE_PATH,
    "rwmfd_black": BLACK_IMAGE_PATH,
}


def read_manifest(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run():
    rows = read_manifest(MANIFEST_PATH)
    total = len(rows) * len(VARIANTS)
    done = 0
    for row in rows:
        identity = row["identity"]
        stem = os.path.splitext(row["filename"])[0]
        out_identity_dir = os.path.join(OUT_DIR, identity)
        os.makedirs(out_identity_dir, exist_ok=True)

        for variant_name, mask_path in VARIANTS.items():
            out_path = os.path.join(out_identity_dir, f"{stem}_{variant_name}.jpg")
            done += 1
            if os.path.exists(out_path):
                continue
            try:
                FaceMasker(row["path"], mask_path, False, "hog", out_path).mask()
            except Exception as exc:
                print(f"skip {row['path']} ({variant_name}): {exc}")
            if done % 200 == 0:
                print(f"{done}/{total}")


if __name__ == "__main__":
    run()
