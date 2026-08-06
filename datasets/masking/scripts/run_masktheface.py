"""
Runs the vendored MaskTheFace tool over datasets/processed/LFW_subset/
with --mask_type all, which applies all 9 non-directional mask styles
(surgical, surgical_blue, surgical_green, N95, KN95, cloth, gas, empty,
inpaint) to every face in one dlib detection pass.

Output lands next to the input dir, as LFW_subset_masked/, mirroring the
identity subfolder structure. That's MaskTheFace's own convention
(args.write_path = args.path + "_masked"), not something we chose.

--color "" matters: mask_the_face.py's --color argparse default is a
non-empty hex string ("#0473e2"), and mask_face() in aux_functions.py
checks `if args.color:` rather than whether the user actually asked for
a color override - so left at its default, every mask template gets
tinted the same blue regardless of its native color, and "surgical" /
"surgical_blue" / "surgical_green" all render identically. Passing an
empty string makes that check falsy and restores each template's real
color.
"""

import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.dirname(BASE_DIR)
MASKTHEFACE_DIR = os.path.join(BASE_DIR, "datasets", "masking", "masktheface")
SUBSET_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset")
PYTHON = sys.executable


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
