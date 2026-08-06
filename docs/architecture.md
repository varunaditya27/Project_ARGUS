# ARGUS — Architecture

How the codebase is actually put together: which process owns what, how a frame
becomes an attendance row, and why each boundary is where it is.

This document describes **what is in the repository today**. Where something is
measured, the number is quoted with its source; where something is not built yet,
it says so.

- Schema contract → [`db.md`](db.md)
- Setup and connection strings → [`database_setup.md`](database_setup.md)
- HTTP/WebSocket contract → [`api_integration.md`](api_integration.md)
- Design rationale and decision policy → [`design.md`](design.md)
- Measured performance → [`benchmarks.md`](benchmarks.md)

---

## 1. The one-paragraph version

ARGUS recognises **masked** faces against a gallery enrolled from **unmasked**
photographs, and turns those recognitions into classroom attendance. A Next.js
console posts frames to a FastAPI service. The service detects faces (SCRFD),
aligns and embeds them (ArcFace, 512-d), searches a ChromaDB template index, and
applies a threshold policy that returns `MATCH`, `HUMAN_REVIEW` or `UNKNOWN`.
Only a `MATCH` becomes attendance evidence. Evidence is coalesced in memory and
flushed to PostgreSQL once per capture interval while the lecture runs; absence
is derived exactly once, in a single statement, when the session is closed.

---

## 2. Two halves of one repository

The tree splits cleanly into a **research pipeline** and a **serving system**.
They share the model weights and the ChromaDB collection schema, and nothing
else — the research scripts never import backend code, and the backend never
imports the research scripts.

```text
Project_ARGUS/
├── datasets/        research   dataset acquisition + synthetic masking (vendored tools)
├── embeddings/      research   batch embedding extraction -> .npz
├── evaluation/      research   rank-1 / ROC / TAR@FAR, threshold calibration
├── enrollment/      research   seeds the 5,802-identity demo gallery into ChromaDB
├── tests/           research   51 tests over the pipeline scripts
│
├── backend/         serving    FastAPI service (see §4)
├── frontend/        serving    Next.js 16 operator console (see §7)
├── models/          shared     InsightFace buffalo_l ONNX pack (git-ignored, ~197 MB)
├── samples/                    example roster CSV + photo ZIP for bulk import
└── docs/                       this directory
```

**Why the split matters.** The research half answers "does this approach work,
and how well" and is allowed to be a collection of scripts driven from the
command line. The serving half answers "is this student present" and is held to
a stricter standard: no fabricated results, one-directional layering, every
dependency either configured or explicitly refused. Read a number from
`evaluation/`; read behaviour from `backend/`.

---

## 3. Runtime topology

```mermaid
flowchart TB
    subgraph client["Browser"]
        UI["Next.js 16 console<br/>localhost:3001"]
        CAM["getUserMedia webcam"]
    end

    subgraph service["FastAPI process — localhost:8000"]
        API["Routers<br/>/api/v1"]
        SVC["Services"]
        BUF["ObservationBuffer<br/>(in-process, per session)"]
        FLUSH["IntervalFlusher<br/>asyncio task"]
        VIS["Recognition stack<br/>onnxruntime, worker threads"]
    end

    subgraph stores["Stores"]
        PG[("PostgreSQL<br/>4 tables")]
        CH[("ChromaDB<br/>argus_templates")]
        OBJ[("Object storage<br/>local dir or Cloudflare R2")]
    end

    CAM --> UI
    UI -->|"REST + multipart"| API
    UI -->|"WebSocket /live"| API
    API --> SVC
    SVC --> VIS
    VIS <--> CH
    SVC -->|"MATCH only"| BUF
    BUF --> FLUSH
    FLUSH -->|"1 statement / interval"| PG
    SVC --> PG
    SVC --> OBJ
    UI -->|"enrollment images"| OBJ
```

One FastAPI process holds the ONNX sessions, the capture buffer and the flusher
task. That is a deliberate constraint, and §9 covers what changes when you run
more than one.

---

## 4. Backend layering

`backend/app/` is layered one-directionally. Nothing in an inner ring imports
from an outer one.

