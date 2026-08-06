"""Calibrates match/review/margin thresholds from real ROC data - fills the nulls in
backend/.env.example (ARGUS_MATCH_THRESHOLD etc) and docs/design.md.
"""

import os

import numpy as np
from sklearn.metrics import roc_curve

from evaluation import eval_sets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_PATH = os.path.join(BASE_DIR, "embeddings", "embeddings.npz")

MATCH_FAR = 0.01
REVIEW_FAR = 0.05


# pools masked probes against their own dataset's gallery, across LFW_subset + MFR2
def pooled_masked_scores(data):
    rng = np.random.default_rng(0)
    genuine, impostor = [], []
    for dataset_name, unmasked_label in [("lfw_subset", eval_sets.LFW_UNMASKED_TYPE),
                                          ("mfr2", eval_sets.MFR2_UNMASKED_TYPE)]:
        gallery_ids, gallery_emb, _ = eval_sets.pick_gallery(data, dataset_name, unmasked_label)
        probe_ids, probe_emb, _, _ = eval_sets.masked_probes(data, dataset_name)
        sims = probe_emb @ gallery_emb.T
        id_to_col = {identity: i for i, identity in enumerate(gallery_ids)}
        for row, identity in enumerate(probe_ids):
            col = id_to_col.get(identity)
            if col is None:
                continue
            genuine.append(sims[row, col])
            others = np.delete(sims[row], col)
            n_sample = min(20, len(others))
            impostor.extend(others[rng.choice(len(others), size=n_sample, replace=False)])
    return np.array(genuine), np.array(impostor)


# similarity threshold that yields the target false-accept-rate on this data
def threshold_at_far(genuine, impostor, target_far):
    labels = np.concatenate([np.ones_like(genuine), np.zeros_like(impostor)])
    scores = np.concatenate([genuine, impostor])
    fpr, _, thresholds = roc_curve(labels, scores)
    idx = np.searchsorted(fpr, target_far, side="left")
    return float(thresholds[min(idx, len(thresholds) - 1)])


# top1-vs-top2 similarity margin for every masked probe, split by whether top1 was correct
def rank1_margins(data):
    correct_margins, wrong_margins = [], []
    for dataset_name, unmasked_label in [("lfw_subset", eval_sets.LFW_UNMASKED_TYPE),
                                          ("mfr2", eval_sets.MFR2_UNMASKED_TYPE)]:
        gallery_ids, gallery_emb, _ = eval_sets.pick_gallery(data, dataset_name, unmasked_label)
        probe_ids, probe_emb, _, _ = eval_sets.masked_probes(data, dataset_name)
        sims = probe_emb @ gallery_emb.T
        top2 = np.argsort(sims, axis=1)[:, -2:]
        for row, identity in enumerate(probe_ids):
            best_idx, second_idx = top2[row, 1], top2[row, 0]
            margin = sims[row, best_idx] - sims[row, second_idx]
            if gallery_ids[best_idx] == identity:
                correct_margins.append(margin)
            else:
                wrong_margins.append(margin)
    return np.array(correct_margins), np.array(wrong_margins)


def run():
    data = eval_sets.load(EMBEDDINGS_PATH)
    genuine, impostor = pooled_masked_scores(data)
    match_threshold = threshold_at_far(genuine, impostor, MATCH_FAR)
    review_threshold = threshold_at_far(genuine, impostor, REVIEW_FAR)

    correct_margins, wrong_margins = rank1_margins(data)
    # 5th percentile of correct-match margins: a cutoff nearly every real match clears
    minimum_margin = float(np.percentile(correct_margins, 5))

    print(f"ARGUS_MATCH_THRESHOLD={match_threshold:.4f}   (similarity at FAR={MATCH_FAR})")
    print(f"ARGUS_REVIEW_THRESHOLD={review_threshold:.4f}  (similarity at FAR={REVIEW_FAR})")
    print(f"ARGUS_MINIMUM_MARGIN={minimum_margin:.4f}    (5th pct of correct-match top1/top2 margins)")
    print()
    print(f"correct-match margins: mean={correct_margins.mean():.4f} p5={np.percentile(correct_margins, 5):.4f}")
    print(f"wrong-match margins:   mean={wrong_margins.mean():.4f}" if len(wrong_margins) else "wrong-match margins:   none observed")


if __name__ == "__main__":
    run()
