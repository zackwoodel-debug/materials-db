#!/usr/bin/env python3
"""
scripts/package_ml_dataset.py
=============================
The ML dataset as one self-describing package for ML platforms: Hugging Face (dataset card with configs and splits),
Zenodo (.zenodo.json, for a DOI) and any Croissant-aware tool (croissant.json, MLCommons Croissant 1.1).

    python3 scripts/package_ml_dataset.py
    -> release/ml-dataset-v<release>/  and  release/ml-dataset-v<release>.zip

Contents (built from the committed ML sets; they must come from the same release):
    materials/{train,validation,test}.parquet   ML_release_feature_matrix + group, split, fold (one row per material)
    spectra/{train,validation,test}.parquet     ML_release_spectra + group, split, fold (one row per optical dataset)
    metadata/*.json                             the generators' metadata (grid, counts, groups, provenance)
    README.md                                   dataset card (Hugging Face YAML header)
    croissant.json, .zenodo.json, CITATION.cff (copied to the repository root), DATA_LICENSE.md, CHANGELOG.md, DATA_DICTIONARY.md (of the SQLite release)
    SHA256SUMS
Nothing is uploaded: publishing to Hugging Face or Zenodo is a separate, deliberate step (commands in NOTES.md).
The package is deterministic: the same inputs give byte-identical files (the zip has fixed timestamps).
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_ROOT = Path(__file__).resolve().parents[1]
DATA = _ROOT / "data"
FEATURES, SPECTRA, SPLITS = DATA / "ML_release_feature_matrix.parquet", DATA / "ML_release_spectra.parquet", DATA / "ML_splits.csv"
METADATA = {"features": DATA / "ML_release_feature_metadata.json", "spectra": DATA / "ML_release_spectra_metadata.json",
            "splits": DATA / "ML_splits_metadata.json"}
SPLIT_NAMES = ("train", "validation", "test")
NAME = "materials-db"
TITLE = "materials-db: optical constants and descriptors of materials, ML edition"
CREATOR = dict(name="Wodel, Zack", given="Zack", family="Wodel")
REPO_URL = "https://github.com/zackwoodel-debug/materials-db"
KEYWORDS = ["refractive index", "optical constants", "extinction coefficient", "materials science", "density",
            "materials informatics", "machine learning", "spectra", "dispersion"]
UPSTREAM = [  # (citation, DOI or URL): DATA_LICENSE.md
    ("M. N. Polyanskiy, Refractiveindex.info database of optical constants, Sci. Data 11, 94 (2024)", "10.1038/s41597-023-02898-2"),
    ("A. Jain et al., The Materials Project, APL Mater. 1, 011002 (2013)", "10.1063/1.4812323"),
    ("S. Kim et al., PubChem 2023 update, Nucleic Acids Res. 51, D1373 (2023)", "10.1093/nar/gkac956"),
    ("S. P. Ong et al., pymatgen, Comput. Mater. Sci. 68, 314 (2013)", "10.1016/j.commatsci.2012.10.028"),
]

SPLIT_COLS = {"group": "Leakage group (identical composition, one product line, or the material itself); never split a group.",
              "split": "train / validation / test, from a hash of the group: stable across releases.",
              "fold": "Grouped cross-validation fold 0-4, from an independent hash of the group."}
MATERIAL_COLS = {
    "material_id": "Permanent material id (never changes or is reused between releases).",
    "meta_key": "Stable text key <family>:<selection key> or <family>:<formula>[@<polymorph>].",
    "meta_name": "Display name.", "meta_formula": "Chemical formula (empty for mixtures and products).",
    "meta_family": "Family table the material comes from.", "meta_material_class": "Material class.",
    "meta_material_kind": "Kind of material (crystal, molecule, polymer, mixture, ...).",
    "meta_primary_dataset": "Source file of the primary optical dataset.", "meta_primary_dataset_label": "Label of the primary optical dataset.",
    "meta_n_optical_datasets": "Number of optical datasets of the material in the release.",
    "meta_primary_wl_min_nm": "Shortest wavelength of the primary dataset (nm).", "meta_primary_wl_max_nm": "Longest wavelength of the primary dataset (nm).",
    "meta_primary_has_negative_k": "The primary dataset contains a negative k (the source's own value).",
    "meta_density_kind": "Where the density comes from (measured literature value, MP DFT, bulk approximation).",
    "meta_density_temperature_c": "Temperature of the density (degC).", "meta_mp_id": "Materials Project entry of the structural descriptors.",
    "target_n_633nm": "TARGET: refractive index n at 633 nm from the primary dataset (NaN outside its range; never extrapolated).",
    "target_k_633nm": "TARGET: extinction coefficient k at 633 nm from the primary dataset (NaN when absent).",
    "target_density_g_cm3": "TARGET: density (g/cm3).",
}
FEATURE_BLOCKS = {"feat_comp_": "Compositional descriptor (formula statistics over element properties).",
                  "feat_frac_": "Element fraction in the formula unit.",
                  "feat_struct_": "Structural descriptor of the Materials Project entry.",
                  "feat_mol_": "Molecular descriptor (RDKit).", "feat_fp_": "Morgan fingerprint bit (radius 2, 512 bits).",
                  "feat_exact_": "Exact mass of the formula unit.", "feat_heavy_": "Heavy-atom count of the formula unit.",
                  "has_": "Whether this descriptor block exists for the material."}
SPECTRA_COLS = {
    "material_id": "Permanent material id (join key to materials).", "key": "Stable material key.", "name": "Material name.",
    "dataset_label": "Dataset label: [variant/phase |] source tag [| axis].", "variant_or_phase": "Variant or phase from the label.",
    "source_tag": "Source (paper) tag.", "axis": "Optical axis or ray (o, e, x, y, z) for anisotropic media.",
    "temperature_c": "Temperature of the dataset (degC), when single-valued.", "is_model_fit": "The dataset is a model fit, not a measurement.",
    "is_primary": "The material's primary dataset (exactly one per material).", "source_file": "refractiveindex.info source file.",
    "wl_min_nm": "Shortest source wavelength (nm).", "wl_max_nm": "Longest source wavelength (nm).", "n_points": "Source points.",
    "n_grid_points": "Grid points with a real n.", "k_grid_points": "Grid points with a real k.",
    "n": "n on the 128-point wavelength grid (metadata/spectra_metadata.json); NaN where n_mask is false.",
    "n_mask": "Where n is real data.", "k": "k on the wavelength grid; NaN where k_mask is false.", "k_mask": "Where k is real data.",
}
CROISSANT_TYPES = {"double": "sc:Float", "float": "sc:Float", "int64": "sc:Integer", "bool": "sc:Boolean", "string": "sc:Text",
                   "large_string": "sc:Text"}
CONTEXT = {
    "@language": "en", "@vocab": "https://schema.org/", "sc": "https://schema.org/", "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/", "dct": "http://purl.org/dc/terms/",
    "citeAs": "cr:citeAs", "column": "cr:column", "conformsTo": "dct:conformsTo", "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"}, "equivalentProperty": "cr:equivalentProperty", "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract", "field": "cr:field", "fileProperty": "cr:fileProperty", "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet", "format": "cr:format", "includes": "cr:includes", "isArray": "cr:isArray", "arrayShape": "cr:arrayShape",
    "isLiveDataset": "cr:isLiveDataset", "jsonPath": "cr:jsonPath", "key": "cr:key", "md5": "cr:md5", "parentField": "cr:parentField",
    "path": "cr:path", "recordSet": "cr:recordSet", "references": "cr:references", "regex": "cr:regex", "repeated": "cr:repeated",
    "replace": "cr:replace", "samplingRate": "cr:samplingRate", "separator": "cr:separator", "source": "cr:source",
    "subField": "cr:subField", "transform": "cr:transform",
}


class PackageError(RuntimeError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def describe(col, table):
    if col in SPLIT_COLS:
        return SPLIT_COLS[col]
    if table == "spectra":
        return SPECTRA_COLS[col]
    if col in MATERIAL_COLS:
        return MATERIAL_COLS[col]
    for prefix, text in FEATURE_BLOCKS.items():
        if col.startswith(prefix):
            return text
    raise PackageError(f"no description for materials column {col!r}: add it to MATERIAL_COLS or FEATURE_BLOCKS")


def load_inputs():
    meta = {k: json.loads(p.read_text()) for k, p in METADATA.items()}
    releases = {k: m["source_release"] for k, m in meta.items()}
    shas = {k: m["source_sqlite_sha256"] for k, m in meta.items()}
    if len(set(releases.values())) != 1 or len(set(shas.values())) != 1:
        raise PackageError(f"the ML sets come from different releases: {releases}; regenerate them")
    splits = pd.read_csv(SPLITS)[["material_id", *SPLIT_COLS]]
    feats = pd.read_parquet(FEATURES).merge(splits, on="material_id", how="left", validate="1:1")
    spec = pd.read_parquet(SPECTRA).merge(splits, on="material_id", how="left", validate="m:1")
    for name, df in (("materials", feats), ("spectra", spec)):
        if df.split.isna().any():
            raise PackageError(f"{name}: rows without a split; regenerate data/ML_splits.csv")
    return feats, spec, meta, releases["features"]


def write_parquet(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df.reset_index(drop=True), preserve_index=False).replace_schema_metadata(None)
    pq.write_table(table, str(path), compression="zstd")


def release_date(version, path=_ROOT / "CHANGELOG.md"):
    m = re.search(rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})", path.read_text(), re.M)
    if not m:
        raise PackageError(f"CHANGELOG.md has no dated entry for {version}")
    return m.group(1)


def croissant(out, version, schemas, meta):
    files, record_sets = [], []
    for table, schema in schemas.items():
        for s in SPLIT_NAMES:
            rel = f"{table}/{s}.parquet"
            files.append({"@type": "cr:FileObject", "@id": rel, "name": rel, "contentUrl": rel, "encodingFormat": "application/x-parquet",
                          "sha256": sha256(out / rel)})
        files.append({"@type": "cr:FileSet", "@id": f"{table}-files", "name": f"{table}-files",
                      "containedIn": [{"@id": f"{table}/{s}.parquet"} for s in SPLIT_NAMES],
                      "encodingFormat": "application/x-parquet", "includes": f"{table}/*.parquet"})
        fields = []
        for f in schema:
            t = f.type
            is_list = pa.types.is_list(t)
            base = str(t.value_type if is_list else t)
            field = {"@type": "cr:Field", "@id": f"{table}/{f.name}", "name": f.name, "description": describe(f.name, table),
                     "dataType": CROISSANT_TYPES[base], "source": {"fileSet": {"@id": f"{table}-files"}, "extract": {"column": f.name}}}
            if is_list:
                field["isArray"] = True
                field["arrayShape"] = str(meta["spectra"]["grid"]["points"])
            fields.append(field)
        record_sets.append({"@type": "cr:RecordSet", "@id": table, "name": table,
                            "description": "One row per material." if table == "materials" else "One row per optical dataset.",
                            "key": [{"@id": f"{table}/material_id"}] if table == "materials" else
                                   [{"@id": f"{table}/material_id"}, {"@id": f"{table}/dataset_label"}],
                            "field": fields})
    return {
        "@context": CONTEXT, "@type": "sc:Dataset", "conformsTo": "http://mlcommons.org/croissant/1.1", "name": NAME,
        "description": f"{TITLE}. Release v{version}: {meta['features']['n_materials']} materials, {meta['spectra']['datasets']} optical "
                       "datasets on a common wavelength grid, leak-free grouped splits.",
        "version": version, "datePublished": release_date(version), "license": "https://creativecommons.org/licenses/by/4.0/", "url": REPO_URL,
        "creator": {"@type": "sc:Person", "name": "Zack Wodel"}, "keywords": KEYWORDS,
        "citeAs": f"Wodel, Z. materials-db v{version} (ML edition). {REPO_URL}",
        "isLiveDataset": False, "distribution": files, "recordSet": record_sets,
    }


def card(version, meta, counts):
    fm, sm, xm = meta["features"], meta["spectra"], meta["splits"]
    configs = "\n".join(f"- config_name: {t}\n  data_files:\n" + "\n".join(f"  - split: {s}\n    path: {t}/{s}.parquet" for s in SPLIT_NAMES)
                        + ("\n  default: true" if t == "materials" else "") for t in ("materials", "spectra"))
    split_rows = "\n".join(f"| {s} | {xm['per_split'][s]['materials']} | {xm['per_split'][s]['groups']} | {counts['spectra'][s]} | "
                           f"{xm['per_split'][s]['with_target_n_633nm']} | {xm['per_split'][s]['with_target_k_633nm']} | "
                           f"{xm['per_split'][s]['with_target_density_g_cm3']} |" for s in SPLIT_NAMES)
    ups = "\n".join(f"- {c}, doi:{d}" for c, d in UPSTREAM)
    return f"""---
