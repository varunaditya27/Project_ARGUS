"""Filters LFW down to identities with >=2 images and symlinks them into LFW_subset/."""

import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LFW_SRC = os.path.join(BASE_DIR, "datasets", "raw", "LFW", "lfw-deepfunneled", "lfw-deepfunneled")
SUBSET_DIR = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset")
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "LFW_subset_manifest.csv")

MIN_IMAGES_PER_IDENTITY = 2


# returns (name, image_list) pairs for every identity with enough images
def list_identities_with_min_images(src_dir, min_images):
    identities = []
    for name in sorted(os.listdir(src_dir)):
        identity_dir = os.path.join(src_dir, name)
        if not os.path.isdir(identity_dir):
            continue
        images = sorted(f for f in os.listdir(identity_dir) if f.lower().endswith(".jpg"))
        if len(images) >= min_images:
            identities.append((name, images))
    return identities


# symlinks each kept image into LFW_subset/ and builds the manifest rows
def build_subset(identities):
    os.makedirs(SUBSET_DIR, exist_ok=True)
    rows = []
    for identity, images in identities:
        out_dir = os.path.join(SUBSET_DIR, identity)
        os.makedirs(out_dir, exist_ok=True)
        for image_name in images:
            src_path = os.path.join(LFW_SRC, identity, image_name)
            link_path = os.path.join(out_dir, image_name)
            if not os.path.exists(link_path):
                os.symlink(src_path, link_path)
            rows.append({"identity": identity, "filename": image_name, "path": link_path})
    return rows


# writes the identity/filename/path rows out as csv
def write_manifest(rows):
    with open(MANIFEST_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["identity", "filename", "path"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    identities = list_identities_with_min_images(LFW_SRC, MIN_IMAGES_PER_IDENTITY)
    rows = build_subset(identities)
    write_manifest(rows)
    print(f"identities: {len(identities)}")
    print(f"images: {len(rows)}")
    print(f"subset written to: {SUBSET_DIR}")
    print(f"manifest written to: {MANIFEST_PATH}")
