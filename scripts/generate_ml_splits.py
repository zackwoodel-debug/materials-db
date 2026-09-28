#!/usr/bin/env python3
"""
scripts/generate_ml_splits.py
=============================
Leak-free, reproducible train / validation / test splits and cross-validation folds for the ML sets (the per-material feature
matrix and the per-dataset spectra), assigned to GROUPS of materials, never to single rows.

    python3 scripts/generate_ml_splits.py
    -> data/ML_splits.csv (one row per material), data/ML_splits_metadata.json

Groups: materials a model cannot tell apart, or that are grades of one product, must fall on the same side of a split:
  * comp:<element fractions>   identical composition (from feat_frac_*): polymorphs (C graphite / diamond), isomers
                               (1- / 2-propanol), grades (PMMA, PDMS mixing ratios), a monomer and its polymer (ethylene / PE),
                               H2O / D2O. Composition features are identical for them, so splitting them apart leaks the target.
  * line:<name>                one product line or one kind of natural material without a formula (PRODUCT_LINES).
  * key:<stable key>           every other material is its own group.
  * composition series (alloys, perovskites; v0.17.0): every member of a series (AlGaAs x = 0.097 ... 0.929) joins the group of
    the series' FIRST end member already in the release (AlGaAs -> GaAs's group), or series:<name> when none is. Existing
    materials never move (the stability promise below), so a second end member (AlAs) may sit in another group: those are
    listed in the metadata (series_end_members_outside_group) for anyone who wants a strict series split. A series member's
    group therefore depends on its anchor being in the release (materials never leave a release in practice).
Rows of the spectra set (axes, phases, temperatures, sources of one material) follow their material_id.

Assignment: from sha256 of the group id, so a material keeps its split in every later release; a new material never moves an
existing one. split: hash mod 10 -> 0-7 train, 8 validation, 9 test (about 80 / 10 / 10 of groups). fold: an independent
hash mod 5 for grouped 5-fold cross-validation. Sizes are therefore near, not exactly, the nominal fractions (reported in the metadata).

For leave-one-family-out, use meta_family, but drop or merge the groups the metadata lists under cross_family_groups
(one composition in two families, e.g. ethylene gas and polyethylene).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
FEATURES = _ROOT / "data" / "ML_release_feature_matrix.parquet"
FEATURE_META = _ROOT / "data" / "ML_release_feature_metadata.json"
OUT_CSV = _ROOT / "data" / "ML_splits.csv"
OUT_METADATA = _ROOT / "data" / "ML_splits_metadata.json"
SPLITS = {**{i: "train" for i in range(8)}, 8: "validation", 9: "test"}
N_FOLDS = 5

# Materials without a formula that are grades of one product or one kind of natural material.
PRODUCT_LINES = {
    "cargille-matching-liquids": ["optical_media:Cargille-BK7", "optical_media:Cargille-06350", "optical_media:Cargille-50350",
                                  "optical_media:Cargille-acrylic", "optical_media:Cargille-acrylic-double"],
    "silk-fibroin": ["liquids:silk-Bm", "liquids:silk-Am", "liquids:silk-Sr", "liquids:silk-Aa"],
    "merck-mlc-9200": ["liquid_crystals:MLC-9200-000", "liquid_crystals:MLC-9200-100"],
    "micro-resist-epoxy": ["polymers:EpoClad", "polymers:EpoCore"],
    "nanoscribe-ip": ["polymers:IP-S", "polymers:IP-Dip"],
}


SERIES_FAMILIES = ("alloys", "perovskites")
GLASS_CATALOG_FAMILY = "glass_catalogs"


def glass_classes(keys):
    """Optical-equivalence classes of catalog glasses (v0.20.0): the same 6-digit glass code (nd, Vd), or listed together on one of
    refractiveindex.info's popular_glass pages (its own cross-maker equivalents: N-BK7 ~ S-BSL7 ~ H-K9L ~ ...). A class that
    contains one of the glasses family's datasheet glasses (N-BK7, B 270, ...) is anchored to that material (it never moves).
    Returns {catalog key: ('anchor', legacy key) | ('class', class id)}."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import yaml
    from glass_catalog_list import RI, glass_code, popular_equivalents
    cat = pd.read_csv(_ROOT / "data" / "glass_catalogs.csv", dtype={"glass_code": str, "glass_code_from_nd": str})
    code = {f"{GLASS_CATALOG_FAMILY}:{k}": (c.split(".")[0] if isinstance(c, str) else None) for k, c in zip(cat.selection_key, cat.glass_code)}
    # a moulding grade also carries the code of its own (post-moulding) nd / Vd: it joins both classes
    code_nd = {f"{GLASS_CATALOG_FAMILY}:{k}": c for k, c in zip(cat.selection_key, cat.glass_code_from_nd) if isinstance(c, str)}
    by_path = {}
    for fam, fname in ((GLASS_CATALOG_FAMILY, "step1_selections_glass_catalogs.json"), ("glasses", "step1_selections_glasses.json")):
        for k, v in json.loads((_ROOT / "data" / fname).read_text()).items():
            for a in v["axes"]:
                by_path[a["data_path"]] = f"{fam}:{k}"
    legacy_code = {}
    for path, key in by_path.items():
        if key.startswith("glasses:"):
            c = glass_code((yaml.safe_load(open(RI / "data" / path)).get("PROPERTIES") or {}))
            if c:
                legacy_code[key] = c
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for k, c in code.items():
        find(k)
        if c:
            union(k, f"code:{c}")
        if k in code_nd:
            union(k, f"code:{code_nd[k]}")
    for k, c in legacy_code.items():
        union(k, f"code:{c}")
    for paths in popular_equivalents().values():
        members = [by_path[p] for p in paths if p in by_path]
        for m in members[1:]:
            union(members[0], m)
    comps = {}
    for x in list(parent):
        comps.setdefault(find(x), []).append(x)
    out = {}
    for members in comps.values():
        legacy = sorted(m for m in members if m.startswith("glasses:"))
        codes = sorted(m[5:] for m in members if m.startswith("code:"))
        cid = ("anchor", legacy[0]) if legacy else ("class", "glass:" + ("+".join(codes) if codes else
                                                                          sorted(m for m in members if m.startswith(GLASS_CATALOG_FAMILY))[0]))
        for m in members:
            if m.startswith(GLASS_CATALOG_FAMILY + ":") and m in keys:
                out[m] = cid
    return out


