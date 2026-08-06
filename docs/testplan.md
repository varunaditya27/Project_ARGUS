# ARGUS Test Plan

## What this plan is for

The system must enroll a person correctly, recognise them while masked, reject
strangers, survive a missing dependency, and explain uncertain results instead
of forcing every face into a match. This document lists every automated case,
what it proves, and what is deliberately not covered here.

Counts at the time of writing: **210 automated tests** in `backend/tests`
(177 distinct cases, the rest parametrised variants), plus the offline
evaluation suite in `tests/`.

---

## 1. How the suites are organised

| Tier | Location | Crosses | Needs |
|---|---|---|---|
| Unit | `backend/tests/unit` | nothing - one module, in memory | nothing |
| Integration | `backend/tests/integration` | PostgreSQL, the ASGI app, the filesystem | `ARGUS_TEST_DATABASE_URL` |
| Acceptance | `backend/tests/acceptance` | the whole system over HTTP | database, Chroma, `models/buffalo_l` |
| Offline evaluation | `tests/` (repository root) | the embedding pipeline over a labelled set | the LFW/MFR2 download |

Shared scaffolding is kept out of the test bodies: `tests/conftest.py` holds the
fixtures and the skip guards, `tests/helpers.py` the roster builders and test
doubles, `tests/images.py` the image builders, and
`tests/acceptance/conftest.py` the running-system fixture. A tier that cannot
run skips with a named reason rather than passing silently.

```bash
cd backend
pytest tests/unit                       # no services required
$env:ARGUS_TEST_DATABASE_URL = "postgresql+asyncpg://argus:argus@localhost:5432/argus_test"
pytest tests/integration
pytest tests/acceptance                 # also needs models/buffalo_l
pytest                                  # everything
```

---

## 2. Unit tests

Pure logic, no I/O. **N** marks a normal case, **E** an edge case.

### 2.1 Face alignment - `unit/test_alignment.py`

| ID | Case | |
|---|---|---|
| UT-01 | reference landmarks map to themselves | N |
| UT-02 | a scaled and shifted face is normalised back | N |
| UT-03 | a rotated face is normalised back | E |

### 2.2 Decision layer - `unit/test_decision.py`

| ID | Case | |
|---|---|---|
| UT-04 | an identity scores as its best template | N |
| UT-05 | a match requires both score and margin | N |
| UT-06 | a score between review and match becomes review | N |
| UT-07 | no neighbours at all is unknown | E |
| UT-08 | uncalibrated thresholds can never match | E |
| UT-09 | a close runner-up forces review | E |
| UT-10 | a stranger is unknown, not the nearest neighbour | E |
| UT-11 | a single candidate has no margin to fail | E |
| UT-12 | a quality note downgrades a would-be match | E |

### 2.3 Capture buffer and flusher - `unit/test_capture.py`

| ID | Case | |
|---|---|---|
| UT-13 | repeated detections collapse to one row | N |
| UT-14 | draining empties the session | N |
| UT-15 | the flusher persists each buffered session | N |
| UT-16 | a requeue merges back into the buffer | E |
| UT-17 | the buffer is bounded | E |
| UT-18 | a failed flush requeues instead of losing attendance | E |

### 2.4 Mask synthesis - `unit/test_masks.py`

| ID | Case | |
|---|---|---|
| UT-19 | every configured variant is rendered | N |
| UT-20 | only the requested variants are rendered | N |
| UT-21 | the variants differ from each other | N |
| UT-22 | rendering is deterministic across runs | N |
| UT-23 | the eye region is never covered (per variant) | E |
| UT-24 | the chin is always covered (per variant) | E |
| UT-25 | an unknown variant is reported and skipped | E |
| UT-26 | no known variant leaves the component unconfigured | E |
| UT-27 | a larger crop is handled by scaling | E |

### 2.5 Archive safety - `unit/test_archives.py`

| ID | Case | |
|---|---|---|
| UT-28 | entries resolve by full path and by bare name | N |
| UT-29 | a suffix filter hides everything else | N |
| UT-30 | directories are not entries | N |
| UT-31 | lookup ignores case and backslashes | E |
| UT-32 | a bare name in two folders is ambiguous | E |
| UT-33 | traversal entries reject the whole archive | E |
| UT-34 | an upload larger than the cap is refused before reading | E |
| UT-35 | too many files is refused | E |
| UT-36 | a declared decompression bomb is refused | E |
| UT-37 | an entry that lied about its size is refused on read | E |
| UT-38 | bytes that are not a ZIP are a request error | E |
| UT-39 | an empty archive yields nothing | E |

