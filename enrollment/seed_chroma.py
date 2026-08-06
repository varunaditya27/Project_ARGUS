"""Seeds the demo gallery directly into ChromaDB, in the exact schema the backend's
recognition stack reads (collection argus_templates, ids {student_id}:{mask_type}).
Bypasses the backend's HTTP API - correct for 5,802 identities, wrong for one.
"""

import argparse
import csv
import os
import uuid

import chromadb
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNMASKED_PATH = os.path.join(BASE_DIR, "enrollment", "enrollment_embeddings.npz")
EVAL_PATH = os.path.join(BASE_DIR, "embeddings", "embeddings.npz")
IDENTITY_MAP_PATH = os.path.join(BASE_DIR, "enrollment", "enrollment_identity_map.csv")
DEFAULT_CHROMA_PATH = os.path.join(BASE_DIR, "backend", ".chroma")

COLLECTION_NAME = "argus_templates"
UNMASKED_TEMPLATE = "UNMASKED"
MODEL_VERSION = "arcface/w600k_r50.onnx"
DEMO_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "argus-demo-gallery")
BATCH_SIZE = 500


# same uuid every time this identity is seeded, so re-running never creates duplicates
def identity_uuid(dataset, identity):
    return uuid.uuid5(DEMO_NAMESPACE, f"{dataset}:{identity}")


# the 5,802-identity unmasked gallery: one UNMASKED template per person
def unmasked_rows():
    data = np.load(UNMASKED_PATH)
    rows = []
    for dataset, identity, embedding in zip(data["dataset"], data["identity"], data["embedding"]):
        student_id = identity_uuid(dataset, identity)
        rows.append((student_id, UNMASKED_TEMPLATE, embedding, dataset, identity))
    return rows


# masked variants for the 400-identity eval subset, added as extra templates for those same people.
# an identity can have several source photos masked with the same mask_type - keep one per
# (identity, mask_type), same tie-break convention as evaluation/eval_sets.py's gallery picking
def masked_rows():
    data = np.load(EVAL_PATH)
    masked = data["is_masked"] == 1
    chosen = {}
    for dataset, identity, mask_type, path, embedding in zip(
        data["dataset"][masked], data["identity"][masked], data["mask_type"][masked],
        data["path"][masked], data["embedding"][masked],
    ):
        dataset_name = "lfw" if dataset == "lfw_subset" else dataset
        key = (dataset_name, identity, mask_type)
        if key not in chosen or path < chosen[key][0]:
            chosen[key] = (path, embedding)

    rows = []
    for (dataset_name, identity, mask_type), (_, embedding) in chosen.items():
        student_id = identity_uuid(dataset_name, identity)
        rows.append((student_id, mask_type, embedding, dataset_name, identity))
    return rows


# writes student_id -> real name/dataset, since the demo gallery has no Postgres students rows to resolve this
def write_identity_map(rows):
    seen = {}
    for student_id, _, _, dataset, identity in rows:
        seen[str(student_id)] = (dataset, identity)
    with open(IDENTITY_MAP_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "dataset", "identity"])
        for student_id, (dataset, identity) in sorted(seen.items()):
            writer.writerow([student_id, dataset, identity])


def seed(chroma_path):
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    rows = unmasked_rows() + masked_rows()
    write_identity_map(rows)

    for start in range(0, len(rows), BATCH_SIZE):
        chunk = rows[start:start + BATCH_SIZE]
        collection.upsert(
            ids=[f"{student_id}:{mask_type}" for student_id, mask_type, _, _, _ in chunk],
            embeddings=[embedding.tolist() for _, _, embedding, _, _ in chunk],
            metadatas=[{"student_id": str(student_id), "mask_type": mask_type, "model_version": MODEL_VERSION}
                       for student_id, mask_type, _, _, _ in chunk],
        )
        print(f"{min(start + BATCH_SIZE, len(rows))}/{len(rows)} templates seeded")

    print(f"done: {collection.count()} templates in '{COLLECTION_NAME}' at {chroma_path}")
    print(f"identity map written to {IDENTITY_MAP_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chroma-path", default=DEFAULT_CHROMA_PATH)
    args = parser.parse_args()
    seed(args.chroma_path)