```text
api/          routers, typed dependency aliases   — HTTP shapes only, no logic
  ↓
services/     use cases, one transaction each     — orchestration
  ↓
repositories/ SQL: set-based upserts, keyset paging
  ↓
db/           engine, session factory, ORM models, integrity mapping

recognition/  ports (Protocol) + adapters + pure decision policy
storage/      ObjectStorage port + local / R2 adapters
core/         settings, logging, error envelope, ZIP safety, helpers
```

`services/` reaches the vision stack **only** through the Protocols in
`recognition/ports.py` (`FaceDetector`, `FaceEmbedder`, `MaskSynthesizer`,
`TemplateIndex`). That is what lets the attendance tests run without
`onnxruntime` or `chromadb` installed, and what makes swapping a model a
one-file change plus one line in `build_recognition_stack()`.

### 4.1 Composition root

`app/container.py` is the only place long-lived objects are constructed: the
engine pool, the observation buffer, the flusher task, the recognition stack and
the service registry. Routers pull them from `app/api/deps.py`; nothing
constructs its own dependency.

The container is honest about partial configuration:

| Missing setting | Consequence |
|---|---|
| `ARGUS_DATABASE_URL` | `registry` is `None`; every database endpoint raises `503 dependency_not_configured` naming the variable |
| `ARGUS_MODEL_ROOT` / model paths | detector/embedder stay `None`; recognition endpoints `503` naming the setting |
| `ARGUS_CHROMA_MODE=disabled` | template index stays `None`; enroll/recognise `503` |
| `ARGUS_OBJECT_STORAGE_MODE=disabled` | image upload and bulk import `503`; everything else works |
| thresholds unset | stack is `ready: false`; `decide()` **cannot** return `MATCH` |

The service still starts in every one of those states. That is the point: it
comes up, reports precisely what is wrong via `GET /health` and `GET /models`,
and refuses only the endpoints that genuinely cannot be served.

---

## 5. The recognition path

```mermaid
sequenceDiagram
    participant C as Client
    participant R as /recognize
    participant S as RecognitionService
    participant D as SCRFD (thread)
    participant E as ArcFace (thread)
    participant X as ChromaDB
    participant P as decide()
    participant B as ObservationBuffer

    C->>R: multipart frame + session_id
    R->>S: recognize(bytes)
    S->>S: decode + size gate
    S->>D: detect(image)
    D-->>S: N faces + 5 landmarks each
    S->>S: align_face() x N  (one thread hop)
    S->>E: embed(crops)      (one batch)
    E-->>S: N x 512 L2-normalised
    S->>X: search(embeddings, k)  (one batched query)
    X-->>S: k neighbours per probe
    S->>P: decide(matches, thresholds, quality_note)
    P-->>S: MATCH | HUMAN_REVIEW | UNKNOWN
    S->>B: observations_from(...)  — MATCH only
    S-->>C: FrameResult (bbox, state, similarity, reason)
```

Three properties of this path are load-bearing:

**Every model call is batched per frame.** One detect, one embed call over all
crops, one index query for all probes. Cost scales with frames, not faces.

**Every model call is pushed to a worker thread.** `onnxruntime` inference is
CPU-bound and would otherwise stall the event loop for the whole frame, blocking
every other request. `asyncio.to_thread` keeps the loop responsive.

**Frames are never stored.** The WebSocket at `/live` is strictly
request/response — the client sends one binary frame and waits for the JSON
result before sending the next, so no backlog of stale frames accumulates and
there is no frame buffer to leak.

### 5.1 Decision policy

`recognition/decision.py` is pure — no I/O, fully unit-tested. It collapses
template hits to identities (an identity scores as its **single best** template),
then applies:

```text
candidates empty                      -> UNKNOWN
thresholds uncalibrated               -> HUMAN_REVIEW   (cannot ever be MATCH)
quality gate tripped                  -> HUMAN_REVIEW
best >= match AND margin >= min_margin -> MATCH
best >= review                        -> HUMAN_REVIEW
otherwise                             -> UNKNOWN
```

Two invariants worth naming explicitly:

1. **Nearest neighbour never implies a match.** A vector index always returns the
   closest vector, even for a total stranger. Absolute similarity must clear
   `match_threshold` on its own.
2. **The margin guard exists because the gallery is large.** With thousands of
   enrolled identities, two people scoring almost identically is the
   characteristic failure. `minimum_margin` sends that case to review rather than
   picking one. It is skipped only when there is a single competing identity, in
   which case there is no margin to measure.

### 5.2 Configured thresholds

`backend/.env` currently ships calibrated values, derived from 400 LFW identities
× 6 synthetic masks (2,400 masked probes) scored against a 10,000-template
gallery — the 1:N identification protocol the system actually runs:

| Setting | Value | Basis |
|---|---|---|
| `ARGUS_MATCH_THRESHOLD` | `0.35` | 0/2400 false accepts at 10k gallery; max impostor similarity was 0.3458 |
| `ARGUS_REVIEW_THRESHOLD` | `0.25` | ~5% of impostors reach this, so it is flagged, never auto-marked |
| `ARGUS_MINIMUM_MARGIN` | `0.06` | 5th percentile of top1/top2 margin on correct matches |
| `ARGUS_DETECTION_SCORE_THRESHOLD` | `0.20` | see below |

Per-frame miss rate at 0.35 is 25.7%. That is acceptable *because attendance
samples every interval*: a student present for 20 intervals is missed with
probability ~1.5e-12. The design converts a mediocre per-frame recogniser into a
reliable per-lecture one by sampling repeatedly, rather than by loosening the
threshold.

> **Caveat carried from `benchmarks.md` §4.** These come from a public dataset
> with synthetic masks, not from the deployment's own cohort, camera and mask
> habits. Re-calibrate on real probes before production. Note also that
> `evaluation/calibrate_thresholds.py` uses a **1:1 verification** protocol and
> reports a much lower match threshold (0.1439) that false-accepts 96% of probes
> under 1:N — protocol mismatch, not a better number.

### 5.3 The detection-recall problem

A mask occludes roughly half the face, so SCRFD scores a masked student far lower
than a bare one. Measured on 72 masked faces composited into 1280×720 frames at
classroom scale (~140 px faces):

| Detection gate | Faces detected |
|---|---|
| 0.50 (library default) | 13.9% |
| 0.30 | 47.2% |
| **0.20 (configured)** | **69.4%** |

This matters more than it looks. A face that is never *detected* produces no
observation at all, so a student who sat through the entire lecture falls through
to `Absent` at close — a silent wrong answer, not a visible failure.

Lowering the gate cannot manufacture false attendance: a detection still has to
clear `ARGUS_MATCH_THRESHOLD` against the gallery. Measured at gate 0.20 over the
same probes: **0 wrong matches**; weak detections land in `HUMAN_REVIEW` or
`UNKNOWN`, which write nothing.

**This is a known open issue, not a solved one.** 69.4% is a mitigation, not a
fix. The real fix is enrolling masked templates per student so the gallery
matches what the camera sees — data, not code.

---

## 6. The attendance path

The central design decision: **attendance accrues during the lecture; absence is
derived once, at the end.**

```text
session created ACTIVE
  │
  ├─ recognition MATCH ──> ObservationBuffer (coalesced per student)
  │                              │  every ARGUS_CAPTURE_INTERVAL_SECONDS (10s)
  │                              ▼
  │                        one INSERT ... ON CONFLICT DO UPDATE
  │                              │
  │                              ▼   Present rows appear live during the lecture
  │
  └─ POST /sessions/{id}/close   (one transaction, session row locked FOR UPDATE)
         ├─ flush whatever is still buffered
         ├─ INSERT ... SELECT ... WHERE NOT EXISTS   -> Absent for the remainder
         └─ status = CLOSED
```

### 6.1 Why coalescing

A student is recognised in many frames per interval. Merging them in memory turns
N detections into **one** row write, with the rule `max(confidence)`,
`min(timestamp)`.

That exact rule is repeated in the SQL `ON CONFLICT DO UPDATE` clause as
`GREATEST`/`LEAST`. Because the in-memory merge and the SQL merge are the same
function, the result is identical no matter whether two observations meet in
memory, in the database, or across two worker processes. The merge is idempotent,
which is also what makes requeuing a failed flush safe.

