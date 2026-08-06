"""Local CPU pipeline for RFBL: masks + embeds all 460 identities, same output schema
generate_rfbl_embeddings_colab.ipynb writes. RFBL is small enough (460 images, ~2,300
masked variants) that local CPU finishes in minutes - no need to wait on a Colab upload
round trip for this dataset, unlike the 5,802-identity LFW/MFR2 gallery.
"""

import csv
import os
import shutil
import subprocess
import sys

import numpy as np

from embeddings.generate import get_embedding

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "rfbl_manifest.csv")
FLAT_DIR = os.path.join(BASE_DIR, "datasets", "processed", "RFBL_flat")
MASKED_DIR = FLAT_DIR + "_masked"
MASKTHEFACE_DIR = os.path.join(BASE_DIR, "datasets", "masking", "masktheface")
OUT_PATH = os.path.join(BASE_DIR, "enrollment", "rfbl_embeddings.npz")

KEEP_MASK_TYPES = {"surgical", "surgical_blue", "N95", "KN95", "cloth"}


# renames every manifest row to {identity}.ext in one flat dir - no RFBL identity has an
# underscore (verified against the raw folder names), so MaskTheFace's own output naming
# ({stem}_{mask_type}.ext) parses back into (identity, mask_type) unambiguously
def flatten_images():
    if os.path.isdir(FLAT_DIR):
        shutil.rmtree(FLAT_DIR)
    os.makedirs(FLAT_DIR)
    with open(MANIFEST_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        ext = os.path.splitext(row["filename"])[1]
        shutil.copy(row["path"], os.path.join(FLAT_DIR, f"{row['identity']}{ext}"))
    return rows


# --color "" is the same fix as datasets/masking/scripts/run_masktheface.py (MaskTheFace's own
# default tints every mask the same blue otherwise). --detector scrfd is RFBL-specific: dlib's
# own HOG detector failed on 355/460 of these small (99-160px) images, verified directly;
# swapping in the same SCRFD detector the recognition pipeline already uses for small crops
# recovers them, without changing landmark prediction (still dlib's 68-point model)
def run_masktheface():
    cmd = [sys.executable, "mask_the_face.py", "--path", FLAT_DIR, "--mask_type", "all",
           "--color", "", "--detector", "scrfd"]
    subprocess.run(cmd, cwd=MASKTHEFACE_DIR, check=True)


# unmasked originals (UNMASKED) + the 5 kept mask type variants for every identity
def build_worklist():
    worklist = []
    for filename in sorted(os.listdir(FLAT_DIR)):
        identity = os.path.splitext(filename)[0]
        worklist.append({"identity": identity, "mask_type": "UNMASKED", "is_masked": 0,
                          "path": os.path.join(FLAT_DIR, filename)})
    for filename in sorted(os.listdir(MASKED_DIR)):
        stem = os.path.splitext(filename)[0]
        identity, mask_type = stem.split("_", 1)
        if mask_type not in KEEP_MASK_TYPES:
            continue
        worklist.append({"identity": identity, "mask_type": mask_type, "is_masked": 1,
                          "path": os.path.join(MASKED_DIR, filename)})
    return worklist


# embeds every worklist entry, printing progress every 200 images
def embed(worklist):
    kept, embeddings = [], []
    skipped = 0
    for i, item in enumerate(worklist):
        embedding = get_embedding(item["path"])
        if embedding is None:
            skipped += 1
            continue
        kept.append(item)
        embeddings.append(embedding)
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(worklist)} processed, {skipped} skipped", flush=True)
    print(f"done: {len(kept)} embeddings, {skipped} skipped")
    return kept, embeddings


def save(kept, embeddings):
    np.savez_compressed(
        OUT_PATH,
        dataset=np.array(["rfbl"] * len(kept)),
        identity=np.array([item["identity"] for item in kept]),
        mask_type=np.array([item["mask_type"] for item in kept]),
        is_masked=np.array([item["is_masked"] for item in kept]),
        path=np.array([item["path"] for item in kept]),
        embedding=np.stack(embeddings).astype(np.float32),
    )


if __name__ == "__main__":
    flatten_images()
    run_masktheface()
    worklist = build_worklist()
    print(f"{len(worklist)} images to embed")
    kept, embeddings = embed(worklist)
    save(kept, embeddings)
    print(f"saved to {OUT_PATH}")
