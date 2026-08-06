"""Zips RFBL images + the vendored MaskTheFace tool (code + mask assets, no dlib model) for Colab upload.

Colab needs to run MaskTheFace itself this time (RFBL has no pre-masked variants yet, unlike
LFW/MFR2 which were masked locally in datasets/masking/). The dlib landmark model (~96MB) is
excluded - mask_the_face.py downloads it itself from dlib.net on first run, same as it would locally.
"""

import csv
import os
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "rfbl_manifest.csv")
MASKTHEFACE_DIR = os.path.join(BASE_DIR, "datasets", "masking", "masktheface")
OUT_ZIP_PATH = os.path.join(BASE_DIR, "enrollment", "rfbl_colab_bundle.zip")

SKIP_DIR_NAMES = {"dlib_models", "images", "__pycache__"}


# renames each file to just {identity}.ext (no identity has an underscore) so MaskTheFace's own
# output naming ({stem}_{mask_type}.ext) can be parsed back into (identity, mask_type) unambiguously
def archive_name(row):
    ext = os.path.splitext(row["filename"])[1]
    return f"{row['identity']}{ext}"


def add_images(zf):
    with open(MANIFEST_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        zf.write(row["path"], arcname=os.path.join("images", archive_name(row)))
    return len(rows)


# code + masks/, skipping the dlib model (downloaded on Colab) and any prior run's own images/ dir
def add_masktheface_tool(zf):
    count = 0
    for root, dirs, files in os.walk(MASKTHEFACE_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, MASKTHEFACE_DIR)
            zf.write(full_path, arcname=os.path.join("masktheface", rel_path))
            count += 1
    return count


def run():
    with zipfile.ZipFile(OUT_ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        image_count = add_images(zf)
        tool_file_count = add_masktheface_tool(zf)

    print(f"packaged {image_count} images + {tool_file_count} masktheface tool files")
    print(f"zip size: {os.path.getsize(OUT_ZIP_PATH) / 1e6:.1f} MB")
    print(f"written to: {OUT_ZIP_PATH}")


if __name__ == "__main__":
    run()
