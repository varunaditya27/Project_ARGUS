"""Computes rank-1 and verification accuracy for masked-vs-unmasked-gallery on LFW_subset and MFR2."""

import json
import os

from evaluation import eval_sets, metrics

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_PATH = os.path.join(BASE_DIR, "embeddings", "embeddings.npz")
RESULTS_PATH = os.path.join(BASE_DIR, "evaluation", "results.json")


# rank-1 + verification metrics for one gallery/probe split, or None if the probe set is empty
def evaluate_split(gallery_ids, gallery_emb, probe_ids, probe_emb):
    if len(probe_ids) == 0:
        return None
    rank1 = metrics.rank1_accuracy(gallery_emb, gallery_ids, probe_emb, probe_ids)
    genuine, impostor = metrics.verification_scores(gallery_emb, gallery_ids, probe_emb, probe_ids)
    roc_auc, tar_at_far = metrics.roc_auc_and_tar(genuine, impostor)
    return {
        "n_probes": int(len(probe_ids)),
        "rank1_accuracy": rank1,
        "roc_auc": roc_auc,
        "tar_at_far": tar_at_far,
    }


# same as evaluate_split but broken out per mask type, for the robustness-across-mask-types comparison
def evaluate_by_mask_type(gallery_ids, gallery_emb, probe_ids, probe_emb, mask_types):
    results = {}
    for mask_type in sorted(set(mask_types.tolist())):
        rows = mask_types == mask_type
        result = evaluate_split(gallery_ids, gallery_emb, probe_ids[rows], probe_emb[rows])
        if result is not None:
            results[mask_type] = result
    return results


# prints and returns baseline/masked/per-mask-type results for one dataset's gallery/probe sets
def report_for_dataset(name, sets):
    print(f"\n=== {name} ===")
    print(f"gallery size (identities): {len(sets['gallery_ids'])}")

    baseline = evaluate_split(sets["gallery_ids"], sets["gallery_emb"],
                               sets["unmasked_probe_ids"], sets["unmasked_probe_emb"])
    masked = evaluate_split(sets["gallery_ids"], sets["gallery_emb"],
                             sets["masked_probe_ids"], sets["masked_probe_emb"])
    by_mask_type = evaluate_by_mask_type(sets["gallery_ids"], sets["gallery_emb"],
                                          sets["masked_probe_ids"], sets["masked_probe_emb"],
                                          sets["masked_probe_types"])

    if baseline:
        print(f"unmasked baseline  rank1={baseline['rank1_accuracy']:.4f}  auc={baseline['roc_auc']:.4f}")
    if masked:
        print(f"masked probe       rank1={masked['rank1_accuracy']:.4f}  auc={masked['roc_auc']:.4f}")
    if baseline and masked:
        gap = baseline["rank1_accuracy"] - masked["rank1_accuracy"]
        print(f"generalization gap (rank1): {gap:.4f}")

    print("by mask type:")
    for mask_type, result in by_mask_type.items():
        print(f"  {mask_type:20s} rank1={result['rank1_accuracy']:.4f}  auc={result['roc_auc']:.4f}  n={result['n_probes']}")

    return {
        "unmasked_baseline": baseline,
        "masked_probe": masked,
        "by_mask_type": by_mask_type,
    }


# runs the full LFW_subset + MFR2 evaluation and writes results.json
def run():
    data = eval_sets.load(EMBEDDINGS_PATH)
    lfw_sets = eval_sets.build_lfw_sets(data)
    mfr2_sets = eval_sets.build_mfr2_sets(data)

    results = {
        "lfw_subset": report_for_dataset("LFW subset (synthetic masks)", lfw_sets),
        "mfr2": report_for_dataset("MFR2 (real masked photos)", mfr2_sets),
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nfull results written to: {RESULTS_PATH}")


if __name__ == "__main__":
    run()