def series_end_members():
    sys.path.insert(0, str(_ROOT / "scripts"))
    from alloy_material_list import SERIES_END_MEMBERS as a
    from perovskite_material_list import SERIES_END_MEMBERS as p
    return {**a, **p}


class SplitError(RuntimeError):
    pass


def composition_key(row, frac_cols):
    parts = [f"{c[len('feat_frac_'):]}{row[c]:.4f}" for c in frac_cols if pd.notna(row[c]) and row[c] > 0]
    return " ".join(parts) or None


def _hash(text, salt):
    return int(hashlib.sha256(f"{salt}:{text}".encode()).hexdigest(), 16)


def assign(df, strict=True):
    """strict: every PRODUCT_LINES key must be present (a renamed key would silently leave its group)."""
    frac = sorted(c for c in df.columns if c.startswith("feat_frac_"))
    line_of = {k: line for line, keys in PRODUCT_LINES.items() for k in keys}
    unknown = sorted(set(line_of) - set(df.meta_key))
    if unknown and strict:
        raise SplitError(f"PRODUCT_LINES names keys not in the feature matrix: {unknown}")
    rows = []
    base = {}
    for r in df.itertuples(index=False):  # composition / product-line / own-key groups, before series
        ck = composition_key(r._asdict(), frac)
        base[r.meta_key] = (f"line:{line_of[r.meta_key]}" if r.meta_key in line_of else f"comp:{ck}" if ck else f"key:{r.meta_key}")
    ends = series_end_members()
    family_of = dict(zip(df.meta_key, df.meta_family))
    glass = glass_classes(set(df.meta_key)) if (df.meta_family == GLASS_CATALOG_FAMILY).any() else {}

    def final_group(key, seen=()):
        """A series member takes its first present end member's FINAL group: when that end member is itself a series member
        (the 2D perovskites -> MAPbI3 -> series:MAPbX3), follow it through."""
        if family_of.get(key) not in SERIES_FAMILIES:
            return base[key]
        series = key.split(":", 1)[1].split("@")[0]
        if series not in ends:
            raise SplitError(f"{key}: series {series!r} has no SERIES_END_MEMBERS entry")
        if key in seen:
            raise SplitError(f"series anchors form a cycle: {seen + (key,)}")
        anchor = next((k for k in ends[series] if k in base), None)
        return final_group(anchor, seen + (key,)) if anchor else f"series:{series}"

    for r in df.itertuples(index=False):
        ck = composition_key(r._asdict(), frac)
        if r.meta_key in line_of:
            if ck:
                raise SplitError(f"{r.meta_key} has a composition; it belongs to a comp: group, not a product line")
            gid = f"line:{line_of[r.meta_key]}"
        else:
            gid = f"comp:{ck}" if ck else f"key:{r.meta_key}"
        if r.meta_family in SERIES_FAMILIES:
            gid = final_group(r.meta_key)
        elif r.meta_family == GLASS_CATALOG_FAMILY:
            kind, ref = glass[r.meta_key]
            gid = base[ref] if kind == "anchor" and ref in base else (f"key:{ref}" if kind == "anchor" else ref)
        rows.append(dict(material_id=r.material_id, meta_key=r.meta_key, meta_name=r.meta_name, meta_family=r.meta_family, group=gid,
                         split=SPLITS[_hash(gid, "split") % 10], fold=_hash(gid, "fold") % N_FOLDS))
    return pd.DataFrame(rows).sort_values("material_id").reset_index(drop=True)


