"""Attendance throughput at cohort scale (default: 20 000 students).

Answers whether the attendance tier keeps up while a 20 000 student cohort is
being recognised, and how long deriving absence at session close takes.

Load data is generated only for this run and only in the dedicated benchmark
database (``ARGUS_BENCH_DATABASE_URL``). This measures database throughput; it
implies nothing about recognition accuracy.

Usage::

    $env:ARGUS_BENCH_DATABASE_URL = "postgresql+asyncpg://argus:argus@localhost:5432/argus_bench"
    python -m benchmarks.db_scale --students 20000 --intervals 20 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import random
import sys
from pathlib import Path

from app.core.config import Settings
from app.core.utils import utc_now
from app.db.session import Database
from app.domain import Observation
from app.repositories.attendance import AttendanceRepository
from app.repositories.session import ClassSessionRepository
from benchmarks._report import BenchmarkReport, timed
from benchmarks._seed import open_session, reset_schema, resolve_dsn, seed_roster

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    # Command line for the benchmark.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=20_000)
    parser.add_argument("--intervals", type=int, default=20)
    parser.add_argument("--interval-batch", type=int, default=500)
    parser.add_argument("--insert-chunk", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=20_260_806)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    parser.add_argument("--yes", action="store_true", help="Confirm the database is throwaway.")
    return parser.parse_args()


def build_report(args: argparse.Namespace) -> BenchmarkReport:
    # The five phases this benchmark times.
    report = BenchmarkReport(
        title="ARGUS attendance tier - database scale benchmark",
        parameters={
            "students": args.students,
            "intervals": args.intervals,
            "interval_batch": args.interval_batch,
            "seed": args.seed,
            "measures": "database throughput only - no recognition accuracy is implied",
        },
    )
    report.measure("Roster import", items=args.students, notes="chunked INSERT")
    report.measure(
        "Capture interval upsert", items=args.interval_batch, notes="one INSERT ... ON CONFLICT"
    )
    report.measure("Register page (keyset, 50 rows)", items=50)
    report.measure("Attendance summary", items=1, notes="filtered COUNT(*)")
    report.measure(
        "Session close (absence pass)", items=args.students, notes="anti-joined INSERT ... SELECT"
    )
    return report


async def run(args: argparse.Namespace) -> int:
    # Seed, capture, read and close, timing every phase.
    dsn = resolve_dsn()
    if not args.yes:
        sys.exit("Re-run with --yes to confirm the benchmark database will be recreated.")

    database = Database(dsn, Settings(_env_file=None, database_url=dsn))  # type: ignore[arg-type]
    rng = random.Random(args.seed)
    report = build_report(args)
    phases = {phase.name: phase for phase in report.measurements}

    try:
        await reset_schema(database)
        async with database.session() as db_session:
            with timed(phases["Roster import"]):
                class_id, student_ids = await seed_roster(
                    db_session, students=args.students, chunk=args.insert_chunk
                )
        session_id = await open_session(database, class_id)

        await capture(database, session_id, student_ids, args, rng, phases)
        await read_back(database, session_id, phases)
        counts, absent = await close(database, session_id, phases)

        phases["Session close (absence pass)"].notes += f"; absent_marked={absent}"
        report.parameters["present_rows"] = counts.present
        report.parameters["absent_rows"] = counts.absent
    finally:
        await database.dispose()

    json_path, md_path = report.write(args.output, "db-scale")
    print(report.to_markdown())
    print(f"Written: {json_path}\n         {md_path}")
    return 0


async def capture(database, session_id, student_ids, args, rng, phases) -> None:
    # Replay N capture intervals, each one a coalesced upsert.
    started_at = utc_now()
    for interval in range(args.intervals):
        observations = [
            Observation(
                student_id=student_id,
                confidence=round(rng.uniform(0.55, 0.95), 4),
                observed_at=started_at + dt.timedelta(seconds=15 * interval),
            )
            for student_id in rng.sample(student_ids, min(args.interval_batch, args.students))
        ]
        async with database.session() as db_session:
            with timed(phases["Capture interval upsert"]):
                await AttendanceRepository(db_session).upsert_present(session_id, observations)


async def read_back(database, session_id, phases) -> None:
    # Page through the register and re-run the summary query.
    async with database.session() as db_session:
        repository = AttendanceRepository(db_session)
        cursor = None
        for _ in range(10):
            with timed(phases["Register page (keyset, 50 rows)"]):
                rows = await repository.list_for_session(
                    session_id, status=None, after_roll_no=cursor, limit=50
                )
            if not rows:
                break
            cursor = rows[-1][2]
        for _ in range(10):
            with timed(phases["Attendance summary"]):
                await repository.counts_for_session(session_id)


async def close(database, session_id, phases):
    # Derive absence and flip the status, exactly as the API does.
    async with database.session() as db_session:
        repository = AttendanceRepository(db_session)
        with timed(phases["Session close (absence pass)"]):
            absent = await repository.insert_absentees(session_id, utc_now())
            await ClassSessionRepository(db_session).mark_closed(session_id)
        return await repository.counts_for_session(session_id), absent


def main() -> int:
    # Entry point.
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
