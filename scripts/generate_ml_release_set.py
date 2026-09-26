#!/usr/bin/env python3
"""
scripts/generate_ml_release_set.py
==================================
ML-ready table of every material in a release database (one row per material), read from the release SQLite and its
family tables. The legacy set (scripts/generate_ml_training_set.py -> data/ML_feature_matrix.parquet) stays the frozen
23-material benchmark of data/materials_normalized.db; this one covers the canonical release.

    python3 scripts/generate_ml_release_set.py [--release release/materials-db-v0.2.1]
    -> data/ML_release_feature_matrix.parquet, data/ML_release_feature_metadata.json

Columns
  meta_*     identity and provenance: name, formula, family, class, primary optical dataset, density kind
  target_*   n and k at 633 nm and density. Nothing that is a target is also a feature.
  feat_*     compositional (formula statistics + element fractions), structural (Materials Project entry) and molecular
             (RDKit columns + 512-bit Morgan fingerprint) descriptors from chemical_descriptors
  has_*      whether a descriptor block exists for the material (its absence is explained in descriptor_json)

Rules
  * Primary optical dataset = the page the release's family table names (ri_page_primary), resolved to its exact data_path
    through the selection the family was built from (data/step1_selections*.json, or the batch-2 / pure-element material
    lists) and matched to optical_dispersion.raw_record_table exactly. A material in two
    family tables uses the first, as the release does. The family tables' n_633 cross-checks the choice.
  * n, k at 633 nm are interpolated inside the primary dataset's own wavelength range only; outside it they are NaN.
    k is NaN when the dataset gives no k. Nothing is extrapolated, imputed or zero-filled. A negative k is the source's own
    value (unphysical for a passive material) and is kept; meta_primary_has_negative_k marks the dataset.
  * The Morgan fingerprint is the release's 2048-bit one folded to 512 bits (bit i = OR of bits i + 512j), identical to
    generating it at 512 bits; it exists only where the release computed one (molecules and polymer repeat units).
  * Features are NOT scaled: fit any scaler on your training split only.
  * Materials Project's DFT density is left out of the features (it is the density target of the MP_DFT rows). Cell
    volume and composition remain, so an MP_DFT density target is derivable from them: filter on meta_density_kind if
    that matters for your model.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
OUT_PARQUET = _ROOT / "data" / "ML_release_feature_matrix.parquet"
OUT_METADATA = _ROOT / "data" / "ML_release_feature_metadata.json"

REF_WL_NM = 633.0
FP_BITS = 512
# release family order (build_release.py): a material in two tables belongs to the first
FAMILY_ORDER = ["oxides_50", "batch2_31", "batch3b_4", "pure_elements_50", "nitrides", "polymers", "inorganic3", "halides",
                "chalcogenides", "liquids", "semiconductors", "inorganic4", "glasses", "optical_media"]
COMP_PROPS = ["atomic_mass", "atomic_number", "atomic_radius", "electronegativity_pauling", "group", "mendeleev_number", "period"]
COMP_STATS = ["min", "max", "mean", "range", "mean_abs_deviation"]
COMP_SCALARS = ["n_elements", "atoms_per_formula_unit", "stoichiometry_l2_norm", "stoichiometry_l3_norm"]
STRUCT_NUMERIC = ["space_group_number", "lattice_a_angstrom", "lattice_b_angstrom", "lattice_c_angstrom", "lattice_alpha_deg",
                  "lattice_beta_deg", "lattice_gamma_deg", "conventional_cell_volume_angstrom3", "primitive_cell_volume_angstrom3",
                  "conventional_cell_sites", "primitive_cell_sites", "formula_units_per_conventional_cell",
                  "volume_per_atom_angstrom3", "formation_energy_ev_per_atom", "energy_above_hull_ev_per_atom", "band_gap_ev"]
STRUCT_BOOL = ["band_gap_is_direct", "is_metal", "is_magnetic"]
CRYSTAL_SYSTEMS = ["Cubic", "Hexagonal", "Monoclinic", "Orthorhombic", "Tetragonal", "Triclinic", "Trigonal"]
MOLECULAR_COLS = ["tpsa", "logp", "rotatable_bonds", "hbond_donors", "hbond_acceptors", "aromatic_rings"]
FORMULA_COLS = ["exact_mass", "heavy_atom_count"]  # defined for any formula unit, molecular or not


class MLSetError(RuntimeError):
    pass


def latest_release():
    dirs = sorted((d for d in (_ROOT / "release").glob("materials-db-v*") if d.is_dir()),
                  key=lambda d: tuple(int(x) for x in d.name.split("-v")[1].split(".")))
    if not dirs:
        raise MLSetError("no release/materials-db-v*/ folder: build one with scripts/build_release.py")
    return dirs[-1]


def _selection_axes():
    """family -> {material name: [(page, data_path), ...]}, from the inputs each family was built from."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    from fluoride_nitride_sulfide_material_list import MATERIALS_31
    from pure_element_material_list import MATERIALS_PURE_ELEMENTS

    def from_json(fn):
        return {v["name"]: [(a["page"], a["data_path"]) for a in v["axes"]] for v in json.loads((_ROOT / "data" / fn).read_text()).values()
                if v.get("axes")}
    from_list = lambda ms: {m["name"]: [(a["page"], a["data_path"]) for a in m["ri_axes"]] for m in ms if m.get("ri_axes")}
    elements = from_list(MATERIALS_PURE_ELEMENTS)
    return {
        "oxides_50": from_json("step1_selections.json"),
        "batch2_31": from_list(MATERIALS_31),
        "batch3b_4": elements, "pure_elements_50": elements,
        **{fam: from_json(f"step1_selections_{fam}.json")
           for fam in ["nitrides", "polymers", "inorganic3", "halides", "chalcogenides", "liquids", "semiconductors", "inorganic4",
                       "glasses", "optical_media"]},
    }


