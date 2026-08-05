"""Attendance throughput at cohort scale (default: 20 000 students).

What this answers: can the attendance tier keep up while a 20 000 student cohort
is being recognised, and how long does deriving absence at session close take.

Load data is generated **only** for this run, **only** in the dedicated benchmark
database (``ARGUS_BENCH_DATABASE_URL``), and every generated row is obviously
placeholder data (``BENCH-<n>`` names, ``*.invalid`` image URLs). It never touches
the application database and it makes no claim about recognition accuracy - see
``vector_search.py`` and the evaluation pipeline for the recognition tier.

Usage::

    $env:ARGUS_BENCH_DATABASE_URL = "postgresql+asyncpg://argus:argus@localhost:5432/argus_bench"
    python -m benchmarks.db_scale --students 20000 --intervals 20 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import random
import sys
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.collections import chunked
from app.core.config import Settings
from app.db.base import Base
from app.db.database import Database
from app.db.models import Classroom
from app.domain.enums import SessionStatus
from app.domain.observation import Observation
from app.repositories.attendance import AttendanceRepository
from app.repositories.session import ClassSessionRepository
from app.repositories.student import StudentRepository
from benchmarks._report import BenchmarkReport, timed

RESULTS_DIR = Path(__file__).resolve().parent / "results"
PLACEHOLDER_IMAGE = "https://benchmark.invalid/placeholder/{roll_no}.jpg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=20_000)
    parser.add_argument(
        "--intervals", type=int, default=20, help="Number of capture intervals to simulate."
    )
    parser.add_argument(
        "--interval-batch",
        type=int,
        default=500,
        help="Students recognised per capture interval.",
    )
    parser.add_argument(
        "--insert-chunk", type=int, default=2_000, help="Rows per multi-row INSERT."
    )
    parser.add_argument("--seed", type=int, default=20_260_806)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that the benchmark database may be dropped and recreated.",
    )
    return parser.parse_args()


def resolve_dsn() -> str:
    dsn = os.getenv("ARGUS_BENCH_DATABASE_URL")
    if not dsn:
        sys.exit(
            "ARGUS_BENCH_DATABASE_URL is not set. Point it at a throwaway database; the "
            "benchmark drops and recreates every table."
        )
    if dsn == os.getenv("ARGUS_DATABASE_URL"):
        sys.exit("Refusing to run: ARGUS_BENCH_DATABASE_URL equals ARGUS_DATABASE_URL.")
    return dsn


async def reset_schema(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


async def seed_roster(
    session: AsyncSession, *, students: int, chunk: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    classroom = Classroom(
        class_name="BENCH-COHORT",
        department="BENCHMARK",
        semester=1,
        strength=students,
    )
    session.add(classroom)
    await session.flush()

    repository = StudentRepository(session)
    student_ids = [uuid.uuid4() for _ in range(students)]
    rows = [
        {
            "student_id": student_id,
            "student_name": f"BENCH-{roll_no:06d}",
            "roll_no": roll_no,
            "class_id": classroom.class_id,
            "image_url": PLACEHOLDER_IMAGE.format(roll_no=roll_no),
        }
        for roll_no, student_id in enumerate(student_ids, start=1)
    ]
    for batch in chunked(rows, chunk):
        await repository.bulk_insert(batch)
    return classroom.class_id, student_ids


async def run(args: argparse.Namespace) -> int:
    dsn = resolve_dsn()
    if not args.yes:
        sys.exit("Re-run with --yes to confirm the benchmark database will be recreated.")

    settings = Settings(_env_file=None, database_url=dsn)  # type: ignore[arg-type]
    database = Database(dsn, settings)
    rng = random.Random(args.seed)

    report = BenchmarkReport(
        title="ARGUS attendance tier - database scale benchmark",
        parameters={
            "students": args.students,
            "intervals": args.intervals,
            "interval_batch": args.interval_batch,
            "insert_chunk": args.insert_chunk,
            "seed": args.seed,
            "data": "synthetic placeholder roster (benchmark database only)",
            "measures": "database throughput only - no recognition accuracy is implied",
        },
    )

    roster_insert = report.measure(
        "Roster import", items=args.students, notes="multi-row INSERT, chunked"
    )
    interval_upsert = report.measure(
        "Capture interval upsert",
        items=args.interval_batch,
        notes="one INSERT ... ON CONFLICT per interval",
    )
    register_page = report.measure(
        "Register page (keyset, 50 rows)", items=50, notes="attendance JOIN students"
    )
    summary_query = report.measure("Attendance summary", items=1, notes="filtered COUNT(*)")
    close_pass = report.measure(
        "Session close (absence pass)",
        items=args.students,
        notes="anti-joined INSERT ... SELECT + status flip",
    )

    try:
        await reset_schema(database)

        async with database.session() as db_session:
            with timed(roster_insert):
                class_id, student_ids = await seed_roster(
                    db_session, students=args.students, chunk=args.insert_chunk
                )

        async with database.session() as db_session:
            class_session = await ClassSessionRepository(db_session).create(
                class_id=class_id,
                subject="BENCH",
                faculty="BENCH",
                date=dt.date.today(),
                start_time=dt.time(9, 0),
                end_time=dt.time(10, 0),
                status=SessionStatus.ACTIVE,
            )
            session_id = class_session.session_id

        started_at = utc_now()
        for interval in range(args.intervals):
            sample = rng.sample(student_ids, min(args.interval_batch, len(student_ids)))
            observations = [
                Observation(
                    student_id=student_id,
                    confidence=round(rng.uniform(0.55, 0.95), 4),
                    observed_at=started_at + dt.timedelta(seconds=15 * interval),
                )
                for student_id in sample
            ]
            async with database.session() as db_session:
                repository = AttendanceRepository(db_session)
                with timed(interval_upsert):
                    await repository.upsert_present(session_id, observations)

        async with database.session() as db_session:
            repository = AttendanceRepository(db_session)
            cursor = None
            for _ in range(10):
                with timed(register_page):
                    rows = await repository.list_for_session(
                        session_id, status=None, after_roll_no=cursor, limit=50
                    )
                if not rows:
                    break
                cursor = rows[-1][2]
            for _ in range(10):
                with timed(summary_query):
                    await repository.counts_for_session(session_id)

        async with database.session() as db_session:
            repository = AttendanceRepository(db_session)
            sessions = ClassSessionRepository(db_session)
            with timed(close_pass):
                absent = await repository.insert_absentees(session_id, utc_now())
                await sessions.mark_closed(session_id)
            counts = await repository.counts_for_session(session_id)

        close_pass.notes += f"; absent_marked={absent}"
        report.parameters["present_rows"] = counts.present
        report.parameters["absent_rows"] = counts.absent
    finally:
        await database.dispose()

    json_path, md_path = report.write(args.output, "db-scale")
    print(report.to_markdown())
    print(f"Written: {json_path}\n         {md_path}")
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
