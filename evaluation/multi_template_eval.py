"""Compares design.md's two evaluation modes: required baseline vs the ARGUS multi-template system."""

import json
import os

from evaluation import eval_sets, multi_template
from evaluation.baseline_eval import evaluate_split, evaluate_by_mask_type

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_PATH = os.path.join(BASE_DIR, "embeddings", "embeddings.npz")
RESULTS_PATH = os.path.join(BASE_DIR, "evaluation", "multi_template_results.json")


# prints and returns the ARGUS template-system results for one dataset, next to its single-template baseline
def report_for_dataset(name, baseline_masked, template_sets):
    print(f"\n=== {name}: ARGUS template system ===")
    print(f"gallery size (templates): {len(template_sets['gallery_ids'])}")

    templated = evaluate_split(template_sets["gallery_ids"], template_sets["gallery_emb"],
                                template_sets["masked_probe_ids"], template_sets["masked_probe_emb"])
    by_mask_type = evaluate_by_mask_type(template_sets["gallery_ids"], template_sets["gallery_emb"],
                                          template_sets["masked_probe_ids"], template_sets["masked_probe_emb"],
                                          template_sets["masked_probe_types"])

    if baseline_masked and templated:
        print(f"required baseline (unmasked gallery)  rank1={baseline_masked['rank1_accuracy']:.4f}")
        print(f"ARGUS template system                 rank1={templated['rank1_accuracy']:.4f}")
        gain = templated["rank1_accuracy"] - baseline_masked["rank1_accuracy"]
        print(f"gain from multi-template matching: {gain:+.4f}")

    print("by mask type:")
    for mask_type, result in by_mask_type.items():
        print(f"  {mask_type:20s} rank1={result['rank1_accuracy']:.4f}  auc={result['roc_auc']:.4f}  n={result['n_probes']}")

    return {"argus_template_system": templated, "by_mask_type": by_mask_type}


# runs both evaluation modes on LFW_subset + MFR2 and writes multi_template_results.json
def run():
    data = eval_sets.load(EMBEDDINGS_PATH)

    lfw_baseline = evaluate_split(*eval_sets.pick_gallery(data, "lfw_subset", eval_sets.LFW_UNMASKED_TYPE)[:2],
                                   *eval_sets.masked_probes(data, "lfw_subset")[:2])
    lfw_templates = multi_template.build_template_sets(data, "lfw_subset", eval_sets.LFW_UNMASKED_TYPE)

    mfr2_baseline = evaluate_split(*eval_sets.pick_gallery(data, "mfr2", eval_sets.MFR2_UNMASKED_TYPE)[:2],
                                    *eval_sets.masked_probes(data, "mfr2")[:2])
    mfr2_templates = multi_template.build_template_sets(data, "mfr2", eval_sets.MFR2_UNMASKED_TYPE)

    results = {
        "lfw_subset": report_for_dataset("LFW subset (synthetic masks)", lfw_baseline, lfw_templates),
        "mfr2": report_for_dataset("MFR2 (real masked photos)", mfr2_baseline, mfr2_templates),
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nfull results written to: {RESULTS_PATH}")


if __name__ == "__main__":
    run()
