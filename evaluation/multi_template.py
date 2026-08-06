"""Builds the ARGUS template-system gallery (design.md): unmasked + synthetic-mask templates per identity."""

import numpy as np

import eval_sets


# adds one embedding per (identity, mask_type) as an extra gallery template, alongside the unmasked photo
def pick_multi_template_gallery(data, dataset_name, unmasked_label):
    unmasked_ids, unmasked_emb, unmasked_paths = eval_sets.pick_gallery(data, dataset_name, unmasked_label)

    mask = eval_sets.dataset_mask(data, dataset_name) & (data["is_masked"] == 1)
    identities = data["identity"][mask]
    paths = data["path"][mask]
    mask_types = data["mask_type"][mask]
    embeddings = data["embedding"][mask]

    # one template per (identity, mask_type), lowest path wins - same tie-break pick_gallery uses
    template_rows = {}
    for identity, path, mtype, embedding in zip(identities, paths, mask_types, embeddings):
        key = (identity, mtype)
        if key not in template_rows or path < template_rows[key][0]:
            template_rows[key] = (path, embedding)

    template_ids = [identity for identity, _ in template_rows.keys()]
    template_paths = [v[0] for v in template_rows.values()]
    template_emb = [v[1] for v in template_rows.values()]

    gallery_ids = np.concatenate([unmasked_ids, np.array(template_ids)])
    gallery_emb = np.concatenate([unmasked_emb, np.stack(template_emb)]) if template_emb else unmasked_emb
    excluded_paths = np.concatenate([unmasked_paths, np.array(template_paths)])
    return gallery_ids, gallery_emb, excluded_paths


# masked probes with whichever embeddings became gallery templates removed, so no probe was also trained on
def held_out_masked_probes(data, dataset_name, excluded_paths):
    ids, emb, mask_types, source_tools = eval_sets.masked_probes(data, dataset_name)
    all_ids, all_emb, all_mask_types, all_source_tools, all_paths = _masked_rows_with_paths(data, dataset_name)
    keep = ~np.isin(all_paths, excluded_paths)
    return all_ids[keep], all_emb[keep], all_mask_types[keep], all_source_tools[keep]


# same filter as eval_sets.masked_probes but keeps the path column too, needed to exclude templates
def _masked_rows_with_paths(data, dataset_name):
    mask = eval_sets.dataset_mask(data, dataset_name) & (data["is_masked"] == 1)
    return (data["identity"][mask], data["embedding"][mask], data["mask_type"][mask],
            data["source_tool"][mask], data["path"][mask])


# builds the full ARGUS template-system gallery/probe split for one dataset
def build_template_sets(data, dataset_name, unmasked_label):
    gallery_ids, gallery_emb, excluded_paths = pick_multi_template_gallery(data, dataset_name, unmasked_label)
    probe_ids, probe_emb, mask_types, source_tools = held_out_masked_probes(data, dataset_name, excluded_paths)
    return {
        "gallery_ids": gallery_ids, "gallery_emb": gallery_emb,
        "masked_probe_ids": probe_ids, "masked_probe_emb": probe_emb,
        "masked_probe_types": mask_types, "masked_probe_tools": source_tools,
    }
