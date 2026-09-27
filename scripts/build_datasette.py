#!/usr/bin/env python3
"""
scripts/build_datasette.py
==========================
A browsable website of a release with Datasette (https://datasette.io): every table and column described from the release's
data dictionary, a one-row-per-material index to filter and facet, and saved queries for common questions.

    python3 scripts/build_datasette.py [--release release/materials-db-vX.Y.Z]
    -> release/browse-vX.Y.Z/  materials-db.sqlite (link to the release file, unchanged), families.db, metadata.json
    pip install datasette      # 0.65
    datasette serve -i release/browse-vX.Y.Z/materials-db.sqlite -i release/browse-vX.Y.Z/families.db \\
        --metadata release/browse-vX.Y.Z/metadata.json --setting sql_time_limit_ms 5000      # (printed by this script)

Databases
  materials-db  the release SQLite itself, served immutable (-i: read-only, never modified).
  families      built here: material_index (one row per material: key, family, class, formula, n/k at 633 nm from the primary
                dataset, density, primary dataset, number of datasets, the family table's flags) and each release family table
                as it is published. Values come from the release. n/k at 633 nm are the family table's published values (a
                formula page evaluated exactly at 633 nm); only polymers, whose table has no n_633, are interpolated from the
                primary dataset's stored points (materials_db.access). n_633_origin says which.
Publishing the site (datasette publish cloudrun / vercel / fly) is a separate, deliberate step; nothing is uploaded here.
"""
import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
from materials_db.access import AccessError, ReleaseDB  # noqa: E402

DB_NAME = "materials-db"
REPO_URL = "https://github.com/zackwoodel-debug/materials-db"

CANNED = {
    DB_NAME: {
        "points_near_wavelength": dict(
            title="Source points near a wavelength",
            description="Every dataset's own points within 2% of a wavelength (nm) for materials whose name contains the text. "
                        "Source points, not interpolated. Compare datasets only with equal variant/phase, axis and temperature.",
            sql="SELECT m.material_id, m.name, o.dataset_label, o.wavelength_nm, o.n, o.k, o.temperature_c, s.title AS source, s.doi "
                "FROM optical_dispersion o JOIN materials m USING (material_id) LEFT JOIN sources s USING (source_id) "
                "WHERE m.name LIKE '%' || :material || '%' AND o.wavelength_nm BETWEEN :wavelength_nm * 0.98 AND :wavelength_nm * 1.02 "
                "ORDER BY m.name, o.dataset_label, abs(o.wavelength_nm - :wavelength_nm)"),
        "datasets_of_material": dict(
            title="Optical datasets of a material",
            description="One row per optical dataset: range, points, k present, temperature and source paper.",
            sql="SELECT m.material_id, m.name, o.dataset_label, MIN(o.wavelength_nm) AS wl_min_nm, MAX(o.wavelength_nm) AS wl_max_nm, "
                "COUNT(*) AS points, SUM(o.k IS NOT NULL) AS points_with_k, MIN(o.temperature_c) AS t_min_c, MAX(o.temperature_c) AS t_max_c, "
                "o.raw_record_table AS source_file, s.title AS source, s.doi FROM optical_dispersion o JOIN materials m USING (material_id) "
                "LEFT JOIN sources s USING (source_id) WHERE m.name LIKE '%' || :material || '%' "
                "GROUP BY m.material_id, o.dataset_label ORDER BY m.name, o.dataset_label"),
        "dataset_disagreements": dict(
            title="Datasets that disagree",
            description="Like-for-like comparisons classified warning or suspicious (same phase, axis and temperature, over the overlap).",
            sql="SELECT m.name, v.property_name, v.dataset_a, v.dataset_b, v.pearson_r, v.rmse, v.mean_relative_error, v.classification, "
                "v.notes FROM dataset_validation v JOIN materials m USING (material_id) WHERE v.classification != 'excellent' "
                "ORDER BY v.classification DESC, v.mean_relative_error DESC"),
        "sources_of_material": dict(
            title="Sources cited for a material",
            description="Every source behind a material's optical and physical data, with DOI.",
            sql="SELECT DISTINCT s.source_id, s.title, s.authors, s.year, s.doi, s.url FROM sources s WHERE s.source_id IN ("
                "SELECT source_id FROM optical_dispersion o JOIN materials m USING (material_id) WHERE m.name LIKE '%' || :material || '%' "
                "UNION SELECT source_id FROM physical_properties p JOIN materials m USING (material_id) WHERE m.name LIKE '%' || :material || '%') "
                "ORDER BY s.year"),
    },
    "families": {
        "index_range": dict(
            title="Materials by refractive index at 633 nm",
            description="Materials whose primary dataset gives n(633 nm) between two values.",
            sql="SELECT material_id, key, name, family, material_class, n_633, k_633, density_g_cm3, primary_dataset FROM material_index "
                "WHERE n_633 BETWEEN CAST(:n_min AS REAL) AND CAST(:n_max AS REAL) ORDER BY n_633"),
    },
}

