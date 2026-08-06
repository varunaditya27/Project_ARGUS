"""Shared measurement + reporting helpers for the benchmark scripts.

No numbers are ever hard-coded or checked into the docs: every table in
``docs/benchmarks.md`` is filled in from a run on the machine being reported.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Measurement:
    name: str
    #: Wall-clock durations in milliseconds, one per repetition.
    samples: list[float] = field(default_factory=list)
    items: int = 0
    notes: str = ""

    def add(self, milliseconds: float) -> None:
        self.samples.append(milliseconds)

    def summary(self) -> dict[str, Any]:
        ordered = sorted(self.samples)
        if not ordered:
            return {"name": self.name, "runs": 0, "notes": self.notes}
        total_ms = sum(ordered)
        return {
            "name": self.name,
            "runs": len(ordered),
            "items": self.items,
            "mean_ms": round(statistics.fmean(ordered), 3),
            "p50_ms": round(_percentile(ordered, 0.50), 3),
            "p95_ms": round(_percentile(ordered, 0.95), 3),
            "max_ms": round(ordered[-1], 3),
            "throughput_items_per_s": (
                round(self.items * len(ordered) / (total_ms / 1000.0), 1) if total_ms else None
            ),
            "notes": self.notes,
        }


def _percentile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@contextmanager
def timed(measurement: Measurement):
    started = time.perf_counter()
    try:
        yield
    finally:
        measurement.add((time.perf_counter() - started) * 1000.0)


@dataclass(slots=True)
class BenchmarkReport:
    title: str
    parameters: dict[str, Any]
    measurements: list[Measurement] = field(default_factory=list)

    def measure(self, name: str, *, items: int = 0, notes: str = "") -> Measurement:
        measurement = Measurement(name=name, items=items, notes=notes)
        self.measurements.append(measurement)
        return measurement

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "processor": platform.processor() or "unknown",
            },
            "parameters": self.parameters,
            "results": [m.summary() for m in self.measurements],
        }

    def to_markdown(self) -> str:
        payload = self.to_dict()
        lines = [
            f"# {payload['title']}",
            "",
            f"- Generated: `{payload['generated_at']}`",
            f"- Python: `{payload['environment']['python']}`",
            f"- Platform: `{payload['environment']['platform']}`",
            "",
            "## Parameters",
            "",
            "| Parameter | Value |",
            "|---|---|",
            *(f"| {key} | `{value}` |" for key, value in payload["parameters"].items()),
            "",
            "## Results",
            "",
            "| Measurement | Runs | Items | Mean (ms) | p50 (ms) | p95 (ms) | Items/s | Notes |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for result in payload["results"]:
            if not result.get("runs"):
                lines.append(f"| {result['name']} | 0 | - | - | - | - | - | {result['notes']} |")
                continue
            lines.append(
                "| {name} | {runs} | {items} | {mean_ms} | {p50_ms} | {p95_ms} | "
                "{throughput_items_per_s} | {notes} |".format(**result)
            )
        return "\n".join(lines) + "\n"

    def write(self, output_dir: Path, slug: str) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        json_path = output_dir / f"{slug}-{stamp}.json"
        md_path = output_dir / f"{slug}-{stamp}.md"
        json_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        return json_path, md_path
