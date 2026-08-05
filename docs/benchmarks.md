# Benchmarks

The system has to identify one person among a 20 000 person cohort and keep an
attendance register up to date while doing it. This document states what is
measured, how to reproduce it, and the numbers from the reference run.

Two tiers are measured separately because they fail for different reasons:

| Tier | Question | Script |
|---|---|---|
| Attendance / database | Can PostgreSQL absorb continuous attendance writes and derive absence for 20 000 students? | `backend/benchmarks/db_scale.py` |
| Recognition / vector search | How long does a k-NN identification take against a 20 000 template gallery? | `backend/benchmarks/vector_search.py` |

**What is not measured here.** Rank-1 accuracy, ROC-AUC, TAR@FAR and the
masked-to-unmasked gap need real labelled probes and the trained model; they
belong to the evaluation pipeline in `docs/design.md`. No accuracy number is
produced, estimated or implied by these scripts.

---

## 1. Reproducing

```bash
cd backend
pip install -e ".[dev,recognition]"
```

### Attendance tier

Point the harness at a throwaway database - it drops and recreates every table
and refuses to start if the DSN equals `ARGUS_DATABASE_URL`:

```bash
export ARGUS_BENCH_DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus_bench
python -m benchmarks.db_scale --students 20000 --intervals 20 --interval-batch 500 --yes
```

The roster it generates is obvious placeholder load data (`BENCH-000001` names,
`*.invalid` image URLs). It exists only inside the benchmark database.

### Recognition tier

```bash
export ARGUS_CHROMA_MODE=persistent
export ARGUS_CHROMA_PATH=./.chroma-bench
python -m benchmarks.vector_search --source random --gallery 20000 --queries 200 --k 5 10 25
```

`--source random` fills a throwaway `argus_bench_*` collection with random unit
vectors and reports **latency only** - random vectors carry no identity, so the
script refuses to emit any accuracy figure. `--source real` (the default) queries
the live gallery instead and will be usable once the ArcFace adapter and
enrollment exist.

Both scripts write timestamped JSON + Markdown into `backend/benchmarks/results/`
(git-ignored). Re-run them on the deployment hardware; the numbers below describe
one machine, not a guarantee.

---

## 2. Reference run

Development laptop, Windows 11, PostgreSQL 16 in Docker, ChromaDB 1.5.9
persistent, Python 3.11. Everything on one host, so client, server and disk
compete for the same CPU - production hardware should do better.

### 2.1 Attendance tier - 20 000 students

Parameters: 20 000 students in one classroom, 20 capture intervals, 500
recognitions per interval, insert chunk 2 000. Result: 7 930 distinct students
recognised, 12 070 marked absent at close.

| Measurement | Runs | Items | Mean | p50 | p95 | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Roster import (bulk INSERT) | 1 | 20 000 rows | 738 ms | - | - | ~27 100 rows/s |
| Capture interval upsert | 20 | 500 observations | 75.9 ms | 72.6 ms | 94.4 ms | ~6 600 observations/s |
| Register page (keyset, 50 rows) | 10 | 50 rows | 11.0 ms | 10.0 ms | 14.7 ms | - |
| Attendance summary | 10 | 1 query | 2.7 ms | 2.5 ms | 4.3 ms | - |
| Session close (absence pass) | 1 | 20 000 roster | 666 ms | - | - | ~30 000 rows/s |

How to read this:

- **Capture interval upsert.** One `INSERT ... ON CONFLICT DO UPDATE` statement
  carries a whole interval. With the default 15 s interval, 500 recognitions cost
  ~76 ms of database time every 15 s - about 0.5 % duty cycle, so the attendance
  tier is nowhere near being the bottleneck.
- **Session close.** Deriving absence for a 20 000 student roster is a single
  anti-joined `INSERT ... SELECT`; 666 ms end to end, and it scales with roster
  size rather than with the number of detections.
- **Register page.** Constant per page because pagination is keyset-based on
  `roll_no`; page 400 costs the same as page 1.

### 2.2 Recognition tier - 20 000 template gallery

Parameters: 20 000 templates of 512 dimensions, cosine space, 200 queries per k.

| k | Runs | Mean | p50 | p95 |
|---:|---:|---:|---:|---:|
| 5 | 200 | 2.25 ms | 2.15 ms | 3.15 ms |
| 10 | 200 | 2.24 ms | 2.01 ms | 3.51 ms |
| 25 | 200 | 2.61 ms | 2.33 ms | 3.81 ms |

Latency only (random vectors). k barely matters at this gallery size, so
`ARGUS_CHROMA_SEARCH_K` can be raised for better identity grouping without a
latency penalty. At ~2 ms per probe, search is not what limits the live pipeline;
detection and embedding will be.

Note that a 20 000 **student** gallery holds more than 20 000 **templates** -
enrollment stores one unmasked template plus one per mask variant, so seven
templates per student at the default configuration. Re-run with
`--gallery 140000` to size that case.

---

## 3. Interpreting a re-run

- Compare p95, not mean - the mean hides pauses.
- Keep `--seed` fixed so two runs see the same load pattern.
- If the interval upsert degrades faster than linearly with
  `--interval-batch`, check that `ARGUS_CAPTURE_FLUSH_CHUNK_SIZE` still splits
  the work into statements PostgreSQL can plan quickly.
- If the absence pass degrades, confirm `ix_students_class_id_roll_no` exists;
  without it the anti-join falls back to a sequential scan.