INDEX_COLUMNS = {
    "material_id": "Permanent material id (same as in materials-db).",
    "key": "Stable text key <family>:<selection key> or <family>:<formula>[@<polymorph>].",
    "name": "Display name.", "formula": "Chemical formula; empty for products and mixtures.",
    "family": "Family table the material comes from.", "material_class": "Material class (from the family table).",
    "n_633": "Refractive index n at 633 nm of the primary dataset, as the release's family table publishes it (a dispersion formula "
             "evaluated exactly at 633 nm); empty if the dataset does not cover 633 nm. See n_633_origin.",
    "k_633": "Extinction coefficient k at 633 nm of the primary dataset (empty when the source gives no k).",
    "n_633_origin": "'family table' (published value) or 'interpolated from the primary dataset's points' (polymers, whose "
                    "family table has no n_633 column).",
    "density_g_cm3": "Density (g/cm3) as the family table gives it.", "density_source": "Where the density comes from (literature, MP DFT, ...).",
    "primary_dataset": "Label of the primary optical dataset (measured first, covering 633 nm, then widest range).",
    "primary_is_model_fit": "1 when the primary dataset is a model fit of the dielectric function rather than a measurement.",
    "primary_wl_min_nm": "Shortest wavelength of the primary dataset (nm).", "primary_wl_max_nm": "Longest wavelength of the primary dataset (nm).",
    "optical_datasets": "Number of optical datasets (phases, axes, temperatures and sources are separate datasets).",
    "flags": "The family table's notes: source disagreements, choices made, caveats.",
}


def material_index(db):
    rows = []
    for mid, m in db.materials.iterrows():
        fam = db._family_rows.get(m["name"], {}).get("row")
        prim = None
        try:
            prim = db._dataset(mid)
        except AccessError:
            pass
        info = db._dataset_info(prim) if prim is not None else {}
        get = (lambda c: None if fam is None or c not in fam or (isinstance(fam[c], float) and math.isnan(fam[c])) else fam[c])
        n = k = origin = None
        if fam is not None and "n_633" in fam:  # the release's published value (a formula page is evaluated exactly at 633 nm)
            n, k = get("n_633"), get("k_633")
            origin = "family table" if n is not None else None
        elif prim is not None:  # polymers: the family table has no n_633 column
            v = db._interp(mid, prim.dataset_label, 633.0)
            n, k = v["n"], v["k"]
            origin = "interpolated from the primary dataset's points" if n is not None else None
        rows.append(dict(material_id=int(mid), key=m.key, name=m["name"], formula=m.formula, family=m.family, material_class=m.material_class,
                         n_633=n, k_633=k, n_633_origin=origin, density_g_cm3=get("density_g_cm3"), density_source=get("density_source"),
                         primary_dataset=info.get("dataset_label"), primary_is_model_fit=info.get("is_model_fit"),
                         primary_wl_min_nm=info.get("wl_min_nm"), primary_wl_max_nm=info.get("wl_max_nm"),
                         optical_datasets=int((db.datasets.material_id == mid).sum()), flags=get("flags")))
    return pd.DataFrame(rows)


