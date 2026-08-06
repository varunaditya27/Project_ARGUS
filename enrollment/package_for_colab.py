"""Zips just the images listed in enrollment_manifest.csv, flat, for upload to Colab (~5,802 files, ~70MB)."""

import csv
import os
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "enrollment_manifest.csv")
OUT_ZIP_PATH = os.path.join(BASE_DIR, "enrollment", "enrollment_images.zip")


# renames each file to dataset_identity_filename so 5,802 files can sit flat in one zip with no collisions
def archive_name(row):
    return f"{row['dataset']}_{row['identity']}_{row['filename']}"


def run():
    with open(MANIFEST_PATH, newline="") as f:
        rows = list(csv.DictReader(f))

    with zipfile.ZipFile(OUT_ZIP_PATH, "w", zipfile.ZIP_STORED) as zf:
        for row in rows:
            zf.write(row["path"], arcname=archive_name(row))

    print(f"packaged {len(rows)} images into {OUT_ZIP_PATH}")
    print(f"zip size: {os.path.getsize(OUT_ZIP_PATH) / 1e6:.1f} MB")


if __name__ == "__main__":
    run()
