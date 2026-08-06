"""Reads enrollment_embeddings.npz (from Colab) and writes it into a local persistent ChromaDB collection."""

import argparse
import os

import chromadb
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EMBEDDINGS_PATH = os.path.join(BASE_DIR, "enrollment", "enrollment_embeddings.npz")
DEFAULT_CHROMA_DIR = os.path.join(BASE_DIR, "enrollment", "chroma_data")
COLLECTION_NAME = "enrollments"

# chromadb.add() rejects batches above this - stay comfortably under it
BATCH_SIZE = 500


# loads the Colab-generated npz: dataset, identity, filename, embedding arrays
def load_embeddings(path):
    data = np.load(path)
    return data["dataset"], data["identity"], data["filename"], data["embedding"]


# writes every row into the collection in batches, ids are dataset:identity so they're unique and stable
def seed(chroma_dir, embeddings_path):
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    dataset, identity, filename, embedding = load_embeddings(embeddings_path)
    ids = [f"{d}:{i}" for d, i in zip(dataset, identity)]
    metadatas = [{"dataset": d, "identity": i, "filename": f}
                 for d, i, f in zip(dataset, identity, filename)]

    for start in range(0, len(ids), BATCH_SIZE):
        end = start + BATCH_SIZE
        collection.add(
            ids=ids[start:end],
            embeddings=embedding[start:end].tolist(),
            metadatas=metadatas[start:end],
        )
        print(f"{min(end, len(ids))}/{len(ids)} seeded")

    print(f"done: {collection.count()} rows in collection '{COLLECTION_NAME}' at {chroma_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", default=DEFAULT_EMBEDDINGS_PATH)
    parser.add_argument("--chroma-dir", default=DEFAULT_CHROMA_DIR)
    args = parser.parse_args()
    seed(args.chroma_dir, args.embeddings)
