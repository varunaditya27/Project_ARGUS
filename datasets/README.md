# datasets/

Three things live here, kept deliberately separate so it's obvious which files are original data, which are generated, and which are tooling.

```
datasets/
├── raw/            original downloads, untouched, gitignored
├── processed/      everything our pipeline generated from raw/
└── masking/        the masking tools (vendored) + our scripts around them
```

## raw/

- `LFW-dataset-archive.zip`, `LFW/` - Labeled Faces in the Wild, unpacked as-is from `vis-www.cs.umass.edu/lfw`.
- `MFR2-dataset-archive.zip`, `MFR2/` - the real masked-face evaluation set (53 identities, 269 images, both masked and unmasked per person), fetched via MaskTheFace's own `fetch_dataset.py`. Comes with `mfr2_labels.txt` (per-image mask type, including `no-mask`) and `pairs.txt` (verification pairs) - we don't relabel or resplit this, it's used as-is for the real-world eval.

Not gitignored as a blanket rule - individually large, regenerable by re-downloading, so they stay out of git history.

## processed/

Everything here is produced by scripts in `masking/scripts/`, run in this order:

| step | script | reads | writes |
|---|---|---|---|
| 1 | `select_subset.py` | `raw/LFW/` | `LFW_subset/` (symlinks) + `LFW_subset_manifest.csv` |
| 2 | `run_masktheface.py` | `LFW_subset/` | `LFW_subset_masked/` |
| 3 | `select_reduced_scope.py` | `LFW_subset_manifest.csv` | `LFW_reduced_manifest.csv` |
| 4 | `run_rwmfd.py` | `LFW_reduced_manifest.csv` | `LFW_subset_rwmfd/` |
| 5 | `build_manifest.py` | everything above + `raw/MFR2/` | `full_manifest.csv` |

`full_manifest.csv` is the only file `embeddings/build_embeddings.py` reads - it doesn't know or care about any of the folder layout above.

**Why two manifests before the final one, and why 400 identities, not 1,680:** LFW has 5,749 identities but only 1,680 have >=2 images, which is the minimum needed for both rank-1 (need a gallery image and a probe image) and verification (need a genuine pair). That's `LFW_subset` / `LFW_subset_manifest.csv` - MaskTheFace ran over all 1,680 of them.

Partway through, embedding extraction turned out to take ~1.2s/image on this machine (CPU-only, no GPU), and RWMFD re-runs face detection per mask color rather than sharing one detection pass like MaskTheFace does, making it the slow step. Running everything over the full 1,680 identities would have taken most of a day. `select_reduced_scope.py`
carves out `LFW_reduced_manifest.csv`: the first 400 identities alphabetically, capped at 4 images each (so no single celebrity with hundreds of photos skews the eval) - that's the scope RWMFD and the final embedding/evaluation runs actually use. MaskTheFace's output for the other 1,280 identities still exists on disk but isn't in the final manifest; nothing was deleted, it just wasn't worth the time to also run RWMFD and embed all of it for this pass.

Mask variants kept in the final manifest:
- MaskTheFace: `surgical`, `surgical_blue`, `N95`, `KN95`, `cloth` (5 of its 9 `--mask_type all` outputs - dropped `surgical_green`, `gas`, `empty`, `inpaint` to fit the reduced time budget)
- RWMFD: `rwmfd_blue`, `rwmfd_black` (2 of its 4 textures)

Gitignored except the manifests - they're small, deterministic text files that document exactly which images and identities went into the result, so they're worth keeping in git even though the images themselves aren't.

## masking/

- `masktheface/` - vendored copy of aqeelanwar/MaskTheFace. Left as-is   except the minimum needed to run here (downloads its own dlib landmark model into `masktheface/dlib_models/` on first use, gitignored, ~100MB).
- `rwmfd/` - vendored copy of the `wear_mask_to_face` tool from X-zhangyang/Real-World-Masked-Face-Dataset. Had a hardcoded macOS path to its dlib model and dead code around mask-color selection; both fixed, see the file for what changed and why.
- `scripts/` - ours. Orchestrates the two vendored tools and builds the manifest described above.