### 2.6 Configuration - `unit/test_config.py`

| ID | Case | |
|---|---|---|
| UT-40 | comma-separated values become lists | N |
| UT-41 | a log level is accepted in any case | N |
| UT-42 | local storage needs nothing extra | N |
| UT-43 | an explicit model path wins over the pack root | N |
| UT-44 | a blank threshold means uncalibrated, not zero | E |
| UT-45 | a review threshold above the match threshold is refused | E |
| UT-46 | equal thresholds are allowed | E |
| UT-47 | a similarity outside the cosine range is refused | E |
| UT-48 | persistent Chroma needs a path | E |
| UT-49 | HTTP Chroma needs both host and port | E |
| UT-50 | R2 names every setting it is missing | E |
| UT-51 | without a pack root a model is simply unset | E |
| UT-52 | positive-only settings reject zero | E |

### 2.7 Object storage - `unit/test_object_storage.py`

| ID | Case | |
|---|---|---|
| UT-53 | an image is written and addressable by its URL | N |
| UT-54 | the same image reuses its key | N |
| UT-55 | different images get different keys | N |
| UT-56 | every accepted format is identified by magic bytes | N |
| UT-57 | an empty key prefix leaves no leading slash | E |
| UT-58 | bytes that are not an image are rejected | E |
| UT-59 | an empty upload is rejected | E |
| UT-60 | no staging file survives a write | E |
| UT-61 | lookalikes are not mistaken for images | E |

### 2.8 Roster CSV parsing - `unit/test_roster_csv.py`

| ID | Case | |
|---|---|---|
| UT-62 | the header is case-insensitive, order-independent and BOM tolerant | N |
| UT-63 | a `class_id` column carries the classroom when no request field is given | N |
| UT-64 | `image_url` rows need no archive and no upload | N |
| UT-65 | archive entries resolve by bare name inside a folder | N |
| UT-66 | missing columns are a request error | E |
| UT-67 | invalid roll numbers are reported without a roll number | E |
| UT-68 | a missing student name is reported with the roll number | E |
| UT-69 | a duplicate roll number inside the file skips the second row | E |
| UT-70 | more rows than allowed rejects the request | E |
| UT-71 | a missing archive entry is a row error | E |
| UT-72 | an `image_filename` without an archive is a row error | E |
| UT-73 | zip-slip entries reject the archive | E |
| UT-74 | an oversize archive upload is rejected | E |
| UT-75 | an archive declaring too much uncompressed data is rejected | E |
| UT-76 | an entry larger than one enrollment image is rejected | E |

### 2.9 Roster import orchestration - `unit/test_roster_import.py`

| ID | Case | |
|---|---|---|
| UT-77 | an `image_url` is stored verbatim | N |
| UT-78 | archive images are uploaded before the rows are written | N |
| UT-79 | a dry run validates without writing or uploading | N |
| UT-80 | already-enrolled roll numbers are skipped, never updated | E |
| UT-81 | rows pointing at an unknown classroom are skipped | E |
| UT-82 | an archive entry that is not an image is skipped | E |
| UT-83 | losing a concurrent insert is a row error, not a failure | E |
| UT-84 | an oversize CSV is rejected before parsing | E |
| UT-85 | missing object storage fails the import (dry run and committed) | E |

---

## 3. Integration tests

Real PostgreSQL, the real ASGI application, the real filesystem.

### 3.1 Schema - `integration/test_migration_matches_models.py`

| ID | Case | |
|---|---|---|
| IT-01 | the Alembic migration produces exactly the ORM schema | N |

### 3.2 Attendance lifecycle - `integration/test_attendance_lifecycle.py`

| ID | Case | |
|---|---|---|
| IT-02 | attendance is written during the session | N |
| IT-03 | later intervals keep the best confidence and the first sighting | N |
| IT-04 | close marks absentees once and is not repeatable | N |
| IT-05 | absent rows carry the documented sentinel (0.0, close instant) | N |
| IT-06 | keyset pagination walks the whole register | N |
| IT-07 | observations outside the roster are rejected by SQL | E |
| IT-08 | closed sessions stop accepting attendance | E |
| IT-09 | closing an unknown session is a 404 | E |

### 3.3 Business rules - `integration/test_roster_rules.py`

| ID | Case | |
|---|---|---|
| IT-10 | one ACTIVE session per classroom | N |
| IT-11 | a classroom can open a new session once the first closes | N |
| IT-12 | deleting a student removes their attendance | N |
| IT-13 | concurrent opens cannot both win | E |
| IT-14 | a duplicate roll number is rejected | E |

