# API Integration Guide

Everything a frontend or a recognition client needs to talk to the ARGUS
attendance backend. Setting the services up is covered in
[`docs/database_setup.md`](database_setup.md).

- Base URL: `http://<host>:8000/api/v1`
- Interactive schema: `http://<host>:8000/docs` (OpenAPI at `/openapi.json`)
- Content type: `application/json`, except the two image endpoints (multipart)
- Auth: **none** - the schema in `docs/db.md` has no users table, so the service
  must sit behind a gateway or a private network
- All timestamps are **naive UTC**; render them in local time client-side

Identifiers are UUIDs. All the example values below are placeholders
(`00000000-...`), not data from a real deployment.

---

## 1. Error format

Every failure - validation, missing row, unavailable dependency - uses one shape:

```json
{
  "error": {
    "code": "dependency_not_configured",
    "message": "PostgreSQL is not configured. Set ARGUS_DATABASE_URL (postgresql+asyncpg://user:password@host:5432/argus).",
    "details": {}
  }
}
```

| Status | `code` | When |
|---|---|---|
| 404 | `not_found` | Unknown classroom / student / session |
| 409 | `conflict` | Duplicate roll number, second ACTIVE session for a classroom, closing an already-closed session |
| 413 | `payload_too_large` | Image above the configured limit |
| 422 | `invalid_request` | Request body or query parameters failed validation |
| 503 | `dependency_not_configured` | PostgreSQL / ChromaDB / a model adapter is not wired up yet |
| 503 | `dependency_unavailable` | A configured dependency is unreachable or failing |
| 503 | `capacity_exceeded` | Too many sessions buffering attendance in one worker |

Show `error.message` to the operator: it always names the concrete next step.

---

## 2. Current capability

The attendance system - classrooms, roster, bulk import, sessions, interval
capture, absence on close, reporting - is complete and works against PostgreSQL
today.

The vision stack is implemented: SCRFD detection and ArcFace embedding run on
onnxruntime against the InsightFace buffalo_l ONNX pack, and mask variants are
synthesised geometrically. Whether they are *live* depends on deployment - the
model files must be present and `ARGUS_MODEL_ROOT` set, and Chroma must be
configured. Until then those endpoints answer `503 dependency_not_configured`.

**The one thing you must handle in the UI regardless:** attendance is only ever
written for a `MATCH`, and whether a `MATCH` is reachable at all depends on
deployment. The three decision thresholds default to `null`, and while any of
them is unset the decision layer can only return `HUMAN_REVIEW` or `UNKNOWN`, so
nothing is recorded automatically. This is deliberate - no attendance is better
than attendance based on a guessed threshold.

`backend/.env.example` ships them empty; the checked-in local `.env` sets
calibrated values (`0.35` / `0.25` / `0.06`, derived from LFW+MFR2 - see
`docs/benchmarks.md` section 4). Never assume which state you are talking to:
read `GET /models`, treat `HUMAN_REVIEW` as a first-class outcome, and show
`reason` when it happens.

Poll `GET /models` to find out what is live; it is the single source of truth
and needs no redeploy of the frontend:

```json
{
  "components": [
    {"name": "face_detector", "configured": true, "detail": "det_10g.onnx providers=['CPUExecutionProvider'] loaded=true"},
    {"name": "face_embedder", "configured": true, "detail": "w600k_r50.onnx providers=['CPUExecutionProvider'] loaded=true"},
    {"name": "mask_synthesizer", "configured": true, "detail": "variants=['surgical_blue', ...]"},
    {"name": "template_index", "configured": false, "detail": "not configured; set ARGUS_CHROMA_MODE=persistent|http"}
  ],
  "thresholds": {"match_threshold": 0.35, "review_threshold": 0.25, "minimum_margin": 0.06},
  "recognition_ready": false
}
```

`recognition_ready` is `false` in that example because `template_index` is not
configured, even though the thresholds are calibrated - it takes *both*.
`thresholds` values are `null` on a deployment that has not calibrated them.

`recognition_ready` is the single boolean to gate the UI on: it is true only when
every component is configured *and* the thresholds are calibrated.

---

## 3. Endpoints

### 3.1 System

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | `200` when PostgreSQL and Chroma are both reachable, `503` with a per-dependency reason otherwise |
| `GET` | `/models` | Component wiring and threshold calibration state |

### 3.2 Classrooms

| Method | Path | Notes |
|---|---|---|
| `POST` | `/classrooms` | `{class_name, department, semester, strength}` |
| `GET` | `/classrooms` | Filters `department`, `semester`; `limit`/`offset` |
| `GET` | `/classrooms/{class_id}` | Adds `roster_count` |

`strength` is the declared class strength typed by an admin. `roster_count` is
how many students are actually assigned. Attendance maths uses `roster_count`; if
the two differ, the roster import is incomplete - worth surfacing in the UI.

### 3.3 Students

