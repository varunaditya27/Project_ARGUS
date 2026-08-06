"""Local CPU fallback for generate_embeddings_colab.ipynb - same output schema, runs on this machine instead."""

import csv
import os

import numpy as np

from embeddings.generate import get_embedding

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "enrollment_manifest.csv")
OUT_PATH = os.path.join(BASE_DIR, "enrollment", "enrollment_embeddings.npz")


# reads the enrollment manifest rows
def read_manifest(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# embeds every row, printing progress every 200 images since this takes tens of minutes
def build():
    rows = read_manifest(MANIFEST_PATH)
    kept_rows, embeddings = [], []
    skipped = 0

    for i, row in enumerate(rows):
        embedding = get_embedding(row["path"])
        if embedding is None:
            skipped += 1
            continue
        kept_rows.append(row)
        embeddings.append(embedding)
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(rows)} processed, {skipped} skipped", flush=True)

    save(kept_rows, embeddings)
    print(f"done: {len(kept_rows)} embeddings saved, {skipped} skipped")


# writes dataset/identity/filename/embedding arrays, matching the Colab notebook's output schema
def save(rows, embeddings):
    np.savez_compressed(
        OUT_PATH,
        dataset=np.array([r["dataset"] for r in rows]),
        identity=np.array([r["identity"] for r in rows]),
        filename=np.array([r["filename"] for r in rows]),
        embedding=np.stack(embeddings).astype(np.float32),
    )


if __name__ == "__main__":
    build()