### 3.4 Classroom endpoints - `integration/test_classroom_api.py`

| ID | Case | |
|---|---|---|
| IT-15 | a created classroom reads back | N |
| IT-16 | the detail view counts the real roster, not the declared strength | N |
| IT-17 | listing filters by department and semester | N |
| IT-18 | offset paging walks the list without repeats | N |
| IT-19 | an offset past the end returns an empty page | E |
| IT-20 | an unknown classroom is a 404 | E |
| IT-21 | a malformed UUID is a validation error | E |
| IT-22 | out-of-range fields are refused (5 variants) | E |
| IT-23 | a page size beyond the cap is refused | E |

### 3.5 Student endpoints - `integration/test_student_api.py`

| ID | Case | |
|---|---|---|
| IT-24 | a created student reads back | N |
| IT-25 | a student may be unassigned to any classroom | N |
| IT-26 | keyset paging walks the roster in roll-number order | N |
| IT-27 | deleting a student removes them | N |
| IT-28 | a duplicate roll number is a conflict | E |
| IT-29 | roll numbers are unique across classrooms, not per classroom | E |
| IT-30 | a roll number that is not a positive integer is refused (4 variants) | E |
| IT-31 | an unusable `image_url` is refused (3 variants) | E |
| IT-32 | the cursor is absent on a short page | E |
| IT-33 | unknown students are 404s on read, delete and history | E |

### 3.6 Session endpoints - `integration/test_session_api.py`

| ID | Case | |
|---|---|---|
| IT-34 | opening a session returns it ACTIVE | N |
| IT-35 | a new session opens once the first closes | N |
| IT-36 | listing filters by status and by date | N |
| IT-37 | two classrooms run sessions in parallel | N |
| IT-38 | a classroom cannot hold two ACTIVE sessions | E |
| IT-39 | a session that ends before it starts is refused | E |
| IT-40 | a zero-length session is refused | E |
| IT-41 | an unknown status filter is refused | E |
| IT-42 | a session for an unknown classroom is refused | E |
| IT-43 | reading and closing an unknown session are 404s | E |
| IT-44 | closing twice is a conflict | E |

### 3.7 Image upload and serving - `integration/test_image_upload.py`

| ID | Case | |
|---|---|---|
| IT-45 | an upload is stored and served back byte for byte | N |
| IT-46 | uploading does not need a database | N |
| IT-47 | a disabled storage backend is reported, not worked around | E |
| IT-48 | a file that is not an image is refused | E |
| IT-49 | a missing file field is a validation error | E |
| IT-50 | the media mount does not serve outside its root | E |

### 3.8 Unprovisioned API - `integration/test_api_smoke.py`

| ID | Case | |
|---|---|---|
| IT-51 | `/health` reports degraded without dependencies | N |
| IT-52 | `/models` reports missing components and uncalibrated thresholds | N |
| IT-53 | database endpoints fail with a configuration hint | E |
| IT-54 | recognition never invents a result | E |
| IT-55 | validation errors use the shared envelope | E |
| IT-56 | an unreachable database is reported, not crashed | E |
| IT-57 | an unknown route uses the shared envelope | E |
| IT-58 | import returns 503 when object storage is disabled | E |
| IT-59 | import reports a missing header with the shared envelope | E |

---

## 4. Acceptance tests

End to end over HTTP, against the real SCRFD detector, ArcFace embedder, mask
synthesizer, Chroma store and PostgreSQL. Each case is one user-visible
promise.

Two fixture decisions are stated openly in `acceptance/conftest.py`. The
decision thresholds are **provisional** values chosen so the decision layer can
be exercised at all - calibration is `evaluation/calibrate_thresholds.py`, and
no case here asserts an accuracy figure. The quality gates, which ship
disabled, are enabled so AT-09 has something to test.

### 4.1 Enrollment - `acceptance/test_enrollment.py`

| ID | Case | Expected | |
|---|---|---|---|
| AT-01 | enroll one clear unmasked photograph | the identity and its unmasked template are stored | N |
| AT-02 | masked variants for that identity | every configured variant is stored against the same student | N |
| AT-02b | re-enrolling the same person | the gallery is replaced, not doubled | E |
| AT-03 | a photograph with no face | refused, message names the problem | E |
| AT-04 | a photograph with two faces | refused; enrollment wants one person | E |
| AT-05a | a truncated image | refused, and the service still answers afterwards | E |
| AT-05b | a file that is not an image at all | refused | E |
| AT-05c | an upload beyond the size cap | refused before decoding | E |
| AT-05d | enrolling an unknown student id | 404 | E |