### 6.2 Why set-based writes

Both write paths are single statements whose cost tracks **roster size, not
detection count**:

- The interval upsert `unnest`s three parallel arrays and joins `class_sessions`
  and `students`. So PostgreSQL itself enforces — in the same statement — that
  the session is still `ACTIVE` and that the recognised student is on that
  classroom's roster. No pre-flight `SELECT`, no race between checking and
  writing. Rows filtered out by the join are reported back by omission.
- The absence pass is one anti-join insert over the roster.

### 6.3 Durability

Nothing captured is dropped:

- A failed flush **requeues** into the buffer rather than discarding attendance.
- A failed tick logs and continues; one bad interval does not kill the task.
- Shutdown flushes one final time.
- `close_session` drains the buffer *before* opening its transaction, and
  requeues on any non-domain failure.

The buffer is a write-coalescing cache in front of PostgreSQL, never the source
of truth. Its one bound is `ARGUS_CAPTURE_MAX_BUFFERED_SESSIONS` (256), which
returns `503 capacity_exceeded` rather than growing without limit.

### 6.4 Offline runs use the same path

`POST /recognize/video` and `POST /recognize/batch` replay recorded footage or a
ZIP of stills through the *same* capture buffer. Observations are merged in
memory first, so a 5,000-frame video hands the attendance layer one entry per
student rather than one per frame. Absence is still only decided at close — never
inferred from a batch run. With `recorded_at` supplied, each frame is timestamped
at `recorded_at + frame_index / fps`, so the register reflects the recording
rather than the upload.

---

## 7. Frontend

Next.js 16 App Router, one directory per route, TanStack Query for server state,
Zustand for the little local UI state (sidebar, theme), Tailwind v4 + Radix
primitives.

```text
src/
├── app/            one directory per screen (dashboard, enrollment,
│                   live-recognition, attendance, students, import,
│                   classrooms, sessions, reports, settings)
├── services/       one module per API area — the ONLY place fetch() is called
├── types/          mirrors backend/app/schemas, snake_case as the API sends it
├── components/     ui primitives, webcam viewport + overlay, async states
├── hooks/store/    camera driver, sidebar and theme state
├── providers/      query client, theme
└── layouts/        dashboard shell
```

`services/api.ts` is the single fetch boundary. It prefixes the base URL and
unwraps the backend's error envelope into an `ApiError` carrying `code`, `status`
and `details`; `components/common/async-state.tsx` renders the backend's own
message rather than a generic one, so an operator sees "set `ARGUS_CHROMA_MODE`"
instead of "something went wrong".

Two rules the UI holds itself to:

- **No mock data.** Nothing is displayed that the API cannot supply. The schema
  has no student email, no per-student accuracy, no camera inventory and no
  "late" state, so no screen invents them.
- **`recognition_ready` gates recognition.** It is a single boolean from
  `GET /models`, true only when every component is configured *and* the
  thresholds are calibrated. The frontend does not need a redeploy to discover
  the backend's capability.

---

## 8. Data stores

Polyglot by design — each store holds only what it is good at.

| Store | Holds | Does not hold |
|---|---|---|
| **PostgreSQL** | classrooms, students, sessions, attendance, image URLs, constraints | face embeddings |
| **ChromaDB** | one embedding per (student, mask variant), cosine index, metadata `student_id`/`mask_type`/`model_version` | any relational data |
| **Object storage** | original enrollment images (local dir in dev, Cloudflare R2 in production) | anything queried |

### 8.1 Schema fidelity

`db/models.py` maps [`db.md`](db.md) **literally**: four tables, their documented
columns, the two documented constraints, nothing else. No convenience indexes, no
extra columns, no soft deletes. Two consequences are handled in the service layer
rather than by DDL:

| Schema reality | Handled by |
|---|---|
| Foreign keys carry no `ON DELETE` rule | `StudentService` deletes Chroma templates, then attendance rows, then the student — one transaction |
| Nothing prevents a second `ACTIVE` session | `SessionService.create` serialises the check with a PostgreSQL advisory lock held until the insert commits |