| Method | Path | Notes |
|---|---|---|
| `POST` | `/students` | `{student_name, roll_no, class_id, image_url}` |
| `POST` | `/students/image` | multipart `image`; stores it and returns `{key, url}` to use as `image_url`. Needs no database |
| `POST` | `/students/import` | Bulk roster from a CSV plus an optional ZIP of photographs - see `docs/registration_import.md` |
| `GET` | `/students` | Filter `class_id`; keyset paging via `after` + `limit` |
| `GET` | `/students/{student_id}` | |
| `DELETE` | `/students/{student_id}` | Removes the Chroma templates, then the attendance rows and the student, in one transaction |
| `POST` | `/students/{student_id}/enroll` | multipart `image`; needs the models and Chroma |
| `GET` | `/students/{student_id}/templates` | mask_types stored in Chroma |
| `GET` | `/students/{student_id}/attendance` | History across sessions |

`roll_no` is an integer and globally unique - that is what `docs/db.md`
specifies, so alphanumeric roll numbers like `CS2024001` cannot be stored, and
two classrooms cannot reuse a number.

`image_url` must be an absolute HTTP(S) URL. Either host the photograph
yourself, or `POST /students/image` first and pass back the `url` it returns - a
file picker and a webcam capture both take that route. A bulk import needs
neither: the backend uploads every photograph in the ZIP itself.

Deleting a student is destructive of their attendance history, because the
foreign keys carry no `ON DELETE` rule and the row cannot go otherwise. Warn
before calling it.

```jsonc
// POST /students
{
  "student_name": "Placeholder Name",
  "roll_no": 1,
  "class_id": "00000000-0000-0000-0000-000000000000",
  "image_url": "https://<your-r2-bucket>/enrollment/1.jpg"
}
```

**Keyset pagination.** Listings that can grow to 20 000 rows page by cursor, not
by offset, so page 400 is as fast as page 1:

```ts
async function* allStudents(classId: string) {
  let after: number | null = null;
  while (true) {
    const query = new URLSearchParams({ class_id: classId, limit: "200" });
    if (after !== null) query.set("after", String(after));
    const page = await fetch(`${BASE}/students?${query}`).then((r) => r.json());
    yield* page.items;
    if (page.next_cursor === null) return;
    after = page.next_cursor;
  }
}
```

### 3.4 Sessions

| Method | Path | Notes |
|---|---|---|
| `POST` | `/sessions` | Opens a lecture; defaults to `status: "ACTIVE"` |
| `GET` | `/sessions` | Filters `class_id`, `status`, `date_from`, `date_to` |
| `GET` | `/sessions/{session_id}` | |
| `POST` | `/sessions/{session_id}/close` | Finalises the session and derives absence |

Only **one ACTIVE session per classroom** is allowed; a second one returns `409`.
To find the current lecture: `GET /sessions?class_id=...&status=ACTIVE`.

```jsonc
// POST /sessions
{
  "class_id": "00000000-0000-0000-0000-000000000000",
  "subject": "Computer Vision",
  "faculty": "Faculty Name",
  "date": "2026-08-06",
  "start_time": "09:00:00",
  "end_time": "10:00:00"
}
```

### 3.5 Attendance

| Method | Path | Notes |
|---|---|---|
| `GET` | `/sessions/{session_id}/attendance` | Register; filter `status`, keyset paging by `roll_no` |
| `GET` | `/sessions/{session_id}/attendance/summary` | Counters for a live dashboard |

```jsonc
// GET /sessions/{id}/attendance
{
  "items": [
    {
      "attendance_id": "00000000-0000-0000-0000-000000000000",
      "student_id": "00000000-0000-0000-0000-000000000000",
      "student_name": "Placeholder Name",
      "roll_no": 1,
      "timestamp": "2026-08-06T09:04:11.482000",  // first sighting, UTC
      "confidence": 0.81,                          // best confidence in the session
      "status": "Present"
    }
  ],
  "next_cursor": 1
}
```

```jsonc
// GET /sessions/{id}/attendance/summary
{
  "session_id": "00000000-0000-0000-0000-000000000000",
  "session_status": "ACTIVE",
  "roster_count": 20000,        // students actually assigned to the classroom
  "present": 7930,
  "absent": 0                   // stays 0 until the session is closed
}
```

Field semantics worth wiring into the UI correctly:

- `timestamp` is the **first** time the student was recognised in the session -
  use it for late arrivals, not as "last seen".
- `confidence` is the **highest** similarity observed during the session.
- `absent: 0` while `session_status` is `ACTIVE` is correct, not a bug: absence
  is derived at close. Show `roster_count - present` as "not seen yet", never as
  "absent".

### 3.6 Closing a session

```jsonc
// POST /sessions/{id}/close
{
  "session_id": "00000000-0000-0000-0000-000000000000",
  "closed_at": "2026-08-06T10:00:03.117000",
  "present": 7930,
  "absent_marked": 12070,      // Absent rows created by this close
  "roster_count": 20000
}
```

One transaction: flush what is buffered, write `Absent` for every roster member
with no row, flip the status. Closing twice returns `409` - the report is not
regenerated, so keep the first response if you need to display it.

### 3.7 Recognition

**`POST /recognize`** - multipart: `frame` (file), optional `session_id`, optional
`frame_id`. When `session_id` is supplied and the decision is `MATCH`, the
recognition is recorded as an attendance observation for that ACTIVE session.

