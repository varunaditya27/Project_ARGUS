"""Runs every image in full_manifest.csv through ArcFace and saves embeddings + metadata to embeddings.npz."""

import argparse
import csv
import os

import numpy as np

from embeddings.generate import get_embedding

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "datasets", "processed", "full_manifest.csv")
DEFAULT_OUT_PATH = os.path.join(BASE_DIR, "embeddings", "embeddings.npz")


# loads the manifest rows we need to embed
def read_manifest(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# builds a path -> embedding lookup from a previous run, used by --resume to skip work
def load_existing(out_path):
    if not os.path.exists(out_path):
        return {}
    data = np.load(out_path)
    paths = data["path"]
    embeddings = data["embedding"]
    return {p: e for p, e in zip(paths, embeddings)}


# embeds every manifest row not already in existing, then writes the combined result
def build(manifest_path, out_path, resume):
    rows = read_manifest(manifest_path)
    existing = load_existing(out_path) if resume else {}

    kept_rows = []
    embeddings = []
    skipped_no_face = 0

    for i, row in enumerate(rows):
        path = row["path"]
        if path in existing:
            embedding = existing[path]
        else:
            embedding = get_embedding(path)
            if embedding is None:
                skipped_no_face += 1
                continue

        kept_rows.append(row)
        embeddings.append(embedding)

        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(rows)} processed, {skipped_no_face} skipped (no face)")

    save(kept_rows, embeddings, out_path)
    print(f"done: {len(kept_rows)} embeddings saved, {skipped_no_face} skipped")


# writes rows + embeddings out as one compressed npz, arrays aligned by index
def save(rows, embeddings, out_path):
    np.savez_compressed(
        out_path,
        path=np.array([r["path"] for r in rows]),
        dataset=np.array([r["dataset"] for r in rows]),
        identity=np.array([r["identity"] for r in rows]),
        source_tool=np.array([r["source_tool"] for r in rows]),
        mask_type=np.array([r["mask_type"] for r in rows]),
        is_masked=np.array([int(r["is_masked"]) for r in rows]),
        embedding=np.stack(embeddings).astype(np.float32),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--out", default=DEFAULT_OUT_PATH)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    build(args.manifest, args.out, args.resume)
