"""Runs the vendored MaskTheFace tool over LFW_subset/, writing all 9 mask variants to LFW_subset_masked/."""

import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.dirname(BASE_DIR)
MASKTHEFACE_DIR = os.path.join(BASE_DIR, "datasets", "masking", "masktheface")
SUBSET_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset")
PYTHON = sys.executable


# --color "" is required: MaskTheFace's own default tints every mask blue regardless of its template
def run():
    if not os.path.isdir(SUBSET_DIR):
        raise SystemExit(f"{SUBSET_DIR} not found, run select_subset.py first")

    cmd = [
        PYTHON, "mask_the_face.py",
        "--path", SUBSET_DIR,
        "--mask_type", "all",
        "--color", "",
    ]
    subprocess.run(cmd, cwd=MASKTHEFACE_DIR, check=True)


if __name__ == "__main__":
    run()