def build_families_db(db, path):
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    idx = material_index(db)
    cols = ", ".join(f'"{c}"' + (" INTEGER PRIMARY KEY" if c == "material_id" else "") for c in idx.columns)
    con.execute(f"CREATE TABLE material_index ({cols})")
    con.executemany(f"INSERT INTO material_index VALUES ({', '.join('?' * len(idx.columns))})",
                    [tuple(None if (isinstance(v, float) and math.isnan(v)) else v for v in r) for r in idx.itertuples(index=False)])
    tables = {}
    for csv in sorted((db.release_dir / "family_tables").glob("*.csv")):
        t = pd.read_csv(csv)
        t.to_sql(csv.stem, con, index=False)
        tables[csv.stem] = len(t)
    for c in ("family", "material_class", "key", "name"):
        con.execute(f"CREATE INDEX idx_{c} ON material_index ({c})")
    con.commit()
    con.close()
    return idx, tables


def metadata(db, idx, family_tables):
    d = db.schema()
    tables = {}
    for t, spec in d["tables"].items():
        cols = {}
        for c in spec["columns"]:
            text = c.get("description") or ""
            if c.get("unit"):
                text += f" [{c['unit']}]"
            cols[c["name"]] = text
        tables[t] = dict(description=spec.get("description", ""), columns=cols)
    tables["optical_dispersion"]["sort"] = "material_id"
    fam_tables = {"material_index": dict(description="One row per material: identity, family and class, n and k at 633 nm from the "
                                                     "primary dataset, density, primary dataset, and the family table's flags.",
                                         columns=INDEX_COLUMNS, facets=["family", "material_class", "density_source", "primary_is_model_fit"],
                                         sort="name", label_column="name")}
    for name, n in family_tables.items():
        fam_tables[name] = dict(description=("Materials the family selection looked for but could not source (with the reason)."
                                             if name.endswith("_gaps") else "The release's family table, as published: one row per material "
                                             "with its selection, primary page, n/k at 633 nm per axis, density and its citation, and flags."))
    grammar = d.get("label_grammar", {})
    return {
        "title": f"materials-db v{db.version}",
        "description_html": (f"<p>Optical constants n(&lambda;), k(&lambda;), densities, scattering length densities and descriptors of "
                             f"{len(db.materials)} materials ({len(db.datasets)} optical datasets), each value traceable to its source. "
                             "Start with <a href=\"/families/material_index\">the material index</a> or a saved query below.</p>"
                             "<p>Rules: calculated values are labelled calculated; model fits are marked; datasets of different phases, "
                             "axes or temperatures are different quantities (" + grammar.get("comparability", "") + ")</p>"),
        "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source": f"materials-db v{db.version} (refractiveindex.info, Materials Project, PubChem and the papers in the sources table)",
        "source_url": REPO_URL,
        "databases": {
            DB_NAME: dict(description=f"The release database v{db.version}, unchanged (sqlite: {db.sqlite_path.name}).", tables=tables,
                          queries=CANNED[DB_NAME]),
            "families": dict(description="Material index and the release's family tables.", tables=fam_tables, queries=CANNED["families"]),
        },
    }


def serve_command(out):
    return (f'datasette serve -i "{out / (DB_NAME + ".sqlite")}" -i "{out / "families.db"}" --metadata "{out / "metadata.json"}" '
            "--setting sql_time_limit_ms 5000")


def build(release=None, out_root=_ROOT / "release"):
    db = ReleaseDB(release)
    if db.primary_unavailable:
        raise SystemExit(f"primary datasets unavailable ({db.primary_unavailable}); run from the repository")
    out = Path(out_root) / f"browse-v{db.version}"
    out.mkdir(parents=True, exist_ok=True)
    link = out / f"{DB_NAME}.sqlite"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(db.sqlite_path.resolve())
    idx, fam = build_families_db(db, out / "families.db")
    meta = metadata(db, idx, fam)
    (out / "metadata.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    return out, idx, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--release", default=None)
    a = ap.parse_args(argv)
    out, idx, _ = build(a.release)
    print(f"{out}: material_index {len(idx)} rows ({int(idx.n_633.notna().sum())} with n(633 nm)); serve with:\n  {serve_command(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
