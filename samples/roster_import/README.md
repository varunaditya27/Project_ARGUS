# Sample roster import

Files for exercising `POST /students/import` and the Bulk Import screen.

| File | What it is |
|---|---|
| `roster.csv` | 12 valid rows, roll numbers 101-112, each pointing at an entry in `photos.zip`. |
| `photos.zip` | 12 entries named `student_101.jpg` … `student_112.jpg`. |
| `roster_with_errors.csv` | 7 rows, each tripping a different validation rule, for seeing the per-row report. |
| `build_roster.py` | Builds a CSV plus archive from your own photographs or from the LFW manifests. |

**Every entry in `photos.zip` is the same photograph** - `tests/fixtures/sample_face.jpg`,
the only public face image in the repository. That is enough to exercise the
import, the roster and the object-storage upload, but it is not an identity
test: enrolling all twelve would put twelve labels on one face. Use
`build_roster.py` with real per-student photographs before demonstrating
recognition.

## Using it

In the UI, open **Bulk Import**, choose `roster.csv` and `photos.zip`, pick a
classroom from the dropdown, and leave **Dry run** on for the first pass. The
report tells you what would be written. Turn dry run off to commit.

The `class_id` column is deliberately empty, because the classroom dropdown
supplies it. Over curl you pass it as a form field instead:

```bash
curl -X POST http://localhost:8000/api/v1/students/import \
  -F "csv_file=@roster.csv" \
  -F "images=@photos.zip" \
  -F "class_id=<classroom-uuid>" \
  -F "dry_run=true"
```

The backend needs somewhere to put the photographs, so
`ARGUS_OBJECT_STORAGE_MODE` must be `local` or `r2`; while it is `disabled` an
import carrying images answers `503` rather than inventing a URL.

## The two ways a row gets an image

A row either names a file in the archive (`image_filename`) or already quotes a
hosted **https** URL (`image_url`), in which case no archive is needed and
nothing is uploaded. Plain `http` is rejected. `roster_with_errors.csv` has one
row of each kind.

## What the error file demonstrates

| Row | Rule it breaks |
|---|---|
| 121 | valid - it is there so the duplicate below has something to collide with |
| 122 | valid - the hosted https URL route, no archive entry needed |
| `CS2024023` | `roll_no` must be an integer; `docs/db.md` makes it `INTEGER` |
| (blank name) | `student_name` is required |
| `missing_photo.jpg` | named file is not in the archive |
| 121 again | roll number already used earlier in the same file |
| `http://…` | `image_url` must be https |

Valid rows in that file are still committed when dry run is off - partial
success is the contract, and the report names every skipped row and why.

## Building a real roster

```bash
# from a folder of photographs, one per student, filename becomes the name
python build_roster.py --photos ./my_photos --start-roll 101

# from the LFW download the evaluation pipeline already uses
python build_roster.py --manifest ../../datasets/processed/enrollment_manifest.csv \
    --root ~/datasets/raw/LFW --count 200
```

Both write `roster.csv` and `photos.zip` next to each other, ready to upload.