def release_families(release_dir):
    """FAMILY_ORDER restricted to the families this release has (an older release predates later families)."""
    return [f for f in FAMILY_ORDER if (Path(release_dir) / "family_tables" / f"{f}.csv").exists()]


def primary_pages(release_dir):
    """material name -> (family, primary data_path). The primary PAGE is the one the release's own family table names
    (ri_page_primary), so the ML set follows the release it is built from even after a selection rule changes; the selection
    inputs resolve that page to its exact data_path (page names and file names differ, e.g. "Walling-\u03b1" / Walling-alpha.yml).
    Polymers have no ri_page_primary column: their first selected axis. A material in two family tables belongs to the first."""
    sel = _selection_axes()
    out = {}
    for fam in release_families(release_dir):
        table = pd.read_csv(release_dir / "family_tables" / f"{fam}.csv")
        for _, r in table.iterrows():
            name = r["name"]
            if name in out:
                continue
            axes = sel[fam].get(name) or []
            page = r.get("ri_page_primary")
            hit = [path for pg, path in axes if pg == page] if pd.notna(page) else [path for _, path in axes[:1]]
            out[name] = (fam, hit[0] if hit else None)
    return out


def n_k_at(rows, wl):
    rows = rows.sort_values("wavelength_nm")
    x = rows["wavelength_nm"].to_numpy(float)
    if not (x[0] <= wl <= x[-1]):
        return np.nan, np.nan
    n = rows["n"].to_numpy(float)
    k = rows["k"].to_numpy(float)
    n_ok, k_ok = ~np.isnan(n), ~np.isnan(k)
    n_val = float(np.interp(wl, x[n_ok], n[n_ok])) if n_ok.sum() >= 2 and x[n_ok][0] <= wl <= x[n_ok][-1] else np.nan
    k_val = float(np.interp(wl, x[k_ok], k[k_ok])) if k_ok.sum() >= 2 and x[k_ok][0] <= wl <= x[k_ok][-1] else np.nan
    return n_val, k_val


def fold(bits, size=FP_BITS):
    a = np.frombuffer(bits.encode(), dtype=np.uint8) - ord("0")
    return a.reshape(-1, size).max(axis=0).astype(float)


