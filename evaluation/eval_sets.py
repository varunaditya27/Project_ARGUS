"""Splits embeddings.npz into gallery (one unmasked photo per identity), unmasked probes, and masked probes."""

import numpy as np

LFW_UNMASKED_TYPE = "unmasked"
MFR2_UNMASKED_TYPE = "no-mask"


# loads the npz file produced by build_embeddings.py
def load(npz_path):
    return np.load(npz_path)


# boolean mask for rows belonging to one dataset (lfw_subset or mfr2)
def dataset_mask(data, dataset_name):
    return data["dataset"] == dataset_name


# picks one unmasked embedding per identity to act as the enrollment photo
def pick_gallery(data, dataset_name, unmasked_label):
    mask = dataset_mask(data, dataset_name) & (data["mask_type"] == unmasked_label)
    identities = data["identity"][mask]
    paths = data["path"][mask]
    embeddings = data["embedding"][mask]

    gallery_rows = {}
    for identity, path, embedding in zip(identities, paths, embeddings):
        if identity not in gallery_rows or path < gallery_rows[identity][0]:
            gallery_rows[identity] = (path, embedding)

    gallery_ids = np.array(list(gallery_rows.keys()))
    gallery_paths = np.array([v[0] for v in gallery_rows.values()])
    if not gallery_rows:
        return gallery_ids, np.empty((0, 512), dtype=np.float32), gallery_paths
    gallery_emb = np.stack([v[1] for v in gallery_rows.values()])
    return gallery_ids, gallery_emb, gallery_paths


# the remaining unmasked photos per identity, excluding whichever one became the gallery photo
def unmasked_probes(data, dataset_name, unmasked_label, gallery_paths):
    mask = dataset_mask(data, dataset_name) & (data["mask_type"] == unmasked_label)
    mask &= ~np.isin(data["path"], gallery_paths)
    return data["identity"][mask], data["embedding"][mask]


# every masked embedding for a dataset, with its mask type and which tool generated it
def masked_probes(data, dataset_name):
    mask = dataset_mask(data, dataset_name) & (data["is_masked"] == 1)
    return data["identity"][mask], data["embedding"][mask], data["mask_type"][mask], data["source_tool"][mask]


# builds the full gallery/unmasked-probe/masked-probe split for LFW_subset
def build_lfw_sets(data):
    gallery_ids, gallery_emb, gallery_paths = pick_gallery(data, "lfw_subset", LFW_UNMASKED_TYPE)
    probe_ids_unmasked, probe_emb_unmasked = unmasked_probes(data, "lfw_subset", LFW_UNMASKED_TYPE, gallery_paths)
    probe_ids_masked, probe_emb_masked, mask_types, source_tools = masked_probes(data, "lfw_subset")
    return {
        "gallery_ids": gallery_ids, "gallery_emb": gallery_emb,
        "unmasked_probe_ids": probe_ids_unmasked, "unmasked_probe_emb": probe_emb_unmasked,
        "masked_probe_ids": probe_ids_masked, "masked_probe_emb": probe_emb_masked,
        "masked_probe_types": mask_types, "masked_probe_tools": source_tools,
    }


# builds the full gallery/unmasked-probe/masked-probe split for MFR2
def build_mfr2_sets(data):
    gallery_ids, gallery_emb, gallery_paths = pick_gallery(data, "mfr2", MFR2_UNMASKED_TYPE)
    probe_ids_unmasked, probe_emb_unmasked = unmasked_probes(data, "mfr2", MFR2_UNMASKED_TYPE, gallery_paths)
    probe_ids_masked, probe_emb_masked, mask_types, source_tools = masked_probes(data, "mfr2")
    return {
        "gallery_ids": gallery_ids, "gallery_emb": gallery_emb,
        "unmasked_probe_ids": probe_ids_unmasked, "unmasked_probe_emb": probe_emb_unmasked,
        "masked_probe_ids": probe_ids_masked, "masked_probe_emb": probe_emb_masked,
        "masked_probe_types": mask_types, "masked_probe_tools": source_tools,
    }