def summary(splits, features):
    targets = [c for c in features.columns if c.startswith("target_")]
    f = features.set_index("material_id")[targets]
    per_split = {}
    for s in ("train", "validation", "test"):
        ids = splits.loc[splits.split == s, "material_id"]
        per_split[s] = dict(materials=len(ids), groups=int(splits.loc[splits.split == s, "group"].nunique()),
                            **{f"with_{t}": int(f.loc[ids, t].notna().sum()) for t in targets})
    fams = splits.groupby("group").meta_family.agg(lambda x: sorted(set(x)))
    ends = series_end_members()
    group_of = dict(zip(splits.meta_key, splits.group))
    series_groups, outside = {}, []
    for k, g in group_of.items():
        if k.split(":", 1)[0] in SERIES_FAMILIES:
            s = k.split(":", 1)[1].split("@")[0]
            series_groups[s] = g
    for s, g in sorted(series_groups.items()):
        outside += [dict(series=s, end_member=e, group=group_of[e]) for e in ends.get(s, []) if e in group_of and group_of[e] != g]
    multi = splits.groupby("group").size()
    return dict(
        groups=int(splits.group.nunique()), multi_material_groups=int((multi > 1).sum()),
        materials_in_multi_material_groups=int(multi[multi > 1].sum()), per_split=per_split,
        per_fold={int(k): int(v) for k, v in splits.fold.value_counts().sort_index().items()},
        cross_family_groups={g: v for g, v in fams.items() if len(v) > 1},
        series_groups=series_groups, series_end_members_outside_group=outside,
        group_members={g: sorted(splits.loc[splits.group == g, "meta_key"]) for g in multi[multi > 1].index})


def main(argv=None):
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args(argv)
    features = pd.read_parquet(FEATURES)
    splits = assign(features)
    splits.to_csv(OUT_CSV, index=False)
    fmeta = json.loads(FEATURE_META.read_text())
    meta = dict(source_release=fmeta["source_release"], source_sqlite_sha256=fmeta["source_sqlite_sha256"],
                assignment="sha256 of the group id: split = hash('split:'+group) mod 10 (0-7 train, 8 validation, 9 test); "
                           f"fold = hash('fold:'+group) mod {N_FOLDS}",
                product_lines=PRODUCT_LINES, **summary(splits, features),
                notes=["Join on material_id: ML_release_feature_matrix.parquet and ML_release_spectra.parquet.",
                       "Never split rows of one group; use 'group' for any other grouped scheme (e.g. sklearn GroupKFold).",
                       "Fit scalers, imputers and feature selection on the training split only."])
    OUT_METADATA.write_text(json.dumps(meta, indent=1) + "\n")
    ps = meta["per_split"]
    print(f"{len(splits)} materials in {meta['groups']} groups ({meta['multi_material_groups']} with >1 material); "
          f"train/validation/test = {ps['train']['materials']}/{ps['validation']['materials']}/{ps['test']['materials']} materials; "
          f"{len(meta['cross_family_groups'])} cross-family groups -> {OUT_CSV.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
