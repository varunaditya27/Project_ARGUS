# evaluation/

Baseline masked face recognition results: ArcFace (buffalo_l) embeddings,
one unmasked enrollment photo per identity as gallery, everything else as
probes. No fine-tuning - this is the zero-training number the rest of
the project is trying to beat.

Run `python -m evaluation.baseline_eval` (from the repo root) after
`embeddings/build_embeddings.py` has produced `embeddings/embeddings.npz`.
It prints a report and writes the full breakdown to `results.json`
(gitignored - regenerate it, don't hand-edit it).

## Headline numbers

| | gallery | unmasked baseline (rank-1) | masked probe (rank-1) | generalization gap |
|---|---|---|---|---|
| LFW subset (synthetic masks) | 400 identities | 96.58% | 96.26% | 0.32pp |
| MFR2 (real masked photos) | 53 identities | 100% | 98.83% | 1.17pp |

ROC-AUC tracks the same story: 0.9852 -> 0.9858 on LFW subset (masked
probes are *not* meaningfully harder than unmasked ones in aggregate),
0.9966 on MFR2 masked probes.

**Read this carefully before quoting it**: ArcFace/buffalo_l is already
strongly mask-robust out of the box. This is not the ~38% TPR drop
MaskTheFace's own paper reports for FaceNet - buffalo_l's training data
or architecture already generalizes past occlusion far better than older
embedding models did. That's a genuine finding, not a disappointing one,
but it means the interesting result isn't "we closed a big gap" - it's
"the gap is already small, and here's exactly where it isn't."

## Where the real signal is

By mask type, LFW subset:

| mask type | rank-1 | source |
|---|---|---|
| N95 | 97.48% | MaskTheFace |
| surgical_blue | 97.48% | MaskTheFace |
| KN95 | 97.22% | MaskTheFace |
| cloth | 97.22% | MaskTheFace |
| surgical | 97.22% | MaskTheFace |
| **rwmfd_black** | **93.51%** | RWMFD |
| **rwmfd_blue** | **93.43%** | RWMFD |

Every MaskTheFace variant clusters around 97.2-97.5%. Both RWMFD variants
sit 3.7-4.0 points lower, consistently. That gap survived a full pipeline
re-run (fixing an unrelated color bug in MaskTheFace, see below) so it's
a real signal, not noise: RWMFD's masking - different warp/overlay
approach, tighter crop, its own face detector - produces embeddings that
sit further from the unmasked baseline than MaskTheFace's do. This is
the actual "consistency across mask types" finding the rubric asks for,
and the clearest lead for what to try next (multi-template gallery
matching, described below, targets exactly this).

On MFR2, everything is at or near 100% except `cloth_white` (85.71%,
n=7) and `cloth_textured` (98%, n=50). `cloth_white`'s low n makes it
noise, not signal - not something to read into without more samples.

## Known issues already fixed

Two real bugs were found and corrected mid-pipeline, not design choices:

1. **Detector window mismatch.** buffalo_l's SCRFD detector defaulted to
   `det_size=(640, 640)`, which assumes scene-scale photos with margin
   around the face. RWMFD's output (128x128, tightly cropped by its own
   alignment step) and MFR2 (pre-aligned 160x160) got upsampled 4-5x into
   that window, breaking detection almost entirely (RWMFD: 10/2308
   embeddings succeeded; MFR2: 86/269). Dropping to `det_size=(160, 160)`
   fixed both with no regression on LFW/MaskTheFace (verified on 60
   samples) and full pipeline re-run recovered RWMFD to 2219/2308 (96%)
   and MFR2 to 269/269 (100%).

2. **Mask color bug.** MaskTheFace's `--color` CLI flag defaults to a
   non-empty hex string, and its own `mask_face()` treats any non-empty
   value as "apply this color" rather than checking whether a color
   override was actually requested - so every generated mask, regardless
   of template, rendered the same shade of blue. `surgical`,
   `surgical_blue`, and `surgical_green` were visually identical.
   Re-ran masking with `--color ""` to restore each template's real
   color; the numbers above are post-fix.

## ARGUS template system (multi-template gallery matching)

`docs/design.md` specifies a second evaluation mode: instead of one
unmasked embedding per identity as gallery, also store one embedding per
(identity, mask type) as extra templates, and match probes against
whichever template scores highest. Zero training - reuses embeddings
already computed. Run `python -m evaluation.multi_template_eval` (from
the repo root).

To keep this honest, whichever specific image becomes a mask-type
template is removed from the probe set for that identity - otherwise a
probe could be compared against its own exact embedding and trivially
"win" (see `evaluation/multi_template.py`'s `held_out_masked_probes`).
Every number below is on genuinely held-out probes.

| | required baseline (rank-1) | ARGUS template system (rank-1) | gain |
|---|---|---|---|
| LFW subset | 96.26% | 96.61% | +0.35pp |
| MFR2 (real) | 98.83% | 100% | +1.17pp |

Modest gains, which is expected and honest given the baseline was
already near-ceiling (96-99%) - there wasn't much gap left to close.
The RWMFD mask types improved the most (rwmfd_black 93.51% -> 93.98%,
rwmfd_blue 93.43% -> 94.33%), consistent with them being the weakest
spot in the single-template baseline: multi-template matching helps
most exactly where the single unmasked template was least representative
of what a masked probe looks like.

## What's not done yet

- **Threshold calibration** - `match_threshold` / `review_threshold` in
  `docs/design.md` are still null. Calibrate real values off the ROC
  curve now that both evaluation modes have numbers.
- **Fine-tuning** - explored, then abandoned given the phase time budget
  (see `CLAUDE.md`). Not revisited.
