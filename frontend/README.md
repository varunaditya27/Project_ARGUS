# Project ARGUS - Frontend

Next.js 16 (App Router) operator console for the ARGUS attendance backend. Every
screen reads from the FastAPI service in `../backend`; there is no mock data and
nothing is displayed that the API cannot supply.

## Quick start

```bash
cd frontend
npm install
cp .env.local.example .env.local     # then point it at your backend
npm run dev                          # http://localhost:3001
```

The backend must be running and reachable, and its `ARGUS_CORS_ORIGINS` must
include this origin:

```bash
ARGUS_CORS_ORIGINS=http://localhost:3001
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Base URL of the API, including the prefix. |

Enrollment images are served by whichever object storage the backend is
configured with. For local development set `ARGUS_OBJECT_STORAGE_MODE=local` and
the backend stores images on disk and serves them from `/media` - see
`docs/database_setup.md`.

## Layout

```text
src/
├── app/                  # one directory per route
│   ├── page.tsx          # dashboard: session counts, dependency health
│   ├── enrollment/       # file picker or webcam capture -> upload -> create -> enroll
│   ├── live-recognition/ # posts webcam frames to POST /recognize
│   ├── attendance/       # per-session register, status filter, CSV export
│   ├── students/         # roster with keyset pagination
│   ├── import/           # bulk CSV + ZIP roster import
│   ├── classrooms/       # classroom list and creation
│   ├── sessions/         # open a session, close it, jump to its register
│   ├── reports/          # attendance rates derived from session summaries
│   └── settings/         # read-only view of /models and /health
├── services/             # one module per API area; the only place fetch is called
├── types/                # mirrors backend/app/schemas, snake_case as the API sends it
├── components/           # ui primitives, webcam viewport, shared async states
└── hooks/, store/        # camera driver, sidebar and theme state
```

## How it talks to the backend

`services/api.ts` is the only module that calls `fetch`. It prefixes the base
URL, unwraps the backend's error envelope into an `ApiError` carrying `code`,
`status` and `details`, and exposes `get`/`post`/`postForm`/`delete`. Pages use
TanStack Query on top of the service modules, and render failures with
`components/common/async-state.tsx`, which shows the backend's own message
instead of a generic one.

Endpoints in use:

| Screen | Calls |
|---|---|
| Dashboard | `GET /health`, `GET /models`, `GET /classrooms`, `GET /sessions`, `GET /sessions/{id}/attendance/summary` |
| Enrollment | `POST /students/image`, `POST /students`, `POST /students/{id}/enroll` |
| Live recognition | `GET /models`, `GET /sessions?status=ACTIVE`, `GET /students`, `POST /recognize` |
| Attendance | `GET /sessions`, `GET /sessions/{id}/attendance`, `.../attendance/summary` |
| Students | `GET /students`, `DELETE /students/{id}` |
| Bulk import | `POST /students/import` |
| Classrooms | `GET /classrooms`, `POST /classrooms` |
| Sessions | `GET /sessions`, `POST /sessions`, `POST /sessions/{id}/close` |
| Reports | `GET /sessions`, `GET /classrooms`, `.../attendance/summary` |
| System | `GET /models`, `GET /health` |

## What the UI deliberately does not show

The schema in `docs/db.md` has no student email, no per-student accuracy score,
no camera inventory and no "late" attendance state, so no screen invents them.
Recognition marks attendance only when `GET /models` reports
`recognition_ready: true`; until the thresholds are calibrated the API answers
`HUMAN_REVIEW` or `UNKNOWN` and the header says so.

## Checks

```bash
npx tsc --noEmit    # types
npm run lint        # eslint, including the React Compiler rules
npm run build       # production build
```