### 4.2 Recognition - `acceptance/test_recognition.py`

| ID | Case | Expected | |
|---|---|---|---|
| AT-06 | an enrolled person, unmasked | MATCH, with that student id | N |
| AT-07 | the same person with the lower face covered | still resolves to that identity, never UNKNOWN | N |
| AT-08 | a face with no gallery entry | UNKNOWN and no student id, not the nearest neighbour | N |
| AT-09a | a heavily blurred face | never a MATCH, and a reason is given | E |
| AT-09b | a face too small to identify | never a MATCH | E |
| AT-10 | several people in one frame | one box and one decision each | N |
| AT-10b | a frame with nobody in it | no faces, not an error | E |
| AT-10c | an undecodable frame | refused with the shared envelope | E |
| AT-10d | the bounding box lies inside the frame | coordinates are ordered and non-negative | E |

The occlusion in AT-07 is drawn by the test, not by the enrollment
synthesizer, so the probe is not produced by the same code that built the
gallery.

### 4.3 Attendance - `acceptance/test_attendance.py`

| ID | Case | Expected | |
|---|---|---|---|
| AT-11 | recognise an enrolled student during an ACTIVE session | a Present row appears after the capture interval | N |
| AT-11b | see the same person twice | still one row | E |
| AT-12 | close the session | everyone unseen becomes Absent, in one pass | N |
| AT-13 | recognise against a closed session | nothing is recorded | E |
| AT-14a | delete an identity | its vectors leave the gallery and it no longer matches | N |
| AT-14b | delete an identity | its attendance rows go with it | E |
| AT-14c | recognise with no session id | a lookup, not attendance | E |

### 4.4 Operating without full provisioning - `acceptance/test_operations.py`

| ID | Case | Expected | |
|---|---|---|---|
| AT-15a | uncalibrated thresholds (the shipped default) | the person is found but the state is HUMAN_REVIEW and the reason says why | N |
| AT-15b | `/models` while uncalibrated | `recognition_ready: false` even though every component loaded | N |
| AT-15c | closing an uncalibrated session | everyone Absent - the visible consequence of refusing to guess | E |
| AT-16a | nothing provisioned at all | `/health` degraded, recognition 503 naming the missing setting | E |
| AT-16b | an unreachable database | `dependency_unavailable`, not a crash | E |
| AT-17a | a roster import with three bad rows | the good row is committed, each bad row is reported with its reason | N |
| AT-17b | the same import as a dry run | report identical, nothing written | E |
| AT-18 | an offline batch over an archive | every image decided, non-images skipped | N |

---

## 5. Offline evaluation suite

`tests/` at the repository root covers the measurement pipeline rather than the
service: manifest parsing, evaluation set construction, metrics and
multi-template aggregation (`test_manifest_parsing.py`, `test_eval_sets.py`,
`test_metrics.py`, `test_multi_template.py`, `test_generate.py`). Accuracy
numbers come from there, against LFW and MFR2, and are reported in
`evaluation/README.md`.

---

## 6. What is not covered here, and why

- **Accuracy.** The backend suite proves behaviour, not recognition rates. The
  repository ships one public face image, so an impostor-versus-populated-gallery
  test would be theatre; that measurement belongs to the evaluation suite over a
  labelled set.
- **Threshold calibration.** The values used in acceptance are provisional. Until
  `evaluation/calibrate_thresholds.py` is run against the downloaded dataset, the
  deployed configuration leaves them empty and the system marks nobody present.
- **The frontend.** Types are checked (`tsc --noEmit`), lint and production build
  run, but there are no component or browser tests yet.
- **Load.** `benchmarks/` measures capture throughput and vector search latency at
  20 000 students; it is run manually, not on every commit.
- **Continuous integration.** No pipeline runs any of this automatically yet.

---

## 7. Test data

| Artefact | Purpose |
|---|---|
| `backend/tests/fixtures/sample_face.jpg` | the one public portrait; every acceptance image derives from it |
| `backend/tests/images.py` | builds the blank, two-face, blurred, tiny, occluded and truncated probes at run time |
| `backend/tests/helpers.py` | CSV and ZIP builders, the recording storage double, the in-memory import service |
| `samples/roster_import/` | a 12-row roster, its archive, and a deliberately broken CSV for the import screen |
| `datasets/processed/*.csv` | LFW and MFR2 manifests used by the evaluation suite |

Nothing in the suite depends on an image that is not in version control or
built from one that is.
