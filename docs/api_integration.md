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

The attendance system - classrooms, roster, sessions, interval capture, absence
on close, reporting - is complete and works against PostgreSQL today.

The vision components (SCRFD detection, ArcFace embedding, MaskTheFace variants)
are **placeholders**, and the decision thresholds in `docs/design.md` are still
`null`. Consequences you must handle in the UI:

- `POST /students/{id}/enroll`, `POST /recognize`, `WS /live` and
  `GET /students/{id}/templates` return `503 dependency_not_configured`.
- Even once the models land, attendance is only written for a `MATCH`, and a
  `MATCH` is impossible while the thresholds are uncalibrated - the API returns
  `HUMAN_REVIEW` instead. This is deliberate: no attendance is better than
  attendance based on a guessed threshold.

Poll `GET /models` to find out what is live; it is the single source of truth
and needs no redeploy of the frontend:

```json
{
  "components": [
    {"name": "face_detector", "configured": false, "adapter": "placeholder", "detail": "not implemented; requires SCRFD adapter + ARGUS_DETECTOR_MODEL_PATH"}
  ],
  "thresholds": {"match_threshold": null, "review_threshold": null, "minimum_margin": null, "calibrated": false},
  "embedding_dim": 512,
  "mask_variants": ["surgical_blue", "surgical_white", "cloth_black", "cloth_colored", "n95", "improper_low"],
  "recognition_ready": false
}
```

---

## 3. Endpoints

### 3.1 System

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | `200` when PostgreSQL and Chroma are both reachable, `503` with a per-dependency reason otherwise |
| `GET` | `/runtime` | Uptime, capture interval, how much attendance is buffered but not yet written |
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
| `GET` | `/students` | Filter `class_id`; keyset paging via `after` + `limit` |
| `GET` | `/students/{student_id}` | |
| `DELETE` | `/students/{student_id}` | Removes the Chroma templates first, then the row |
| `POST` | `/students/{student_id}/enroll` | multipart `image`; **503 today** |
| `GET` | `/students/{student_id}/templates` | mask_types stored in Chroma; **503 today** |
| `GET` | `/students/{student_id}/attendance` | History across sessions |

`roll_no` is an integer and globally unique. `image_url` must be an absolute
HTTP(S) URL - upload the photograph to Cloudflare R2 first and send the URL; the
backend does not handle the upload.

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
  "declared_strength": 20000,   // classrooms.strength
  "present": 7930,
  "absent": 0,                  // stays 0 until the session is closed
  "unrecorded": 12070,          // roster members not seen yet
  "pending_observations": 12    // buffered in this worker, not written yet
}
```

Field semantics worth wiring into the UI correctly:

- `timestamp` is the **first** time the student was recognised in the session -
  use it for late arrivals, not as "last seen".
- `confidence` is the **highest** similarity observed during the session.
- `absent: 0` while `session_status` is `ACTIVE` is correct, not a bug: absence
  is derived at close. Show `unrecorded` as "not seen yet", never as "absent".
- `pending_observations` counts what one worker has buffered; with several
  workers it is per-worker, so treat it as a liveness hint rather than a total.

### 3.6 Closing a session

```jsonc
// POST /sessions/{id}/close
{
  "session_id": "00000000-0000-0000-0000-000000000000",
  "closed_at": "2026-08-06T10:00:03.117000",
  "flushed_observations": 12,  // written from the buffer during close
  "present": 7930,
  "absent_marked": 12070,      // Absent rows created by this close
  "roster_count": 20000,
  "total_recorded": 20000
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
  "request_id": "req-0a1b2c3d4e5f",
  "frame_id": "frame-000042",
  "latency_ms": 0.0,
  "session_id": "00000000-0000-0000-0000-000000000000",
  "faces": [
    {
      "bbox": [104, 53, 221, 194],
      "detection_score": 0.97,
      "state": "MATCH",                 // MATCH | HUMAN_REVIEW | UNKNOWN
      "student_id": "00000000-0000-0000-0000-000000000000",
      "similarity": 0.71,
      "second_best_similarity": 0.57,
      "margin": 0.14,
      "matched_template": "surgical_blue",
      "reason": "Similarity and identity margin passed the calibrated thresholds.",
      "attendance_recorded": true,
      "candidates": [
        {"student_id": "00000000-0000-0000-0000-000000000000", "similarity": 0.71, "matched_template": "surgical_blue"}
      ]
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

---

## 4. Suggested frontend flows

**Attendance dashboard.** Resolve the ACTIVE session
(`GET /sessions?class_id=...&status=ACTIVE`), poll
`GET /sessions/{id}/attendance/summary` every few seconds - align the interval
with `capture_interval_seconds` from `GET /runtime` - and load the register with
keyset paging. Present rows appear progressively while the lecture runs.

**Closing.** Call `POST /sessions/{id}/close` once, display the report, then
refresh the register: `unrecorded` becomes 0 and `absent` becomes non-zero.

**Enrollment.** Upload the photograph to R2, `POST /students` with the URL, then
`POST /students/{id}/enroll` with the image. Handle `503` from the enroll step
until the models exist - the student row is still created and usable.

**Degraded mode.** Call `GET /health` and `GET /models` at startup. If
`recognition_ready` is false, hide the live-recognition surface and label the
attendance views as manual/partial rather than letting operators believe
recognition is running.