`test_migration_matches_models.py` asserts the Alembic revision and the ORM never
drift apart.

### 8.2 Template identity

Chroma ids are `{student_id}:{mask_type}`, so re-enrolling a student replaces
their templates instead of accumulating duplicates. `model_version` is recorded
per template because embeddings from different weights are not comparable — that
metadata is what makes a future model swap detectable rather than silently wrong.

Enrollment stores the unmasked template plus one per configured mask variant —
**7 templates per student** at the default configuration. A 20,000-student
deployment is therefore a ~140,000-vector index, not a 20,000-vector one.

---

## 9. Scaling characteristics

Measured numbers live in [`benchmarks.md`](benchmarks.md); this is the shape of
the system.

**What already scales.** Both attendance write paths are single set-based
statements. Every listing that can grow to 20,000 rows uses **keyset**
pagination, not `OFFSET`, so page 400 costs the same as page 1. Vector search is
~2 ms per probe and barely varies with `k`, so `ARGUS_CHROMA_SEARCH_K` can be
raised for better identity grouping essentially for free. Search is not the
bottleneck; detection and embedding are.

**What is single-process today.** The observation buffer and the flusher live in
the process. Two consequences:

1. Two workers each buffer their own observations. This is *correct but
   duplicated* — both converge on the same row via the same merge rule, so the
   result is right; it costs an extra write, it does not corrupt anything.
2. A hard process kill loses at most one interval (10 s) of un-flushed
   observations for the sessions that worker held.

Moving the buffer to Redis, or pinning a session to a worker, is the change that
makes this horizontal. Neither is implemented, and the merge rule is already
written so that either would be a drop-in.

**The absence pass is a sequential scan of `students` by design** — `db.md`
declares no index on `class_id` and none was added, to keep the DDL literal. It
is one pass over narrow rows, which is why 20,000 students close in well under a
second. If a deployment outgrows that, add the index in a separate migration.

---

## 10. Error handling

One envelope for every failure, from validation to a dead dependency:

```json
{ "error": { "code": "dependency_not_configured", "message": "...", "details": {} } }
```

| Status | `code` | Cause |
|---|---|---|
| 404 | `not_found` | Unknown classroom / student / session |
| 409 | `conflict` | Duplicate roll number, second `ACTIVE` session, re-closing a session |
| 413 | `payload_too_large` | Upload above the configured limit |
| 422 | `invalid_request` | Body or query validation failed |
| 503 | `dependency_not_configured` | A store or model adapter is not wired up |
| 503 | `dependency_unavailable` | A configured dependency is unreachable |
| 503 | `capacity_exceeded` | Too many sessions buffering in one worker |

`core/errors.py` is the single mapping point, and the same envelope is sent over
the WebSocket. `error.message` always names the concrete next step, which is why
the frontend surfaces it verbatim.

`db/integrity.py` translates named database constraints into domain errors, so a
duplicate roll number surfaces as `409 conflict` with a readable message rather
than a raw `IntegrityError`. The database stays the real arbiter — batch
pre-checks are an optimisation that produce better reports, never the guarantee.

---

## 11. Testing

| Suite | Count | Needs |
|---|---|---|
| `backend/tests/` | 82 | Nothing by default; PostgreSQL only for `@pytest.mark.database` |
| `tests/` (research pipeline) | 51 | Nothing |

The backend suite runs without `onnxruntime`, `chromadb` or PostgreSQL installed,
because the vision stack sits behind Protocols and is substituted with fakes.
That is the practical payoff of the port/adapter boundary: the attendance logic —
coalescing, the merge rule, absence derivation, the decision policy — is tested
as pure logic in milliseconds.

What is covered where:

- **Pure logic**: `test_decision.py` (threshold policy incl. the uncalibrated
  case), `test_capture.py` (merge, requeue, capacity), `test_alignment.py`,
  `test_masks.py`, `test_scrfd_decode.py` (anchor decoding without ONNX).
- **Persistence**: `test_attendance_lifecycle.py` — the full ACTIVE → intervals →
  close → absence timeline against real PostgreSQL.
