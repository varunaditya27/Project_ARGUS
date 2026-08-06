# enrollment/

Builds the production enrollment gallery: one unmasked embedding per
identity across LFW (5,749) + MFR2 (53) = 5,802 identities. This is
separate from `datasets/` and `evaluation/`, which exist to *measure*
masked recognition accuracy on a reduced 400-identity slice. This is
about *seeding the real gallery* the backend's 1:N search will run
against - full scope, no reduction.

Embedding 5,802 images takes ~53 min on this machine's CPU (0.55s/image
per `embeddings/generate.py`'s benchmark). That's not unreasonable on
its own, but running it alongside everything else competing for CPU
made a GPU path worth setting up - Colab's free T4 does the same job in
a few minutes.

## Workflow

1. **Locally:** build the manifest and package images.

   ```
   python enrollment/build_manifest.py     # -> datasets/processed/enrollment_manifest.csv
   python enrollment/package_for_colab.py  # -> enrollment/enrollment_images.zip (~54MB)
   ```

2. **Upload** `enrollment_images.zip` and `enrollment_manifest.csv` to a
   Google Drive folder (e.g. `MyDrive/argus_enrollment/`). Drive, not a
   direct browser upload widget, because a ~54MB file over a flaky
   upload widget is a bad time and Drive lets you re-run the notebook
   without re-uploading.

3. **Run `generate_embeddings_colab.ipynb`** on Colab with a T4 runtime.
   It mounts Drive, unzips, runs ArcFace (buffalo_l) with
   `CUDAExecutionProvider`, and writes `enrollment_embeddings.npz` back
   to the same Drive folder. Uses `det_size=(160, 160)`, not
   InsightFace's default 640 - LFW/MFR2 images are small enough that 640
   upsamples them past the point SCRFD's anchors still match, the same
   detector bug we hit and fixed locally (see `evaluation/README.md`).

4. **Download** `enrollment_embeddings.npz` from Drive back to
   `enrollment/` on this machine.

5. **Seed ChromaDB locally:**

   ```
   python enrollment/seed_chromadb.py
   ```

   Writes every row into a persistent Chroma collection at
   `enrollment/chroma_data/` (collection name: `enrollments`, metadata:
   `dataset`, `identity`, `filename`). Batches at 500 rows - Chroma
   rejects larger single `add()` calls.

## Why this is a separate pipeline, not a rerun of datasets/masking/

`datasets/masking/scripts/` and `embeddings/build_embeddings.py` exist
to build a *masked-vs-unmasked evaluation set* - they need synthetic
mask variants, a reduced identity count to keep masking/RWMFD time
bounded, and a gallery/probe split that never lets a probe leak into the
gallery. None of that applies here: enrollment is just "one unmasked
photo per real person," at full dataset scope, with no masking step and
no evaluation split. Reusing the eval pipeline's reduced-scope manifest
would have meant seeding a gallery of 400 people instead of 5,802 -
wrong for what "initial DB" means here.

## Files

- `build_manifest.py` - one unmasked photo per identity -> `enrollment_manifest.csv` (tracked in git, same policy as the other manifests)
- `package_for_colab.py` - zips exactly those images for upload
- `generate_embeddings_colab.ipynb` - GPU embedding generation, run on Colab
- `seed_chromadb.py` - loads the Colab output into a local persistent Chroma collection
