# Database Setup & Integration Guide

How to bring up the data stores the ARGUS backend talks to, how the code maps
onto the schema in [`docs/db.md`](db.md), and every decision that was made while
mapping it. Read this before writing code that touches the database.

Related documents:

- [`docs/db.md`](db.md) - the authoritative schema.
- [`docs/api_integration.md`](api_integration.md) - the HTTP contract for the frontend.
- [`docs/benchmarks.md`](benchmarks.md) - measured behaviour at 20 000 students.
- [`backend/README.md`](../backend/README.md) - running the service.

---

## 1. What the backend stores where

| Store | Holds | Required for |
|---|---|---|
| **PostgreSQL 13+** | classrooms, students, class_sessions, attendance | every attendance endpoint |
| **ChromaDB** | 512-D face templates + `{student_id, mask_type, model_version}` metadata | enrollment, recognition |
| **Cloudflare R2** | enrollment images (originals + synthetic masked) | image hosting only |

The backend never stores an embedding in PostgreSQL and never uploads to R2 -
it persists the `students.image_url` your client provides.

PostgreSQL 13 or newer is required because the primary keys default to
`gen_random_uuid()`, which is built in from 13 onwards. On PostgreSQL 12 or
older, run `CREATE EXTENSION IF NOT EXISTS pgcrypto;` first.

---

## 2. Connection string

One variable drives the application, the migrations and the tests:

```bash
ARGUS_DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<database>
```

The `+asyncpg` driver suffix is mandatory - the backend is fully async and a
`psycopg2` URL will fail at startup. URL-encode any special characters in the
password (`@` becomes `%40`).

| Variable | Default | Meaning |
|---|---|---|
| `ARGUS_DATABASE_URL` | *(unset)* | Connection string. When unset every attendance endpoint answers `503 dependency_not_configured` instead of failing obscurely. |
| `ARGUS_DB_POOL_SIZE` | `10` | Persistent pooled connections per worker process. |
| `ARGUS_DB_MAX_OVERFLOW` | `20` | Extra connections allowed during bursts. |
| `ARGUS_DB_POOL_RECYCLE_SECONDS` | `1800` | Recycle age; keep below your proxy/idle timeout. |
| `ARGUS_DB_STATEMENT_TIMEOUT_MS` | `15000` | Server-side `statement_timeout`; a runaway query is killed by PostgreSQL, not left hanging. |
| `ARGUS_DB_ECHO` | `false` | Log every SQL statement (development only). |

Total connections to size the server for: `(pool_size + max_overflow) x number of
API worker processes`.

### Local instance

```bash
docker run -d --name argus-pg \
  -e POSTGRES_USER=argus -e POSTGRES_PASSWORD=argus -e POSTGRES_DB=argus \
  -p 5432:5432 postgres:16-alpine
```

```bash
ARGUS_DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus
```

### Managed instance (Supabase / Neon / RDS)

Use the connection-pooler host if one is offered, keep `ARGUS_DB_POOL_SIZE`
small (the pooler already multiplexes), and append `?ssl=require` when the
provider mandates TLS.

---

## 3. Creating the schema

```bash
cd backend
pip install -e .
alembic upgrade head
```

Revision `0001_initial_schema` creates exactly the four tables from `docs/db.md`.
A test (`tests/test_migration_matches_models.py`) applies the migration to a
scratch database and asserts Alembic finds **no** difference against the ORM
models, so the migration and the code can never drift apart.

To inspect the SQL without executing it:

```bash
alembic upgrade head --sql
```

---

## 4. Schema mapping decisions

The four tables, their columns, types and constraints are taken from
`docs/db.md` unchanged. **No table and no column was added.** Everything below is
either a decision about how to *use* the documented schema, or an addition that
introduces no new data - indexes, CHECK constraints over already-documented
value sets, and foreign-key delete rules.

### 4.1 Additions (no new data, no new columns)

