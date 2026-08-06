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
pip install -r requirements.txt
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

The DDL is a literal materialisation of `docs/db.md`: the four tables, their
columns and types, the primary keys, `UNIQUE(roll_no)`, `UNIQUE(session_id,
student_id)` and the four foreign keys. **Nothing else is created** - no extra
index, no CHECK constraint, no `ON DELETE` rule. `alembic upgrade head --sql`
prints exactly the schema the document describes and nothing more.

### 4.1 What the schema therefore does *not* do for you

Two guarantees that a constraint would normally provide are upheld by the
service layer instead. If you write to these tables from anything other than
this API, they are yours to maintain.

| Guarantee | Where it lives now |
|---|---|
| At most one `ACTIVE` session per classroom | `SessionService.create` takes a transaction-scoped advisory lock keyed on `class_id` (`pg_advisory_xact_lock`), re-checks for an ACTIVE session and inserts inside the same transaction. `docs/db.md` requires recognition to "Fetch Active Class Session", which only has one answer if this holds. A direct `INSERT` bypasses it. |
| Deleting a student removes their attendance | The foreign keys have no `ON DELETE`, i.e. `NO ACTION`, so PostgreSQL refuses to delete a student who has ever been marked present. `StudentService.delete` deletes the attendance rows first, in the same transaction (acceptance test AT-11). |

Two further consequences to be aware of:

* **Deleting a classroom fails** while any student or session still references it.
  Reassign or remove them first. There is no classroom-delete endpoint.
* **Value ranges are validated at the API boundary, not in the database.**
  Pydantic rejects `semester < 1`, `strength < 0`, `end_time <= start_time` and a
  confidence outside `[-1, 1]` before any statement runs, but a direct `INSERT`
  can still write nonsense.

### 4.2 Performance without the indexes

Only the indexes PostgreSQL creates for the documented primary keys and unique
constraints exist. For a 20 000 student roster that is enough, because the two
hot paths are already covered or are cheap sequential work:

| Query | Plan |
|---|---|
| Attendance register for a session | Uses the `UNIQUE(session_id, student_id)` index; `session_id` is its leading column. |
| Interval flush (`upsert_present`) | Same index arbitrates the `ON CONFLICT`. |
| Absence pass at session close | Sequential scan of `students` filtered by `class_id`, anti-joined against the session's attendance rows. One pass over 20 000 narrow rows. |
| Roster listing, keyset paged by `roll_no` | Uses the `UNIQUE(roll_no)` index for ordering; the `class_id` filter is applied as a predicate. |
| Per-student attendance history | Sequential scan of `attendance` filtered by `student_id`. This is the one path that would benefit from an index if history grows large. |

If a deployment outgrows this, add indexes as a separate migration - they are
pure performance and change no behaviour. See `docs/benchmarks.md` for measured
numbers.

### 4.3 Interpretations you need to know

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
`GET /classrooms/{class_id}` returns both `strength` and `roster_count`, so a
mismatch is visible.

**`students.roll_no` stays `INTEGER` and globally unique**, exactly as
documented. It is also the pagination cursor for roster and register listings.

**All timestamps are naive UTC.** The columns are `TIMESTAMP` (no time zone), so
the backend writes UTC and never local time. Clients should render in local time.

### 4.4 Gaps to be aware of (nothing was added for them)

| Gap | Effect today | Options if you want it |
|---|---|---|
| No table for per-detection events | Only the aggregated attendance row survives; individual interval sightings are coalesced in memory and not persisted. `GET /events` and `GET /audit/status` from `docs/design.md` have no backing store. | Needs a new table - not created, since the schema is fixed. |
| No table for template metadata | `docs/design.md` says PostgreSQL stores "template information"; `docs/db.md` has no such table. Template metadata therefore lives **only** in Chroma (`student_id`, `mask_type`, `model_version`). | Works as-is; only limits SQL-side reporting on templates. |
| No users/roles table | The API is unauthenticated. Anyone who can reach it can open a session or delete a student. | Put it behind a gateway/VPN, or add auth once a table is approved. |
| No `closed_at` on sessions | The close instant is recoverable from the `Absent` rows' timestamp, not from the session row. | Acceptable; noted so nobody looks for the column. |
| No import-job table | `POST /students/import` reports its per-row outcome in the HTTP response only. If the caller loses the response, the outcome is not recoverable from the database, and the trail for orphaned R2 objects is the application log. | Needs a new table - not created. |

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
   mid-lecture returns who has been seen so far; `roster_count - present` in the
   summary is how many roster members have no row yet.
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

| Variable | Values | Notes |
|---|---|---|
| `ARGUS_OBJECT_STORAGE_MODE` | `disabled` \| `r2` | `disabled` makes any import that carries images answer 503 rather than invent a URL. |
| `ARGUS_R2_ENDPOINT_URL` | `https://<account>.r2.cloudflarestorage.com` | Required for `r2`. |
| `ARGUS_R2_BUCKET` | bucket name | Required for `r2`. |
| `ARGUS_R2_ACCESS_KEY_ID` / `ARGUS_R2_SECRET_ACCESS_KEY` | credentials | Required for `r2`. |
| `ARGUS_R2_PUBLIC_BASE_URL` | `https://images.example.edu` | Required for `r2`; the prefix written into `students.image_url`. |
| `ARGUS_R2_KEY_PREFIX` | `enrollment` | Object key prefix. |

There are two ways an enrollment image gets a URL. `POST /students` takes an
`image_url` your client has already uploaded, and the backend only validates and
stores it. `POST /students/import` accepts a ZIP of photographs and uploads each
one itself before writing the row, because `students.image_url` is `NOT NULL`.
See `docs/registration_import.md`.

Objects are never deleted by the backend. If an import's insert fails after its
images were uploaded, the orphaned keys are logged at `ERROR` for reconciliation.

---

## 8. Verifying a deployment

```bash
curl http://localhost:8000/api/v1/health    # 200 = every dependency reachable
curl http://localhost:8000/api/v1/models    # which components are wired, thresholds
```

`/health` returns `503` with a per-dependency reason while anything is missing;
that is the expected state before PostgreSQL and Chroma are wired up.

Integration tests against a real database:

```bash
export ARGUS_TEST_DATABASE_URL=postgresql+asyncpg://argus:argus@localhost:5432/argus_test
pytest            # without the variable, the database tests skip
```