**`WS /live`** - `ws://<host>:8000/api/v1/live?session_id=<uuid>`. Send one binary
frame, wait for the JSON result, then send the next. That back-pressure is the
protocol (`docs/design.md`): it stops a queue of stale frames building up. Frames
are never stored. Target 5-8 processed frames per second.

```ts
const socket = new WebSocket(`${WS_BASE}/live?session_id=${sessionId}`);
socket.binaryType = "arraybuffer";
socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.error) return showError(message.error);   // dependency failure
  render(message.faces);
  sendNextFrame();                                       // only now
};
```

Both return the same per-face payload:

```jsonc
{
  "frame_id": "frame-000042",
  "session_id": "00000000-0000-0000-0000-000000000000",
  "faces": [
    {
      "bbox": [104, 53, 221, 194],
      "detection_score": 0.97,
      "state": "MATCH",                 // MATCH | HUMAN_REVIEW | UNKNOWN
      "student_id": "00000000-0000-0000-0000-000000000000",
      "similarity": 0.71,
      "reason": "Similarity and identity margin passed the calibrated thresholds.",
      "attendance_recorded": true
    }
  ]
}
```

`state` drives the UI:

| State | Meaning | Suggested treatment |
|---|---|---|
| `MATCH` | Similarity and margin cleared the calibrated thresholds | Green box; `attendance_recorded` tells you whether it reached the register |
| `HUMAN_REVIEW` | Plausible but not reliable - low quality face, close runner-up, or uncalibrated thresholds | Amber box; show `reason` and offer manual confirmation |
| `UNKNOWN` | Nobody reached the review threshold, or no usable face | Grey box; never label it with the nearest name |

`student_id` may be populated for `UNKNOWN`/`HUMAN_REVIEW` - it is the best
*candidate*, not an identification. Only treat `state === "MATCH"` as identified.

### 3.8 Offline recognition runs

Two routes take a recording instead of a live camera. Both replay their results
through the same capture buffer as the live stream, so absence is still derived
only when the session is closed - a batch run never marks anybody absent.

| Method | Path | Body |
|---|---|---|
| `POST` | `/recognize/video` | multipart: `video` (file), optional `session_id`, optional `recorded_at` |
| `POST` | `/recognize/batch` | multipart: `archive` (ZIP of stills), optional `session_id`, optional `recorded_at` |

`recorded_at` matters for the register. Supply it and each sampled video frame is
timestamped at `recorded_at + frame_index / fps`, so `attendance.timestamp`
reflects when the student actually appeared in the recording rather than when the
file was uploaded. Omit it and the upload instant is used for everything.

Video is sampled every Nth frame (`ARGUS_VIDEO_FRAME_STRIDE`, default 5) rather
than exhaustively; which containers decode depends on the OpenCV build on the
server. Both routes return the same shape:

```jsonc
{
  "session_id": "00000000-0000-0000-0000-000000000000",
  "processed": 240,              // frames sampled, or images read from the archive
  "skipped": 3,                  // undecodable entries
  "faces_detected": 812,
  "matched": 0,                  // 0 if the thresholds are uncalibrated
  "human_review": 812,
  "unknown": 0,
  "attendance_observations": 0   // distinct students handed to the capture buffer
}
```

Size limits are `ARGUS_VIDEO_MAX_BYTES`, `ARGUS_BATCH_MAX_ARCHIVE_BYTES` and
`ARGUS_BATCH_MAX_FILES`; exceeding them gives `413 payload_too_large`. Archives
are validated before anything is decompressed, so a malformed or hostile ZIP
fails with `422` rather than being partially processed.

---

## 4. Suggested frontend flows

**Attendance dashboard.** Resolve the ACTIVE session
(`GET /sessions?class_id=...&status=ACTIVE`), poll
`GET /sessions/{id}/attendance/summary` every few seconds - roughly the
deployment's `ARGUS_CAPTURE_INTERVAL_SECONDS` - and load the register with keyset
paging. Present rows appear progressively while the lecture runs.

**Closing.** Call `POST /sessions/{id}/close` once, display the report, then
refresh the register: `present + absent` now equals `roster_count`.

**Enrollment, one student.** `POST /students/image` with the file or the webcam
capture, `POST /students` with the URL it returns, then
`POST /students/{id}/enroll` with the same bytes. Handle `503` from the enroll
step when the models or Chroma are not configured - the student row is still
created and usable. This is what `frontend/src/app/enrollment/page.tsx` does.

**Enrollment, a whole roster.** `POST /students/import` with the CSV and a ZIP of
photographs; the backend uploads the images and writes the rows. It reports per
row, so render `errors` as a table rather than a single failure message, and
offer `dry_run=true` first so an admin can see what would happen. Full contract
in `docs/registration_import.md`.

**Degraded mode.** Call `GET /health` and `GET /models` at startup. If
`recognition_ready` is false, hide the live-recognition surface and label the
attendance views as manual/partial rather than letting operators believe
recognition is running.

The reference implementation of all of the above is the Next.js console in
`frontend/`; its README maps each screen to the endpoints it calls.
