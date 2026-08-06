# ARGUS Backend

FastAPI service for the Project ARGUS attendance system: classrooms, roster,
lecture sessions, interval attendance capture, absence derivation, and the
recognition endpoints backed by the InsightFace `buffalo_l` ONNX pack.

- Schema contract: [`docs/db.md`](../docs/db.md) - mapped 1:1, no extra tables
- **How it all fits together: [`docs/architecture.md`](../docs/architecture.md)**
- Setup and schema decisions: [`docs/database_setup.md`](../docs/database_setup.md)
- HTTP contract: [`docs/api_integration.md`](../docs/api_integration.md)
- Measured behaviour at 20 000 students: [`docs/benchmarks.md`](../docs/benchmarks.md)

---

## Quick start

Requires **Python 3.11+** (the code uses `enum.StrEnum`, added in 3.11 -
`ruff.toml` targets `py311`). If your machine's default `python`/`python3`
resolves to something older, point the venv at 3.11 explicitly
(`python3.11 -m venv .venv`) or you'll hit
`ImportError: cannot import name 'StrEnum' from 'enum'` on the first import.

```bash
cd backend
python3.11 -m venv .venv && .venv/Scripts/activate  # source .venv/bin/activate on Unix
pip install -r requirements-dev.txt                # requirements.txt for runtime only
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
  pass, so cost tracks roster size, not detection count.
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
│   ├── domain.py               status vocabularies, Observation
│   ├── api/
│   │   ├── deps.py             typed dependency aliases
│   │   ├── router.py           mounts every route under ARGUS_API_PREFIX
│   │   └── routes/             system, classrooms, students, sessions, recognition
│   ├── core/                   settings, logging, errors, ZIP safety, helpers
│   ├── db/                     engine/session, models (docs/db.md), integrity mapping
│   ├── recognition/
│   │   ├── ports.py            detector / embedder / mask synth / index protocols
│   │   ├── decision.py         MATCH | HUMAN_REVIEW | UNKNOWN policy (pure)
│   │   ├── alignment.py        ArcFace 5-point alignment
│   │   ├── stack.py            which adapter is wired in
│   │   └── adapters/           scrfd, arcface, masks, chroma
│   ├── repositories/           SQL: set-based upserts, keyset paging
│   ├── schemas/                request/response models
│   ├── services/               use cases, one transaction per operation
│   └── storage/                Cloudflare R2 upload for the roster import
├── alembic/                    0001_initial_schema = docs/db.md
├── benchmarks/                 db_scale.py, vector_search.py
└── tests/
```

Layering is one-directional: `api -> services -> repositories -> db`, with
`recognition` reached only through the port protocols.

---

## Recognition stack

Runs on `onnxruntime` against the InsightFace `buffalo_l` ONNX pack - no torch
and no `insightface` package at serving time.

| Component | Adapter | Model |
|---|---|---|
| Detection + 5-point landmarks | `adapters/scrfd.py` | `det_10g.onnx` |
| Embedding (512-d, L2-normalised) | `adapters/arcface.py` | `w600k_r50.onnx` |
| Mask variants | `adapters/masks.py` | none - geometric, in the aligned frame |
| Template index | `adapters/chroma.py` | ChromaDB, cosine |

```bash
export ARGUS_MODEL_ROOT=../models/buffalo_l
export ARGUS_CHROMA_MODE=persistent ARGUS_CHROMA_PATH=./.chroma
```

The weights are **not in the repository** - the pack is ~197 MB and
`w600k_r50.onnx` alone exceeds GitHub's 100 MB per-file limit, so `models/` is
git-ignored. Download the InsightFace `buffalo_l` pack and unpack it so the
repository root looks like this:

```text
models/buffalo_l/
├── det_10g.onnx        detection + 5 landmarks   (used)
├── w600k_r50.onnx      512-d embedding           (used)
├── 2d106det.onnx       dense landmarks           (not used)
└── genderage.onnx      age/gender                (not used)
```

`2d106det.onnx` is unused because the mask synthesiser works in the aligned
canonical frame, where the geometry is already known; `genderage.onnx` is not an
attendance concern.

Models load lazily and are warmed at startup, so `GET /models` reports the truth
before the first request. A component with no model file configured stays unset
and its endpoints answer `503` naming the missing setting - nothing is guessed.

Thresholds have been **calibrated** against LFW (400 identities) + MFR2 (53
identities) under the 1:N identification protocol this system actually runs, and
`backend/.env` sets them:

| Setting | Value | Basis |
|---|---|---|
| `ARGUS_MATCH_THRESHOLD` | `0.35` | 0/2400 false accepts against a 10 000-template gallery |
| `ARGUS_REVIEW_THRESHOLD` | `0.25` | ~5% of impostors reach it, so it is flagged, never auto-marked |
| `ARGUS_MINIMUM_MARGIN` | `0.06` | 5th percentile of the top1/top2 margin on correct matches |

`.env.example` still ships them empty, and that state is meaningful: until all
three are set, `decide()` cannot return `MATCH`, so nothing is auto-marked and the
API returns `HUMAN_REVIEW` with that reason rather than inventing a threshold.
See `docs/benchmarks.md` section 4 for the derivation - and re-calibrate on real
masked photos of the actual cohort before production.

Detection is the remaining weak point, not recognition:
`ARGUS_DETECTION_SCORE_THRESHOLD` is lowered to `0.20` because SCRFD scores
masked faces far lower than bare ones (the 0.50 default detected only 13.9% of
masked faces at classroom scale, versus 69.4% at 0.20). A face that is never
detected produces no observation and silently becomes `Absent`. Lowering the gate
cannot create false attendance - detections still have to clear the match
threshold, and 0 wrong matches were measured at 0.20 - but 69.4% is a mitigation,
not a fix. See `docs/architecture.md` section 5.3.

To replace an adapter, satisfy the protocol in `app/recognition/ports.py` and
register it in `build_recognition_stack()` in `app/recognition/stack.py`.
Alignment, decision logic, capture and persistence sit behind the ports.

---

## Configuration

Every setting is an `ARGUS_`-prefixed environment variable; see
[`.env.example`](.env.example) for the annotated list and
[`docs/database_setup.md`](../docs/database_setup.md) for what each store needs.
Values that require calibration (thresholds, image quality gates) default to
`None` and are reported as uncalibrated rather than guessed.