def build(release_dir):
    release_dir = Path(release_dir)
    db = next(release_dir.glob("materials-db-v*.sqlite"))
    con = sqlite3.connect(str(db))
    mats = pd.read_sql("SELECT material_id, name, formula FROM materials ORDER BY material_id", con)
    opt = pd.read_sql("SELECT material_id, wavelength_nm, n, k, dataset_label, raw_record_table FROM optical_dispersion", con)
    dens = pd.read_sql("SELECT material_id, density_g_cm3, temperature_c, dataset_label FROM physical_properties "
                       "WHERE density_g_cm3 IS NOT NULL", con)
    desc = pd.read_sql("SELECT * FROM chemical_descriptors", con).set_index("material_id")
    con.close()

    primaries = primary_pages(release_dir)
    missing = set(mats["name"]) - set(primaries)
    if missing:
        raise MLSetError(f"materials in no family table: {sorted(missing)[:5]}")
    if dens["material_id"].duplicated().any():
        raise MLSetError("a material has more than one density row; pick rule needed")
    dens = dens.set_index("material_id")
    opt_by = dict(tuple(opt.groupby("material_id")))

    records, fps = [], []
    for _, m in mats.iterrows():
        mid, name = int(m["material_id"]), m["name"]
        fam, key = primaries[name]
        rows = opt_by.get(mid)
        if rows is None or key is None:
            raise MLSetError(f"{name}: no optical rows or no primary dataset")
        tables = rows["raw_record_table"].unique()
        hit = [t for t in tables if t == key]
        if len(hit) != 1:
            raise MLSetError(f"{name}: primary {key!r} matches {len(hit)} datasets of {list(tables)}")
        prim = rows[rows["raw_record_table"] == hit[0]]
        n633, k633 = n_k_at(prim, REF_WL_NM)

        dj = json.loads(desc.at[mid, "descriptor_json"])
        comp, struct, mol = dj["compositional"], dj["structural"], dj["molecular"]
        rec = dict(material_id=mid, meta_name=name, meta_formula=m["formula"], meta_family=fam,
                   meta_material_class=dj.get("material_class"), meta_material_kind=dj.get("material_kind"),
                   meta_primary_dataset=hit[0], meta_primary_dataset_label=prim["dataset_label"].iloc[0],
                   meta_n_optical_datasets=len(tables),
                   meta_primary_wl_min_nm=float(prim["wavelength_nm"].min()),
                   meta_primary_wl_max_nm=float(prim["wavelength_nm"].max()),
                   meta_primary_has_negative_k=bool((prim["k"] < 0).any()),
                   target_n_633nm=n633, target_k_633nm=k633)
        if mid in dens.index:
            d = dens.loc[mid]
            rec.update(target_density_g_cm3=float(d["density_g_cm3"]),
                       meta_density_kind=d["dataset_label"].split("density_", 1)[1],
                       meta_density_temperature_c=float(d["temperature_c"]) if pd.notna(d["temperature_c"]) else np.nan)
        else:
            rec.update(target_density_g_cm3=np.nan, meta_density_kind=None, meta_density_temperature_c=np.nan)

        rec["has_composition"] = "element_fractions" in comp
        if rec["has_composition"]:
            for c in COMP_SCALARS:
                rec[f"feat_comp_{c}"] = float(comp[c])
            for p in COMP_PROPS:
                for s in COMP_STATS:
                    rec[f"feat_comp_{p}_{s}"] = float(comp[p][s])
            for el, frac in comp["element_fractions"].items():
                rec[f"feat_frac_{el}"] = float(frac)

        rec["has_structure"] = "mp_id" in struct
        rec["meta_mp_id"] = struct.get("mp_id")
        if rec["has_structure"]:
            rec["feat_struct_is_reference_only"] = float(not struct["applies_to"].startswith("the material"))
            for c in STRUCT_NUMERIC:
                rec[f"feat_struct_{c}"] = float(struct[c]) if struct.get(c) is not None else np.nan
            for c in STRUCT_BOOL:
                rec[f"feat_struct_{c}"] = float(struct[c]) if struct.get(c) is not None else np.nan
            for cs in CRYSTAL_SYSTEMS:
                rec[f"feat_struct_system_{cs.lower()}"] = float(struct["crystal_system"] == cs)

        for c in FORMULA_COLS:
            v = desc.at[mid, c]
            rec[f"feat_{c}"] = float(v) if pd.notna(v) else np.nan
        fp = desc.at[mid, "morgan_fp"]
        rec["has_molecular"] = isinstance(fp, str)
        for c in MOLECULAR_COLS:
            v = desc.at[mid, c]
            rec[f"feat_mol_{c}"] = float(v) if pd.notna(v) else np.nan
        records.append(rec)
        fps.append(fold(fp) if isinstance(fp, str) else np.full(FP_BITS, np.nan))

    df = pd.DataFrame(records)
    frac_cols = sorted(c for c in df.columns if c.startswith("feat_frac_"))
    df.loc[df["has_composition"], frac_cols] = df.loc[df["has_composition"], frac_cols].fillna(0.0)  # absent element = 0
    fp_df = pd.DataFrame(np.vstack(fps), columns=[f"feat_fp_{i:03d}" for i in range(FP_BITS)])
    df = pd.concat([df, fp_df], axis=1)

    order = ([c for c in df.columns if c == "material_id" or c.startswith("meta_") or c.startswith("has_")]
             + [c for c in df.columns if c.startswith("target_")]
             + [c for c in df.columns if c.startswith("feat_") and not c.startswith(("feat_frac_", "feat_fp_"))]
             + frac_cols + list(fp_df.columns))
    df = df[order]
    df[["has_composition", "has_structure", "has_molecular"]] = df[["has_composition", "has_structure", "has_molecular"]].astype(bool)
    return df, db