license: cc-by-4.0
pretty_name: materials-db (ML edition)
language:
- en
tags:
- materials-science
- optics
- refractive-index
- chemistry
- tabular
task_categories:
- tabular-regression
size_categories:
- n<1K
configs:
{configs}
---

# {TITLE}

Release **v{version}** of [materials-db]({REPO_URL}), packaged for machine learning. Two tables share one set of leak-free splits:

- **materials**: one row per material ({fm['n_materials']}). Targets: `target_n_633nm`, `target_k_633nm`, `target_density_g_cm3`.
  Features: `feat_*` (compositional, element fractions, Materials Project structural, RDKit molecular, 512-bit Morgan fingerprint),
  `has_*` block flags, `meta_*` identity and provenance.
- **spectra**: one row per optical dataset ({sm['datasets']} datasets of {sm['materials']} materials). `n` and `k` on
  {sm['grid']['points']} wavelengths log-spaced from {sm['grid']['min']:g} to {sm['grid']['max']:g} nm, with `n_mask` / `k_mask`
  marking real values. Values are interpolated in log-wavelength inside each dataset's own range only, and masked across source
  gaps wider than {sm['max_gap_ratio']}x; nothing is extrapolated. The grid is in `metadata/spectra_metadata.json`.

```python
from datasets import load_dataset
materials = load_dataset("path/or/hub-id", "materials")   # train / validation / test
spectra = load_dataset("path/or/hub-id", "spectra")
```

