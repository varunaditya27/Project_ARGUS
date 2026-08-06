# Accuracy comparison across techniques

Quick-reference summary. Full breakdowns (TAR@FAR, per-mask-type numbers)
are in `results.json` and `multi_template_results.json` in this folder;
methodology and honest framing are in `README.md`.

## 1. Required baseline

One unmasked embedding per identity as gallery, zero training.

| Dataset | Unmasked-vs-unmasked | Masked-vs-unmasked | Generalization gap |
|---|---|---|---|
| LFW subset (400 identities) | 96.58% | 96.26% | 0.32pp |
| MFR2 (53 identities, real masks) | 100% | 98.83% | 1.17pp |

**By mask type (LFW subset):**

| Mask type | Rank-1 | Source |
|---|---|---|
| N95, surgical_blue | 97.48% | MaskTheFace |
| KN95, cloth, surgical | 97.22% | MaskTheFace |
| **rwmfd_black** | **93.51%** | RWMFD |
| **rwmfd_blue** | **93.43%** | RWMFD |

RWMFD sits ~3.7-4pp below every MaskTheFace variant, consistently -
survived a full pipeline re-run, so it's real, not noise.

## 2. Multi-template gallery matching ("ARGUS template system")

Adds one embedding per (identity, mask type) as extra gallery templates.
Zero training, reuses embeddings already computed.

| Dataset | Baseline rank-1 | Multi-template rank-1 | Gain |
|---|---|---|---|
| LFW subset | 96.26% | 96.61% | +0.35pp |
| MFR2 | 98.83% | 100% | +1.17pp |

Modest gains overall (baseline was already near-ceiling), concentrated
exactly where the baseline was weakest: `rwmfd_black` 93.51% -> 93.98%,
`rwmfd_blue` 93.43% -> 94.33%.

## 3. Fine-tuning ArcFace

Explored (CBAM attention + embedding-consistency loss), **abandoned**
before producing numbers. Training risk/time didn't justify itself
against the zero-training alternatives above, given the phase budget.

## 4. Full-scale seeded-gallery verification

Not a technique comparison - the most realistic number produced this
session. Held-out masked probes queried against the complete
5,802-identity demo gallery in the live ChromaDB (8,700 templates
total), a harder test than 1-3 above since every other enrolled
identity is a potential wrong answer, not just the 400-subset's own
gallery.

**2,688 / 2,797 = 96.1%** correctly resolved to their true identity.

## Honest framing

ArcFace/buffalo_l is already far more mask-robust out of the box than
older embedding models - MaskTheFace's own paper reports a ~38% TPR
*increase* after fine-tuning FaceNet, while our baseline gap here is
under 2pp with zero training. The story isn't "we closed a huge gap,"
it's "the gap was already small, multi-template matching closed most of
what remained, and RWMFD's masking approach is measurably weaker than
MaskTheFace's."
