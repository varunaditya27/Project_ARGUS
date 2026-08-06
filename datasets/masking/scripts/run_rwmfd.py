"""Runs the vendored RWMFD tool over LFW_reduced_manifest.csv, writing blue/black variants to LFW_subset_rwmfd/."""

import csv
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RWMFD_DIR = os.path.join(BASE_DIR, "datasets", "masking", "rwmfd")
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "LFW_reduced_manifest.csv")
OUT_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset_rwmfd")


# loads the reduced-scope manifest rows to run RWMFD over
def read_manifest(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# applies both mask variants to every image, skipping ones already done. wearmask is imported here,
# not at module level, since it only exists once RWMFD_DIR is added to sys.path
def run():
    sys.path.insert(0, RWMFD_DIR)
    from wearmask import FaceMasker, BLUE_IMAGE_PATH, BLACK_IMAGE_PATH

    variants = {"rwmfd_blue": BLUE_IMAGE_PATH, "rwmfd_black": BLACK_IMAGE_PATH}
    rows = read_manifest(MANIFEST_PATH)
    total = len(rows) * len(variants)
    done = 0
    for row in rows:
        identity = row["identity"]
        stem = os.path.splitext(row["filename"])[0]
        out_identity_dir = os.path.join(OUT_DIR, identity)
        os.makedirs(out_identity_dir, exist_ok=True)

        for variant_name, mask_path in variants.items():
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