## Splits

| split | materials | groups | spectra rows | with n(633 nm) | with k(633 nm) | with density |
|---|---|---|---|---|---|---|
{split_rows}

Splits are assigned to **groups**, never rows: materials with identical composition (polymorphs, isomers, grades, a monomer and
its polymer, H2O/D2O) or one product line share a group, and all spectra of a material follow it. Assignment is a hash of the
group id, so a material keeps its split in later releases. `fold` (0-4) gives grouped 5-fold cross-validation. For
leave-one-family-out, use `meta_family` and handle the groups in `metadata/splits_metadata.json` -> `cross_family_groups`.

## Things to know

- Missing values are NaN, never imputed. Features are unscaled: fit scalers on the training split only.
- n(633 nm) is NaN when the primary dataset does not cover 633 nm; k is NaN when the source gives none. A negative k is the
  source's own value (`meta_primary_has_negative_k`).
- Some rows are model fits of the dielectric function rather than measurements (`is_model_fit` in spectra; measured data is
  preferred for the primary dataset). Densities may be calculated (MP DFT); see `meta_density_kind`.
- Mixtures, glasses, polymers and biological media have no formula; their composition features are NaN.
- Small data: {fm['n_materials']} materials. Report grouped cross-validation, not a single split.

## Provenance and license

