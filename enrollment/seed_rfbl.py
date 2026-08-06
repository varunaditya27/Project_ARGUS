"""Seeds RFBL templates (from generate_rfbl_embeddings_colab.ipynb's output) into the same
ChromaDB gallery as seed_chroma.py, in the same schema (collection argus_templates,
ids {student_id}:{mask_type}). Separate script, not merged into seed_chroma.py, since RFBL
is a distinct organizer-provided dataset seeded on its own schedule, not part of the
5,802-identity LFW/MFR2 gallery build.
"""

import argparse
import csv
import os
import uuid

import chromadb
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_PATH = os.path.join(BASE_DIR, "enrollment", "rfbl_embeddings.npz")
IDENTITY_MAP_PATH = os.path.join(BASE_DIR, "enrollment", "rfbl_identity_map.csv")
DEFAULT_CHROMA_PATH = os.path.join(BASE_DIR, "backend", ".chroma")

COLLECTION_NAME = "argus_templates"
MODEL_VERSION = "arcface/w600k_r50.onnx"
RFBL_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "argus-rfbl-gallery")
BATCH_SIZE = 500


# same uuid every time this identity is seeded, so re-running never creates duplicates
def identity_uuid(identity):
    return uuid.uuid5(RFBL_NAMESPACE, f"rfbl:{identity}")


# one row per (identity, mask_type) - the notebook already keeps exactly one embedding per pair
def rows_from_embeddings(data):
    rows = []
    for identity, mask_type, embedding in zip(data["identity"], data["mask_type"], data["embedding"]):
        student_id = identity_uuid(identity)
        rows.append((student_id, mask_type, embedding, identity))
    return rows


# writes student_id -> real RFBL identity name, since this gallery has no Postgres students rows either
def write_identity_map(rows):
    seen = {}
    for student_id, _, _, identity in rows:
        seen[str(student_id)] = identity
    with open(IDENTITY_MAP_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "identity"])
        for student_id, identity in sorted(seen.items()):
            writer.writerow([student_id, identity])


def seed(chroma_path):
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    rows = rows_from_embeddings(np.load(EMBEDDINGS_PATH))
    write_identity_map(rows)

    for start in range(0, len(rows), BATCH_SIZE):
        chunk = rows[start:start + BATCH_SIZE]
        collection.upsert(
            ids=[f"{student_id}:{mask_type}" for student_id, mask_type, _, _ in chunk],
            embeddings=[embedding.tolist() for _, _, embedding, _ in chunk],
            metadatas=[{"student_id": str(student_id), "mask_type": mask_type, "model_version": MODEL_VERSION}
                       for student_id, mask_type, _, _ in chunk],
        )
        print(f"{min(start + BATCH_SIZE, len(rows))}/{len(rows)} templates seeded")

    print(f"done: {collection.count()} templates in '{COLLECTION_NAME}' at {chroma_path}")
    print(f"identity map written to {IDENTITY_MAP_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chroma-path", default=DEFAULT_CHROMA_PATH)
    args = parser.parse_args()
    seed(args.chroma_path)