- **Contract**: `test_api_smoke.py` (every route answers, unconfigured
  dependencies `503` correctly), `test_migration_matches_models.py` (Alembic ==
  ORM).
- **Import rules**: `test_roster_csv.py`, `test_roster_import.py`,
  `test_roster_rules.py` — partial-success semantics and per-row rejection.

```bash
cd backend && pytest                    # 82, no external services
ARGUS_TEST_DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus_test pytest
pytest tests/                           # 51, research pipeline, from repo root
```

---

## 12. Research pipeline

Sequential, each stage consuming the previous stage's manifest. Run from the
repository root.

```mermaid
flowchart LR
    A["datasets/raw/<br/>LFW, MFR2"] --> B["masking/scripts/<br/>select + MaskTheFace + RWMFD"]
    B --> C["full_manifest.csv"]
    C --> D["embeddings/<br/>build_embeddings.py"]
    D --> E["embeddings.npz"]
    E --> F["evaluation/<br/>baseline + multi_template"]
    E --> G["enrollment/<br/>seed_chroma.py"]
    G --> H[("backend/.chroma<br/>8,700 templates")]
    F --> I["results.json<br/>accuracy_comparison.md"]
```

`full_manifest.csv` is the only file the embedding stage reads — it knows nothing
about the folder layout above it. Manifests are tracked in git even though the
images are not: they are small deterministic text files, and they are the
provenance record of exactly which images and identities produced a result.

**Scope, and why it is what it is.** LFW has 5,749 identities but only 1,680 with
≥2 images (the minimum for both rank-1 and verification). MaskTheFace ran over all
1,680; RWMFD and the final embedding runs use the first 400 alphabetically,
capped at 4 images each so no single heavily-photographed celebrity skews the
evaluation. Embedding extraction measured ~1.2 s/image CPU-only and RWMFD
re-runs detection per mask colour, so the full set would have taken most of a
day. Nothing was deleted — the wider MaskTheFace output is still on disk, just
not in the final manifest.

### 12.1 Headline results

Baseline: one unmasked embedding per identity as gallery, zero training.

| Dataset | Unmasked→unmasked | Masked→unmasked | Gap |
|---|---|---|---|
| LFW subset (400 ids, synthetic masks) | 96.58% | 96.26% | 0.32 pp |
| MFR2 (53 ids, real masks) | 100% | 98.83% | 1.17 pp |

Multi-template gallery matching (one extra template per mask type, zero
training):

| Dataset | Baseline | Multi-template | Gain |
|---|---|---|---|
| LFW subset | 96.26% | 96.61% | +0.35 pp |
| MFR2 | 98.83% | 100% | +1.17 pp |

Full-scale seeded gallery — held-out masked probes against all 5,802 demo
identities (8,700 templates) in the live ChromaDB: **2,688/2,797 = 96.1%**.

**Read this honestly.** ArcFace/buffalo_l is already strongly mask-robust out of
the box. This is *not* the ~38% TPR drop MaskTheFace's own paper reports for
FaceNet. The finding is not "we closed a large gap" — it is "the gap was already
small, multi-template matching closed most of what remained, and RWMFD's masking
is measurably harder than MaskTheFace's" (both RWMFD variants sit 3.7–4.0 pp
below every MaskTheFace variant, consistently, across a full pipeline re-run).

### 12.2 Two real bugs found and fixed

Recorded because both silently destroyed results rather than raising:

1. **Detector window mismatch.** buffalo_l's SCRFD defaults to `det_size=(640,
   640)`, which assumes scene-scale photos with margin. RWMFD output (128×128,
   tightly cropped) and MFR2 (pre-aligned 160×160) got upsampled 4–5× into that
   window and detection collapsed — RWMFD produced 10/2,308 embeddings, MFR2
   86/269. Dropping to `det_size=(160, 160)` recovered RWMFD to 2,219/2,308 (96%)
   and MFR2 to 269/269, with no regression on LFW/MaskTheFace.
2. **Mask colour bug.** MaskTheFace's `--color` flag defaults to a non-empty hex
   string and its `mask_face()` treats any non-empty value as "apply this
   colour", so every generated mask rendered the same blue regardless of
   template — `surgical`, `surgical_blue` and `surgical_green` were visually
   identical. Re-ran with `--color ""`; all numbers above are post-fix.

The same 640-vs-160 trap applies to the backend: `ARGUS_DETECTION_INPUT_SIZE`
defaults to 640, correct for webcam frames and normal enrollment photos. Feeding
tightly-cropped 128–160 px images straight to `/enroll` will hit it again.

### 12.3 Closed-set benchmark tool

`evaluation/identify_folder.py` implements a different protocol from the live
API, deliberately. Attendance is **open-set** — an unknown face must not be
marked present, so the API abstains below threshold and writes nothing. That
benchmark is **closed-set** and scored purely on correct predictions: every test
image belongs to someone in the gallery, so abstaining is a guaranteed wrong
answer. The tool therefore always emits its best guess (argmax, no threshold) and
spends its effort on making that argmax right — detector fallback ladder,
horizontal-flip TTA, synthetic-mask gallery, max-over-templates.

Do not read its accuracy as the live system's accuracy. Different protocol,
different objective.

---

## 13. Configuration

Every setting is an `ARGUS_`-prefixed environment variable parsed by
`pydantic-settings` into one cached `Settings` object shared process-wide. See
`backend/.env.example` for the annotated list.

Two conventions worth knowing:

**Half-configured dependencies are rejected at startup, not at first use.**
`ARGUS_CHROMA_MODE=persistent` without `ARGUS_CHROMA_PATH` raises immediately;
`=r2` without credentials names every missing variable at once;
`review_threshold > match_threshold` is refused as incoherent.

**Anything requiring calibration defaults to `None`, never to a guess.** The
thresholds and the image-quality gates ship unset. An unset gate is *skipped*, and
unset thresholds make `MATCH` unreachable. The system reports "uncalibrated"
rather than inventing a number, because a fabricated threshold silently trades
false accepts against false rejects on a real attendance record.

---

## 14. Known limitations

Stated plainly, because a document that hides these is worse than no document.

| Limitation | Status |
|---|---|
| **Masked-face detection recall** — SCRFD misses ~31% of masked faces at classroom scale even at gate 0.20. A never-detected student silently becomes `Absent`. | Open. Mitigated, not fixed. Real fix is enrolling masked templates per student — data, not code. |
| **No authentication** — `db.md` has no users table, so the API is unauthenticated and must sit behind a gateway or private network. | By schema. |
| **Single-process buffer** — horizontal scaling duplicates writes (correct, wasteful) and a hard kill loses ≤1 interval. | Known. Redis buffer or session pinning is the fix. |
| **Thresholds are dataset-derived** — calibrated on LFW/MFR2 with synthetic masks, not on a real cohort or camera. | Re-calibrate before production. |
| **`roll_no` is an integer and globally unique** — `CS2024001` cannot be stored; two classrooms cannot reuse a number. | By schema (`db.md`). |
| **Deleting a student destroys their attendance history** — no `ON DELETE` rule exists and the row cannot go otherwise. | By schema. UI warns. |
| **Fine-tuning** — CBAM attention + embedding-consistency loss was explored, then abandoned before producing numbers; the zero-training alternatives were already near-ceiling. | Not pursued. |

---

## 15. Where to start reading

| To understand… | Read, in this order |
|---|---|
| How a frame becomes attendance | `api/routes/recognition.py` → `services/recognition.py` → `recognition/decision.py` → `services/capture.py` → `repositories/attendance.py` |
| Why a session closes the way it does | `services/attendance.py::close_session` → the two SQL statements in `repositories/attendance.py` |
| How to swap a model | `recognition/ports.py` → `recognition/stack.py::build_recognition_stack` → any file in `recognition/adapters/` |
| What the API guarantees | [`api_integration.md`](api_integration.md) → `schemas/` |
| How accurate it is | [`../evaluation/accuracy_comparison.md`](../evaluation/accuracy_comparison.md) → [`../evaluation/README.md`](../evaluation/README.md) |
| How it was set up | [`database_setup.md`](database_setup.md) → `backend/.env.example` |
