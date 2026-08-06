# Bulk Student Registration

`POST /api/v1/students/import` registers a whole roster in one request: a CSV of
students plus an optional ZIP archive of their enrollment photographs. The backend
uploads each photograph to Cloudflare R2 itself and stores the resulting URL in
`students.image_url`.

Valid rows are committed, invalid rows are skipped, and the response reports every
skipped row with the reason. It is **not** all-or-nothing.

---

# Request

`multipart/form-data`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `csv_file` | file | yes | UTF-8 CSV. A UTF-8 BOM is accepted. |
| `images` | file | no | ZIP archive holding the files named by `image_filename`. |
| `class_id` | UUID | no | Classroom for **every** row in the file. Accepted as a form field or a query parameter. |
| `dry_run` | bool | no | Default `false`. Validate and report without writing anything. Accepted as a form field or a query parameter. |

When `class_id` is supplied it applies to every row and the CSV `class_id` column
becomes optional (and is ignored). This is the common "import one classroom's
roster" case.

---

# CSV format

A header row is required. Column names are case-insensitive and may appear in any
order; unrecognised columns are ignored.

| Column | Required | Description |
|--------|----------|-------------|
| `student_name` | yes | 1-160 characters. |
| `roll_no` | yes | Integer >= 1. `students.roll_no` is INTEGER and globally UNIQUE (`docs/db.md`), so alphanumeric roll numbers such as `CS2024001` cannot be imported. |
| `class_id` | only when the request-level `class_id` is absent | UUID of an existing classroom. |
| `image_filename` | one of the two | Name of an entry inside the ZIP. |
| `image_url` | one of the two | An already-uploaded `https` URL, used as-is. |

Exactly one image source has to resolve per row: if `image_url` is present and is a
valid `https` URL it is stored verbatim and no ZIP entry is needed; otherwise
`image_filename` must match an entry in the archive.

```csv
student_name,roll_no,image_filename
Ada Lovelace,1,ada.jpg
Grace Hopper,2,photos/grace.png
Alan Turing,3,alan.jpeg
```

With no request-level `class_id`, and mixing both image sources:

```csv
student_name,roll_no,class_id,image_filename,image_url
Ada Lovelace,1,7f9c1f22-0f0e-4d1e-9d2a-2c9d1a4b5e60,ada.jpg,
Grace Hopper,2,7f9c1f22-0f0e-4d1e-9d2a-2c9d1a4b5e60,,https://images.example.com/enrollment/grace.jpg
```

## ZIP layout

Flat or foldered, both work. `image_filename` may be the bare file name or the
full path inside the archive; a bare name that occurs in two folders is ambiguous
and the row is skipped with that reason.

```text
images.zip
├── ada.jpg
└── photos/
    └── grace.png
```

Entries must be real images - JPEG, PNG, WEBP, GIF or BMP, checked by magic bytes.
An archive is rejected outright (422/413) when it is not a readable ZIP, contains an
entry with an absolute path or a `..` segment (zip-slip), declares more
uncompressed data than `ARGUS_IMPORT_MAX_ARCHIVE_BYTES`, or holds an entry larger
than `ARGUS_ENROLLMENT_MAX_IMAGE_BYTES`. An individual entry that is not a decodable
image only skips its own row.

---

# Response

```json
{
  "received_rows": 3,
  "created": 2,
  "skipped": 1,
  "dry_run": false,
  "uploaded_images": 1,
  "students": [
    {"student_id": "0f2b...", "roll_no": 1},
    {"student_id": "8ac4...", "roll_no": 3}
  ],
  "errors": [
    {"row": 3, "roll_no": 2, "reason": "a student with this roll number is already enrolled."}
  ],
  "errors_truncated": false
}
```

* `received_rows` counts data rows, excluding the header and blank lines.
* `created + skipped == received_rows`, always.
* `row` in an error is the 1-based line number in the uploaded file, so the header
  is line 1 and the first student is line 2.
* `roll_no` in an error is `null` only when the roll number itself could not be
  parsed.
* `errors` is capped at 1 000 entries; `skipped` still counts every skipped row and
  `errors_truncated` says the list was cut short.
* `uploaded_images` is lower than `created` when rows carried their own `image_url`.

## Why a row gets skipped