| Object | Type | Why it exists |
|---|---|---|
| `ix_students_class_id_roll_no` | index | Roster scan and keyset pagination for a classroom. Without it every roster read at 20 000 students is a sequential scan. |
| `ix_class_sessions_class_id_date` | index | Timetable listings filtered by classroom and date. |
| `uq_class_sessions_active_per_class` | **partial unique index** on `class_id WHERE status = 'ACTIVE'` | `docs/db.md` says recognition must "Fetch Active Class Session". That has one answer only if one session per classroom can be ACTIVE. Enforced in the database so two concurrent writers cannot both succeed. |
| `ix_attendance_student_id` | index | Per-student attendance history. (Session-scoped reads already use the documented `UNIQUE(session_id, student_id)` index.) |
| `ck_class_sessions_status_domain` | CHECK | `status IN ('ACTIVE','CLOSED')` - the vocabulary already documented for the column. |
| `ck_attendance_status_domain` | CHECK | `status IN ('Present','Absent')` - same. |
| `ck_attendance_confidence_range` | CHECK | `-1.0 <= confidence <= 1.0`, the cosine-similarity domain used in `docs/design.md`. |
| `ck_class_sessions_time_range` | CHECK | `end_time > start_time`. |
| `ck_classrooms_semester_positive`, `ck_classrooms_strength_non_negative` | CHECK | Reject nonsense values on input. |

Foreign-key delete rules (`docs/db.md` does not specify them):

| Foreign key | Rule | Reason |
|---|---|---|
| `attendance.session_id -> class_sessions` | `CASCADE` | A deleted session has no attendance. |
| `attendance.student_id -> students` | `CASCADE` | Acceptance test AT-11: deleting an identity removes its records. |
| `students.class_id -> classrooms` | `SET NULL` | A student outlives a classroom reorganisation; `class_id` is nullable in `docs/db.md`. |
| `class_sessions.class_id -> classrooms` | `RESTRICT` | Deleting a classroom that has taught sessions would orphan the attendance history. |

### 4.2 Interpretations you need to know

**`attendance.timestamp` = first sighting.** A student is typically recognised
in many capture intervals. The single row keeps the **earliest** detection - the
moment the student was marked present, which is the useful value for
late-arrival analysis.

**`attendance.confidence` = best evidence.** The same row keeps the **highest**
similarity seen across the whole session. Both rules are applied by the same
`GREATEST`/`LEAST` clause in SQL, so the result is identical no matter how the
detections were spread over intervals or across backend workers.

**`attendance.confidence = 0.0` marks an absence.** The column is
`FLOAT NOT NULL`, but rows created by the session-close absence pass involve no
recognition at all. `0.0` is the sentinel; the meaning comes from
`status = 'Absent'`, never from the confidence value. If you need to distinguish
"absent" from "recognised with 0.0 confidence", filter on `status`.

**`classrooms.strength` is the declared strength, not a live count.** It is the
number an administrator enters. Attendance maths uses `COUNT(students)` for the
classroom instead, so a stale `strength` can never cause a wrong absence list.
The API returns both (`declared_strength` and `roster_count`) so a mismatch is
visible.

**`students.roll_no` stays `INTEGER` and globally unique**, exactly as
documented. It is also the pagination cursor for roster and register listings.

**All timestamps are naive UTC.** The columns are `TIMESTAMP` (no time zone), so
the backend writes UTC and never local time. Clients should render in local time.

### 4.3 Gaps to be aware of (nothing was added for them)

| Gap | Effect today | Options if you want it |
|---|---|---|
| No table for per-detection events | Only the aggregated attendance row survives; individual interval sightings are coalesced in memory and not persisted. `GET /events` and `GET /audit/status` from `docs/design.md` have no backing store. | Needs a new table - not created, since the schema is fixed. |
| No table for template metadata | `docs/design.md` says PostgreSQL stores "template information"; `docs/db.md` has no such table. Template metadata therefore lives **only** in Chroma (`student_id`, `mask_type`, `model_version`). | Works as-is; only limits SQL-side reporting on templates. |
| No users/roles table | The API is unauthenticated. Anyone who can reach it can open a session or delete a student. | Put it behind a gateway/VPN, or add auth once a table is approved. |
| No `closed_at` on sessions | The close instant is recoverable from the `Absent` rows' timestamp, not from the session row. | Acceptable; noted so nobody looks for the column. |
| No bulk student import endpoint | A 20 000 row roster has to be POSTed one student at a time over HTTP. The repository already has `bulk_insert` (used by the benchmarks); only the endpoint is missing. | One route away if you want it. |

