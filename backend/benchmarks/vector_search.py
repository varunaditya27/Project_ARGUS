"""k-NN latency of the template index at gallery scale (default: 20 000 vectors).

Random unit vectors are written into a throwaway ``argus_bench_*`` collection and
queried back. This measures index latency and nothing else - random vectors say
nothing about recognition accuracy, so no accuracy figure is produced here.
Rank-1, ROC and TAR@FAR belong to the evaluation pipeline with labelled probes.

Usage::

    $env:ARGUS_CHROMA_MODE = "persistent"; $env:ARGUS_CHROMA_PATH = "./.chroma"
    python -m benchmarks.vector_search --gallery 20000 --queries 200
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import numpy as np

from app.core.config import Settings
from app.recognition.adapters.chroma import ChromaTemplateIndex
from benchmarks._report import BenchmarkReport, timed

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DISCLAIMER = "latency only - random vectors, no accuracy meaning"


def parse_args() -> argparse.Namespace:
    # Command line for the benchmark.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gallery", type=int, default=20_000, help="Templates in the gallery.")
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--k", type=int, nargs="+", default=[5, 10, 25])
    parser.add_argument("--upsert-chunk", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20_260_806)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    return parser.parse_args()


def unit_vectors(count: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    # L2-normalised rows, matching what ArcFace produces.
    vectors = rng.standard_normal((count, dim), dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


async def build_gallery(
    settings: Settings, args: argparse.Namespace, rng: np.random.Generator
) -> tuple[ChromaTemplateIndex, np.ndarray]:
    # Fill a throwaway collection so the real one is never polluted.
    index = ChromaTemplateIndex(
        collection_name=f"argus_bench_{uuid.uuid4().hex[:8]}",
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
    return index, vectors


async def run(args: argparse.Namespace) -> int:
    # Fill the gallery, then time k-NN search at every requested k.
    settings = Settings()
    if settings.chroma_mode == "disabled":
        sys.exit(
            "ChromaDB is not configured. Set ARGUS_CHROMA_MODE=persistent (with "
            "ARGUS_CHROMA_PATH) or =http (with ARGUS_CHROMA_HOST/PORT)."
        )

    print(f"[!] {DISCLAIMER.upper()}")
    rng = np.random.default_rng(args.seed)
    index, probes = await build_gallery(settings, args, rng)
    report = BenchmarkReport(
        title="ARGUS recognition tier - vector search latency",
        parameters={
            "gallery": await index.count(),
            "queries": args.queries,
            "embedding_dim": settings.embedding_dim,
            "chroma_mode": settings.chroma_mode,
            "collection": index.status().detail,
        },
    )

    for k in args.k:
        measurement = report.measure(f"k-NN search (k={k})", items=1, notes=DISCLAIMER)
        for query in range(args.queries):
            probe = probes[query % len(probes)]
            with timed(measurement):
                await index.search([probe], k)

    json_path, md_path = report.write(args.output, "vector-search")
    print(report.to_markdown())
    print(f"Written: {json_path}\n         {md_path}")
    print("\nDrop the throwaway argus_bench_* collection when you are done.")
    return 0


def main() -> int:
    # Entry point.
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
