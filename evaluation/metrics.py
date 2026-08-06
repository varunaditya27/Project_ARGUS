import numpy as np
from sklearn.metrics import roc_curve, auc as sklearn_auc

BATCH_SIZE = 1000

def rank1_accuracy(gallery_emb, gallery_ids, probe_emb, probe_ids):
    correct = 0
    for start in range(0, len(probe_emb), BATCH_SIZE):
        batch = probe_emb[start:start + BATCH_SIZE]
        sims = batch @ gallery_emb.T
        best = np.argmax(sims, axis=1)
        predicted_ids = gallery_ids[best]
        correct += np.sum(predicted_ids == probe_ids[start:start + BATCH_SIZE])
    return correct / len(probe_emb)


def verification_scores(gallery_emb, gallery_ids, probe_emb, probe_ids, n_impostor_samples=50, seed=42):
    rng = np.random.default_rng(seed)
    genuine_scores = []
    impostor_scores = []

    id_to_col = {identity: i for i, identity in enumerate(gallery_ids)}

    for start in range(0, len(probe_emb), BATCH_SIZE):
        batch_emb = probe_emb[start:start + BATCH_SIZE]
        batch_ids = probe_ids[start:start + BATCH_SIZE]
        sims = batch_emb @ gallery_emb.T

        for row_idx, identity in enumerate(batch_ids):
            genuine_col = id_to_col.get(identity)
            if genuine_col is None:
                continue
            genuine_scores.append(sims[row_idx, genuine_col])

            other_cols = [c for c in range(len(gallery_ids)) if c != genuine_col]
            n_sample = min(n_impostor_samples, len(other_cols))
            sampled_cols = rng.choice(other_cols, size=n_sample, replace=False)
            impostor_scores.extend(sims[row_idx, sampled_cols].tolist())

    return np.array(genuine_scores), np.array(impostor_scores)


def roc_auc_and_tar(genuine_scores, impostor_scores, far_targets=(0.01, 0.05, 0.1)):
    labels = np.concatenate([np.ones_like(genuine_scores), np.zeros_like(impostor_scores)])
    scores = np.concatenate([genuine_scores, impostor_scores])

    fpr, tpr, _ = roc_curve(labels, scores)
    roc_auc = sklearn_auc(fpr, tpr)

    tar_at_far = {}
    for target in far_targets:
        idx = np.searchsorted(fpr, target, side="left")
        idx = min(idx, len(tpr) - 1)
        tar_at_far[target] = float(tpr[idx])

    return float(roc_auc), tar_at_far
