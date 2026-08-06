# ARGUS Backend

FastAPI service for the Project ARGUS attendance system: classrooms, roster,
lecture sessions, interval attendance capture, absence derivation, and the
recognition endpoints that the vision stack plugs into.

- Schema contract: [`docs/db.md`](../docs/db.md) - mapped 1:1, no extra tables
- Setup and schema decisions: [`docs/database_setup.md`](../docs/database_setup.md)
- HTTP contract: [`docs/api_integration.md`](../docs/api_integration.md)
- Measured behaviour at 20 000 students: [`docs/benchmarks.md`](../docs/benchmarks.md)

---

## Quick start

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate     # source .venv/bin/activate on Unix
pip install -e ".[dev]"
cp .env.example .env                                # then fill in ARGUS_DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs. Without `ARGUS_DATABASE_URL` the service still
starts, and every database endpoint answers `503` naming the missing variable.

```bash
pytest                                              # unit tests
ARGUS_TEST_DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus_test pytest
ruff check . && ruff format --check .
```

---

## How attendance works

Attendance is taken **throughout** the lecture and absence is derived **once**,
when the lecture ends.

```text
ACTIVE session
  recognition MATCH -> capture buffer (coalesced per student)
                          | every ARGUS_CAPTURE_INTERVAL_SECONDS
                          v
                    one INSERT ... ON CONFLICT DO UPDATE   -> Present rows appear live
close
  flush the buffer -> INSERT ... SELECT ... WHERE NOT EXISTS -> Absent for the rest
                   -> status = CLOSED          (one transaction, row locked)
```

Design points behind that:

- **Coalescing.** Many detections of one student inside an interval become one
  row write. `max(confidence)`, `min(timestamp)` - the same rule in memory and in
  the SQL `GREATEST`/`LEAST`, so the result is identical regardless of how many
  workers or intervals were involved.
- **Set-based writes.** One statement per interval and one for the whole absence
  pass, so cost tracks roster size, not detection count. 20 000 students close in
  ~0.7 s (see the benchmarks).
- **The database validates.** The interval upsert joins `class_sessions` and
  `students`, so an observation for a closed session or a student outside the
  classroom is rejected in SQL rather than by a pre-flight SELECT.
- **Nothing is lost.** A failed flush requeues into the buffer instead of
  dropping attendance, and shutdown flushes one last time.

---

## Layout

```text
backend/
├── app/
│   ├── main.py                 FastAPI factory + lifespan
│   ├── container.py            composition root (pools, buffer, flusher, services)
│   ├── api/
│   │   ├── deps.py             typed dependency aliases
│   │   └── v1/routes/          system, classrooms, students, sessions, recognition
│   ├── attendance/
│   │   ├── buffer.py           per-interval coalescing
│   │   └── flusher.py          background interval writer
│   ├── core/                   settings, logging, errors, clock, helpers
│   ├── db/                     engine/session, models (docs/db.md), integrity mapping
│   ├── domain/                 status vocabularies, Observation
│   ├── recognition/
│   │   ├── ports.py            detector / embedder / mask synth / index protocols
│   │   ├── decision.py         MATCH | HUMAN_REVIEW | UNKNOWN policy (pure)
│   │   ├── alignment.py        ArcFace 5-point alignment
│   │   ├── factory.py          which adapter is wired in
│   │   └── adapters/           scrfd, arcface, mask_synthesis, chroma_index, placeholder
│   ├── repositories/           SQL: set-based upserts, keyset paging
│   ├── schemas/                request/response models
│   ├── services/               use cases, one transaction per operation
│   └── storage/                Cloudflare R2 upload for roster import
├── alembic/                    0001_initial_schema = docs/db.md
├── benchmarks/                 db_scale.py, vector_search.py
└── tests/
```

Layering is one-directional: `api -> services -> repositories -> db`, with
`recognition` reached only through the port protocols. No module imports a model
framework directly, which is why the whole attendance suite runs without
torch/insightface installed.

---

## Recognition status

The vision stack is implemented and runs on `onnxruntime` against the InsightFace
`buffalo_l` ONNX pack - no torch, no `insightface` package at serving time.

| Component | Adapter | Model |
|---|---|---|
| Detection + 5-point landmarks | `adapters/scrfd.py` | `det_10g.onnx` |
| Embedding (512-d, L2-normalised) | `adapters/arcface.py` | `w600k_r50.onnx` |
| Mask variants | `adapters/mask_synthesis.py` | none - geometric, in the aligned frame |
| Template index | `adapters/chroma_index.py` | ChromaDB, cosine |

```bash
pip install -e ".[recognition]"
export ARGUS_MODEL_ROOT=../models/buffalo_l
```

The weights are **not in the repository** - the pack is ~197 MB and
`w600k_r50.onnx` alone is over GitHub's 100 MB per-file limit, so `models/` is
git-ignored. Download the InsightFace `buffalo_l` pack and unpack it so the
repository root looks like this:

```text
models/buffalo_l/
├── det_10g.onnx        detection + 5 landmarks   (used)
├── w600k_r50.onnx      512-d embedding           (used)
├── 2d106det.onnx       dense landmarks           (not used - see below)
└── genderage.onnx      age/gender                (not used)
```

Models load lazily and are warmed at startup, so `GET /models` reports the truth
before the first request. Leave `ARGUS_MODEL_ROOT` unset and the placeholders in
`adapters/placeholder.py` stay active: they contain no model, no heuristic and no
fabricated output, and each call raises `503` naming the missing configuration.

Two files in the pack are **not used**: `2d106det.onnx` (dense landmarks - the
mask synthesiser works in the aligned canonical frame, where the geometry is
already known, so it needs no per-face landmarks) and `genderage.onnx` (not an
attendance concern). `ARGUS_LANDMARK_MODEL_PATH` is wired through config for the
day a mask synthesiser wants it.

**Thresholds are still `null`**, which is the one thing standing between this and
automatic attendance. Until all three are set, `decide()` cannot return `MATCH`,
so nothing is auto-marked - the API returns `HUMAN_REVIEW` with that reason
instead of inventing a threshold. See `docs/benchmarks.md` section 4.

### Adding or replacing an adapter

1. Add a class satisfying the protocol in `app/recognition/ports.py`.
2. Register it in `build_recognition_stack()` in `app/recognition/factory.py`.
3. Add its runtime dependency to the `recognition` extra in `pyproject.toml`.

Nothing else changes: alignment, decision logic, capture and persistence sit
behind the ports, and `GET /models` reports whatever is wired in.

---

## Configuration

Every setting is an `ARGUS_`-prefixed environment variable; see
[`.env.example`](.env.example) for the annotated list and
[`docs/database_setup.md`](../docs/database_setup.md) for what each store needs.
Values that require calibration (thresholds, image quality gates) default to
`None` and the code reports them as uncalibrated rather than guessing.
