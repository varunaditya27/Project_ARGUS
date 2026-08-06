# enrollment/

Seeds the demo gallery: 5,802 identities (LFW 5,749 + MFR2 53) enrolled
unmasked, plus masked template variants for the 400-identity subset
that already has them from `evaluation/`. This is the "database of
people" the presentation demo recognizes a masked person against - the
whole point is showing the system picks the *correct* one of 5,802, not
a random lookalike.

## Why this writes to ChromaDB directly instead of going through the backend's HTTP API

The backend's real schema (`backend/app/recognition/adapters/chroma.py`)
is respected exactly - collection `argus_templates`, ids
`{student_id UUID}:{mask_type}`, metadata `student_id`/`mask_type`/
`model_version` - so `/recognize` reads this gallery correctly with no
changes on the backend side. What's different is *how* it gets there:
`POST /students/{id}/enroll` is the right call for one real student
enrolling one photo, but is one HTTP round trip per person, requires a
running Postgres + a real classroom + real student rows for 5,802
people who aren't actual students - it's the wrong tool for seeding a
demo dataset at this scale. `seed_chroma.py` writes the same schema
directly and finishes in under a minute.

This intentionally has **no corresponding Postgres `students` rows**.
`/recognize` without a `session_id` never touches Postgres - it's pure
Chroma search + `decide()` - so recognition against this gallery works
correctly through the real API. Only attendance-recording (which needs
`session_id` and a real student row) wouldn't apply here, which is
correct: these are recognition-demo identities, not real students.

## Files

- `build_manifest.py` - one unmasked photo per identity ->
  `datasets/processed/enrollment_manifest.csv`. LFW: 5,749 identities
  (verified against the raw dataset, not the >=2-image eval subset).
  MFR2: 53, using each identity's earliest `no-mask`-labeled photo.
- `build_embeddings_local.py` - runs `embeddings/generate.py` (same
  thread-capped, `det_size=160` pipeline as evaluation) over that
  manifest -> `enrollment_embeddings.npz`. ~53 min on this machine's
  CPU. A Colab GPU path was attempted and abandoned after stacking
  environment failures (onnxruntime-gpu/plain-onnxruntime file
  clobbering, a NumPy 1.x/2.x ABI mismatch, a cuDNN version mismatch)
  cost more time than the run it was meant to save.
- `seed_chroma.py` - the actual seeding script. Combines
  `enrollment_embeddings.npz` (5,802 UNMASKED templates) with the
  masked variants already computed for the 400-identity eval subset in
  `embeddings/embeddings.npz`, generates a stable UUID per identity
  (`uuid5`, reproducible across reruns - reseeding never duplicates),
  and upserts everything into `backend/.chroma` in 500-row batches
  (Chroma's own limit). Deduplicates to one embedding per
  (identity, mask_type) first - some identities have several source
  photos masked with the same mask type, which collide on the same id
  otherwise (hit this as a real crash, not a hypothetical).
- `enrollment_identity_map.csv` - `student_id` (uuid) -> real
  dataset/identity name, since there's no Postgres row to resolve this
  from. The presenter's cheat sheet for the demo.

## Verified end to end, not just seeded

8,700 templates total (5,802 unmasked + 2,898 deduplicated masked
variants). Queried Chroma directly with masked probes that were
excluded from the gallery during dedup (a genuine held-out test, not
matching an embedding against itself): **2,688/2,797 (96.1%)** correctly
resolved to their true identity against the full 5,802-identity
gallery - a harder test than `evaluation/`'s numbers since every other
enrolled identity is a potential wrong answer, not just the 400-subset.
Run the check yourself:

```python
import chromadb, numpy as np
client = chromadb.PersistentClient(path="backend/.chroma")
collection = client.get_collection("argus_templates")
print(collection.count())  # 8700
```

## A cross-team note worth knowing

Backend's `ARGUS_DETECTION_INPUT_SIZE` defaults to 640, matching
InsightFace's own default - correct for normal enrollment photos and
webcam frames. But this is the exact setting that broke detection
almost entirely on tightly-cropped 128-160px images during this
pipeline's own masking work (RWMFD output, MFR2's raw photos - both
pre-cropped with no margin): SCRFD's anchors stop matching once a small
image gets upsampled 4-5x into a 640x640 canvas. If MFR2's raw photos
are ever fed through the backend's `/enroll` endpoint directly (rather
than through this pipeline, which already uses `det_size=160`), expect
the same failure.