def check(df, release_dir):
    """Cross-check the 633 nm targets against the family tables' own n_633 (computed by the builders from the same
    primary dataset, exactly for formula pages). Returns the worst relative deviation; stops on a real disagreement."""
    worst = 0.0
    seen = set()
    for fam in release_families(release_dir):
        t = pd.read_csv(Path(release_dir) / "family_tables" / f"{fam}.csv")
        if "n_633" not in t:
            continue
        for _, r in t.iterrows():
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            ours = df.loc[df["meta_name"] == r["name"], "target_n_633nm"].iloc[0]
            if pd.isna(r["n_633"]) or pd.isna(ours):
                if pd.isna(r["n_633"]) != pd.isna(ours):
                    raise MLSetError(f"{r['name']}: n_633 present in only one of family table ({r['n_633']}) / ML set ({ours})")
                continue
            dev = abs(ours - r["n_633"]) / r["n_633"]
            if dev > 0.01:
                raise MLSetError(f"{r['name']}: ML n_633 {ours} vs family table {r['n_633']}")
            worst = max(worst, dev)
    return worst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--release", type=Path, default=None, help="release folder (default: newest release/materials-db-v*)")
    a = ap.parse_args(argv)
    release_dir = a.release or latest_release()
    df, db = build(release_dir)
    worst = check(df, release_dir)
    df.to_parquet(OUT_PARQUET, index=False)

    manifest = json.loads((Path(release_dir) / "MANIFEST.json").read_text())
    cols = lambda p: [c for c in df.columns if c.startswith(p)]
    feat = [c for c in cols("feat_") if not c.startswith(("feat_frac_", "feat_fp_"))]
    meta = dict(
        source_release=manifest["version"], source_release_git_commit=manifest["git_commit"],
        source_sqlite=db.name, source_sqlite_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
        n_materials=len(df), optical_ref_wl_nm=REF_WL_NM, scaled=False,
        target_columns=cols("target_"),
        target_present={c: int(df[c].notna().sum()) for c in cols("target_")},
        feature_columns=feat, element_fraction_columns=cols("feat_frac_"), fp_columns=cols("feat_fp_"),
        fp_bits=FP_BITS, fp_radius=2, fp_note="release 2048-bit Morgan fingerprint folded to 512 (identical to fpSize=512)",
        block_present={c: int(df[c].sum()) for c in ["has_composition", "has_structure", "has_molecular"]},
        per_family=df["meta_family"].value_counts().to_dict(),
        n633_max_rel_dev_vs_family_tables=worst,
        notes=["Primary optical dataset per material; n,k interpolated inside its range only, never extrapolated.",
               "Missing values are NaN, never imputed; has_* flags say which descriptor blocks exist.",
               "Unscaled: fit scalers on the training split only.",
               "A negative target_k_633nm is the source dataset's own value (meta_primary_has_negative_k); drop or clip "
               "it deliberately if your model needs k >= 0.",
               "MP DFT density is excluded from features; MP_DFT density targets are still derivable from cell volume "
               "and composition (see meta_density_kind)."],
    )
    OUT_METADATA.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{len(df)} materials, {len(feat)} descriptor features + {len(cols('feat_frac_'))} element fractions + {FP_BITS} "
          f"fingerprint bits; targets present {meta['target_present']}; n_633 max deviation vs family tables {worst:.2e}")
    print(f"-> {OUT_PARQUET.relative_to(_ROOT)}, {OUT_METADATA.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MLSetError as e:
        sys.exit(f"STOPPED: {e}")