Built from the SQLite release v{version} (sha256 `{fm['source_sqlite_sha256']}`, git `{fm['source_release_git_commit']}`).
The full relational database, with every source, citation and dataset, is in the GitHub release. Data license: **CC BY 4.0**
(`DATA_LICENSE.md`). Cite this dataset and the upstream sources:

{ups}

and each dataset's original paper (the `sources` table of the SQLite release).
"""


def zenodo(version, meta):
    return {
        "title": f"{TITLE} (v{version})", "upload_type": "dataset", "version": version,
        "description": f"<p>{meta['features']['n_materials']} materials and {meta['spectra']['datasets']} optical datasets (n, k on a "
                       "common wavelength grid) with compositional, structural and molecular descriptors, targets n and k at 633 nm "
                       "and density, and leak-free grouped splits. Croissant metadata included.</p>",
        "creators": [{"name": CREATOR["name"]}], "license": "cc-by-4.0", "keywords": KEYWORDS, "access_right": "open",
        "related_identifiers": [{"identifier": REPO_URL, "relation": "isSupplementTo", "scheme": "url"}]
                               + [{"identifier": d, "relation": "references", "scheme": "doi"} for _, d in UPSTREAM],
    }


def citation(version):
    lines = ["cff-version: 1.2.0", "message: If you use this dataset, cite it and the upstream sources in DATA_LICENSE.md.",
             "type: dataset", f'title: "{TITLE}"', f'version: "{version}"', "license: CC-BY-4.0", f"repository-code: {REPO_URL}",
             "authors:", f"  - family-names: {CREATOR['family']}", f"    given-names: {CREATOR['given']}", "keywords:"]
    lines += [f'  - "{k}"' for k in KEYWORDS]
    lines += ["references:"]
    for c, d in UPSTREAM:
        lines += ["  - type: article", f'    title: "{c}"', "    authors:", f'      - name: "{c.split(",")[0]}"', f"    doi: {d}"]
    return "\n".join(lines) + "\n"


def build(out_root=_ROOT / "release"):
    feats, spec, meta, version = load_inputs()
    sqlite_release = out_root / f"materials-db-v{version}"
    out = out_root / f"ml-dataset-v{version}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    counts = {"materials": {}, "spectra": {}}
    for s in SPLIT_NAMES:
        write_parquet(feats[feats.split == s], out / "materials" / f"{s}.parquet")
        write_parquet(spec[spec.split == s], out / "spectra" / f"{s}.parquet")
        counts["materials"][s] = int((feats.split == s).sum())
        counts["spectra"][s] = int((spec.split == s).sum())
    (out / "metadata").mkdir()
    for k, p in METADATA.items():
        shutil.copy(p, out / "metadata" / f"{k}_metadata.json")
    schemas = {t: pq.read_schema(out / t / "train.parquet") for t in ("materials", "spectra")}
    (out / "croissant.json").write_text(json.dumps(croissant(out, version, schemas, meta), indent=1) + "\n")
    (out / "README.md").write_text(card(version, meta, counts))
    (out / ".zenodo.json").write_text(json.dumps(zenodo(version, meta), indent=1) + "\n")
    (out / "CITATION.cff").write_text(citation(version))
    shutil.copy(_ROOT / "DATA_LICENSE.md", out / "DATA_LICENSE.md")
    shutil.copy(_ROOT / "CHANGELOG.md", out / "CHANGELOG.md")
    if (sqlite_release / "DATA_DICTIONARY.md").exists():
        shutil.copy(sqlite_release / "DATA_DICTIONARY.md", out / "DATA_DICTIONARY.md")
    files = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.relative_to(out).as_posix()}\n" for p in files))
    zpath = out_root / f"{out.name}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(q for q in out.rglob("*") if q.is_file()):
            info = zipfile.ZipInfo(f"{out.name}/{p.relative_to(out).as_posix()}", date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    return out, zpath, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-root", type=Path, default=_ROOT / "release")
    a = ap.parse_args(argv)
    out, zpath, counts = build(a.out_root)
    (_ROOT / "CITATION.cff").write_text((out / "CITATION.cff").read_text())  # GitHub's "Cite this repository"; committed
    print(f"{out.relative_to(_ROOT) if out.is_relative_to(_ROOT) else out}: materials {counts['materials']}, spectra {counts['spectra']}; "
          f"{zpath.name} ({zpath.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
