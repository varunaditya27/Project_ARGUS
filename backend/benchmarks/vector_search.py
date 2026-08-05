"""Identification latency at gallery scale ("can we search 20 000 people fast?").

Two sources, and the difference matters:

``--source real`` (default)
    Queries the configured ARGUS collection with vectors taken from that same
    collection. Requires an enrolled gallery, so it only works once the ArcFace
    adapter and enrollment exist. This is the number to publish.

``--source random``
    Writes random unit vectors into a **throwaway** ``argus_bench_*`` collection
    to measure index latency alone. It reports latency and nothing else: random
    vectors say nothing about recognition accuracy, so this mode refuses to emit
    any accuracy figure and labels every result accordingly.

Rank-1 / ROC / TAR@FAR belong to the evaluation pipeline with real labelled
probes, not to this backend benchmark.

Usage::

    $env:ARGUS_CHROMA_MODE = "persistent"; $env:ARGUS_CHROMA_PATH = "./.chroma"
    python -m benchmarks.vector_search --source random --gallery 20000 --queries 200
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import numpy as np

from app.core.config import Settings
from app.recognition.adapters.chroma_index import ChromaTemplateIndex
from app.recognition.factory import build_template_index
from benchmarks._report import BenchmarkReport, timed

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RANDOM_DISCLAIMER = "latency only - random vectors, no accuracy meaning"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("real", "random"), default="real")
    parser.add_argument("--gallery", type=int, default=20_000, help="Templates in the gallery.")
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--k", type=int, nargs="+", default=[5, 10, 25])
    parser.add_argument("--upsert-chunk", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20_260_806)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    return parser.parse_args()


def unit_vectors(count: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    vectors = rng.standard_normal((count, dim), dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


async def build_random_gallery(
    settings: Settings, args: argparse.Namespace, rng: np.random.Generator
) -> tuple[ChromaTemplateIndex, np.ndarray]:
    collection = f"argus_bench_{uuid.uuid4().hex[:8]}"
    index = ChromaTemplateIndex(
        collection_name=collection,
        persist_path=str(settings.chroma_path) if settings.chroma_path else None,
        host=settings.chroma_host,
        port=settings.chroma_port,
    )
    vectors = unit_vectors(args.gallery, settings.embedding_dim, rng)
    for start in range(0, args.gallery, args.upsert_chunk):
        chunk = vectors[start : start + args.upsert_chunk]
        await index.upsert(
            uuid.uuid4(),
            {f"bench_{start + offset}": row for offset, row in enumerate(chunk)},
            model_version="benchmark-random",
        )
    print(f"Created throwaway collection {collection} with {args.gallery} random vectors.")
    return index, vectors


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.chroma_mode == "disabled":
        sys.exit(
            "ChromaDB is not configured. Set ARGUS_CHROMA_MODE=persistent (with "
            "ARGUS_CHROMA_PATH) or =http (with ARGUS_CHROMA_HOST/PORT)."
        )

    rng = np.random.default_rng(args.seed)
    report = BenchmarkReport(
        title="ARGUS recognition tier - vector search latency",
        parameters={
            "source": args.source,
            "requested_gallery": args.gallery,
            "queries": args.queries,
            "embedding_dim": settings.embedding_dim,
            "chroma_mode": settings.chroma_mode,
            "collection": settings.chroma_collection,
        },
    )

    if args.source == "real":
        index = build_template_index(settings)
        if not index.status().configured:
            sys.exit("The configured template index is disabled.")
        gallery_size = await index.count()
        report.parameters["actual_gallery"] = gallery_size
        if gallery_size < args.gallery:
            sys.exit(
                f"The collection holds {gallery_size} templates but the benchmark asked for "
                f"{args.gallery}. Enroll more identities or lower --gallery. Random probe "
                "vectors are not substituted, because that would not measure real search."
            )
        sys.exit(
            "Real-source probing needs enrolled embeddings to query with. Implement the ArcFace "
            "adapter and enroll a gallery first, then re-run; until then use --source random for "
            "latency-only numbers."
        )

    print(f"[!] {RANDOM_DISCLAIMER.upper()}")
    index, probe_pool = await build_random_gallery(settings, args, rng)
    report.parameters["collection"] = index.status().detail
    report.parameters["actual_gallery"] = await index.count()

    for k in args.k:
        measurement = report.measure(f"k-NN search (k={k})", items=1, notes=RANDOM_DISCLAIMER)
        for query_index in range(args.queries):
            probe = probe_pool[query_index % len(probe_pool)]
            with timed(measurement):
                await index.search([probe], k)

    json_path, md_path = report.write(args.output, f"vector-search-{args.source}")
    print(report.to_markdown())
    print(f"Written: {json_path}\n         {md_path}")
    if args.source == "random":
        print(
            "\nReminder: drop the throwaway argus_bench_* collection when you are done, and do "
            "not quote these numbers as accuracy."
        )
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