---

## 5. How attendance is written

```text
session ACTIVE
   |
   |-- recognition MATCH ---> capture buffer (in memory, per worker)
   |                              | every ARGUS_CAPTURE_INTERVAL_SECONDS
   |                              v
   |                        INSERT ... ON CONFLICT DO UPDATE   <- one statement
   |                        (Present rows appear during the lecture)
   v
POST /sessions/{id}/close
   |-- flush whatever is still buffered
   |-- INSERT ... SELECT ... WHERE NOT EXISTS  -> Absent for the rest
   |-- status = CLOSED
   (one transaction, session row locked with SELECT ... FOR UPDATE)
```

Two properties matter for integration:

1. **Attendance is written continuously, not at the end.** Reading the register
   mid-lecture returns who has been seen so far. `unrecorded` in the summary is
   how many roster members have no row yet.
2. **Absence is derived exactly once, at close.** Nothing writes `Absent` while
   the session is running, so a student who arrives late is never wrongly marked.

The interval upsert statement joins `class_sessions` and `students`, which means
PostgreSQL itself rejects an observation when the session is not ACTIVE or the
recognised student is not on that classroom's roster. Running several backend
workers is safe: the merge rule is commutative, so the row converges to the same
values regardless of which worker wrote first.

Tuning: `ARGUS_CAPTURE_INTERVAL_SECONDS` (default 15) trades register freshness
against write frequency. One statement is issued per interval per active session
regardless of how many students were recognised.

---

## 6. ChromaDB

| Variable | Values | Notes |
|---|---|---|
| `ARGUS_CHROMA_MODE` | `disabled` \| `persistent` \| `http` | `disabled` makes recognition endpoints answer 503. |
| `ARGUS_CHROMA_PATH` | path | Required for `persistent`. |
| `ARGUS_CHROMA_HOST` / `ARGUS_CHROMA_PORT` | host / port | Required for `http`. |
| `ARGUS_CHROMA_COLLECTION` | `argus_templates` | Created on first use with `hnsw:space = cosine`. |
| `ARGUS_CHROMA_SEARCH_K` | `10` | Neighbours fetched per probe before grouping by identity. |

```bash
docker run -d --name argus-chroma -p 8000:8000 -v argus-chroma:/data chromadb/chroma
```

Stored metadata per template: `student_id`, `mask_type` (`UNMASKED` or a variant
from `ARGUS_MASK_VARIANTS`), `model_version`. Similarity is `1 - cosine_distance`.
Deleting a student removes their vectors **before** the SQL row, so a failure can
never leave searchable vectors pointing at a deleted identity.

---

## 7. Cloudflare R2

The backend does not upload. Your enrollment client puts the image in R2 and
sends the resulting URL as `students.image_url`, which is validated as an
absolute HTTP(S) URL. `ARGUS_OBJECT_STORAGE_MODE` / `ARGUS_R2_PUBLIC_BASE_URL`
are placeholders reserved for the day the backend does the upload itself.

---

## 8. Verifying a deployment

```bash
curl http://localhost:8000/api/v1/health    # 200 = every dependency reachable
curl http://localhost:8000/api/v1/runtime   # capture interval, buffered work
curl http://localhost:8000/api/v1/models    # which adapters are real, thresholds
```

`/health` returns `503` with a per-dependency reason while anything is missing;
that is the expected state before PostgreSQL and Chroma are wired up.

Integration tests against a real database:

```bash
export ARGUS_TEST_DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus_test
pytest            # without the variable, the database tests skip
```