| Reason | Cause |
|--------|-------|
| `roll_no must be an integer >= 1` | Empty, non-numeric or non-positive roll number. |
| `student_name must be 1-160 characters` | Empty or over-long name. |
| `class_id must be a UUID` | Unparseable `class_id` cell. |
| `the referenced classroom does not exist` | No `classrooms` row with that `class_id`. |
| `roll_no N was already used on line M` | The same roll number appears twice in the file. |
| `a student with this roll number is already enrolled` | The roll number exists in PostgreSQL. Existing students are never updated. |
| `the images archive has no entry named ...` | `image_filename` does not match the archive. |
| `... is not a decodable image` | The archive entry is not a JPEG/PNG/WEBP/GIF/BMP. |
| `the roll number was registered by a concurrent request` | Another writer inserted that roll number while this import was running. |

Request-level failures use the shared error envelope instead: 413 for a file over
the configured limits, 422 for a broken header or an unsafe archive, and 503 when
PostgreSQL or object storage is unavailable.

---

# Dry run

```bash
curl -X POST "http://localhost:8000/api/v1/students/import?dry_run=true" \
  -F "csv_file=@roster.csv" \
  -F "images=@images.zip" \
  -F "class_id=7f9c1f22-0f0e-4d1e-9d2a-2c9d1a4b5e60"
```

A dry run parses the CSV, validates the archive, resolves every image, checks the
classrooms and the already-used roll numbers, and returns the same report - but
writes nothing to PostgreSQL and uploads nothing to R2. `created` is then the
number of rows that *would* be created, `uploaded_images` is `0` and `students` is
empty.

A dry run still fails with 503 when rows need an upload and object storage is not
configured: the real run could not succeed, so the dry run does not pretend
otherwise.

The real import is the same call without `dry_run`:

```bash
curl -X POST "http://localhost:8000/api/v1/students/import" \
  -F "csv_file=@roster.csv" \
  -F "images=@images.zip" \
  -F "class_id=7f9c1f22-0f0e-4d1e-9d2a-2c9d1a4b5e60"
```

---

# Cloudflare R2

Uploading is only possible once object storage is configured. Until then, rows that
carry an `https` `image_url` still import, and any row that needs an upload makes
the request fail with `503 dependency_not_configured` naming these variables -
`students.image_url` is NOT NULL and the backend never invents a URL.

| Variable | Description |
|----------|-------------|
| `ARGUS_OBJECT_STORAGE_MODE` | `disabled` (default) or `r2`. |
| `ARGUS_R2_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com`. |
| `ARGUS_R2_BUCKET` | Bucket holding the enrollment images. |
| `ARGUS_R2_ACCESS_KEY_ID` | R2 API token access key. |
| `ARGUS_R2_SECRET_ACCESS_KEY` | R2 API token secret. |
| `ARGUS_R2_PUBLIC_BASE_URL` | Public base URL of the bucket (custom domain or `r2.dev`); stored URLs are built from it. |
| `ARGUS_R2_KEY_PREFIX` | Key prefix, default `enrollment`. |

Install the extra that provides the client:

```bash
pip install -e ".[storage]"
```

Object keys are deterministic:

```text
{ARGUS_R2_KEY_PREFIX}/{student_id}/{sha256-prefix}.{ext}
```

so re-running an import overwrites the same objects instead of littering the
bucket.

---

# Limits

| Variable | Default | Applies to |
|----------|---------|------------|
| `ARGUS_IMPORT_MAX_CSV_BYTES` | 16 MiB | Size of `csv_file`. |
| `ARGUS_IMPORT_MAX_ARCHIVE_BYTES` | 1 GiB | Uploaded archive size **and** the uncompressed size it declares. |
| `ARGUS_IMPORT_MAX_ROWS` | 50 000 | Data rows per request. |
| `ARGUS_ENROLLMENT_MAX_IMAGE_BYTES` | 8 MiB | A single archive entry. |

---

# Operational notes

* **Ordering.** Images are uploaded before the rows are inserted, because
  `image_url` is NOT NULL. If an insert batch then fails, the affected rows are
  reported as skipped and the now-unreferenced object keys are logged at ERROR
  level (`Registration import left N uploaded image(s) ... unreferenced`) so they can
  be reconciled. There is no import-job table in `docs/db.md`, so the log is the
  audit trail.
* **Scale.** The already-used roll numbers are fetched with a single
  `WHERE roll_no = ANY(...)` query, classrooms are looked up once per distinct
  classroom, and rows are inserted 1 000 at a time. No statement is issued per row.
* **Concurrency.** The pre-check is an optimisation; the UNIQUE constraint on
  `roll_no` is the arbiter. Inserts use `ON CONFLICT DO NOTHING`, so a row that
  loses a race is reported as a skipped row rather than failing the request.
* **Enrollment.** This endpoint creates the roster rows only. Face templates are
  still created per student through `POST /students/{student_id}/enroll`.
