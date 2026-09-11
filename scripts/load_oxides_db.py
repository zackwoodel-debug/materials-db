#!/usr/bin/env python3
"""
scripts/load_oxides_db.py
==========================
Step 3 of the 50-oxide task: load data/oxides_50.csv + data/step1_selections.json
into a fresh data/materials_oxide_test.db built from updated_sql_schema.sql.
Does NOT touch data/materials.db.

Per the agreed convention (schema is frozen pending Aiden's approval, see
data/CHECKPOINT_2_report.md): no new columns. Polymorph, optical axis, and
SLD real-vs-imaginary distinctions are all encoded in the existing
`dataset_label` text column as "polymorph | source_or_quantity | axis".

Everything happens inside a single transaction; any exception rolls back the
whole load so the DB is never left half-populated.
"""

import html
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
import materials_db.pipeline.fetch_optical_data as _fetch_optical_data  # noqa: E402
from materials_db.pipeline.fetch_optical_data import parse_file  # noqa: E402

_fetch_optical_data.WL_MIN_NM = 0.01
_fetch_optical_data.WL_MAX_NM = 2_000_000.0

SCHEMA_PATH = _ROOT / "updated_sql_schema.sql"
DB_PATH = _ROOT / "data" / "materials_oxide_test.db"
CSV_PATH = _ROOT / "data" / "oxides_50.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections.json"
RI_DATA_ROOT = _ROOT / "refractiveindex_db" / "database" / "data"

XRAY_ENERGY_EV = 8048.0
XRAY_WAVELENGTH_NM = 0.15406
NEUTRON_WAVELENGTH_NM = 0.1798


def fresh_db() -> sqlite3.Connection:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def parse_ri_references(data_path: str) -> dict:
    p = RI_DATA_ROOT / data_path
    raw = yaml.safe_load(open(p))
    refs = raw.get("REFERENCES") or ""
    if isinstance(refs, list):
        refs = " | ".join(str(r) for r in refs)
    refs = str(refs)

    doi = None
    m = re.search(r"doi\.org/([^\s\"<>]+)", refs)
    if m:
        doi = m.group(1).rstrip(".,")

    url = None
    m2 = re.search(r'href="([^"]+)"', refs)
    if m2:
        url = html.unescape(m2.group(1))

    plain = re.sub(r"<[^>]+>", "", refs)
    plain = html.unescape(plain)
    lines = [l.strip().lstrip("0123456789) ").strip() for l in plain.splitlines() if l.strip()]
    authors = lines[0] if lines else None
    title = lines[1] if len(lines) > 1 else None

    year = None
    ym = re.search(r"\((\d{4})\)", plain)
    if ym:
        year = int(ym.group(1))

    return dict(doi=doi, url=url, authors=authors, title=title, year=year, notes=plain[:1000])


def get_or_create_source(conn, cache: dict, key, **fields) -> int:
    if key in cache:
        return cache[key]
    if fields.get("doi"):
        row = conn.execute("SELECT source_id FROM sources WHERE doi = ?", (fields["doi"],)).fetchone()
        if row:
            cache[key] = row[0]
            return row[0]
    cur = conn.execute(
        "INSERT INTO sources (doi, title, authors, journal, year, technique, url, uncertainty, notes) "
        "VALUES (:doi, :title, :authors, :journal, :year, :technique, :url, :uncertainty, :notes)",
        dict(doi=fields.get("doi"), title=fields.get("title"), authors=fields.get("authors"),
             journal=fields.get("journal"), year=fields.get("year"), technique=fields.get("technique"),
             url=fields.get("url"), uncertainty=fields.get("uncertainty"), notes=fields.get("notes")),
    )
    cache[key] = cur.lastrowid
    return cur.lastrowid


def label_join(polymorph, *parts) -> str:
    segs = [polymorph] if polymorph else []
    segs += [p for p in parts if p]
    return " | ".join(segs)


def load_optical_axis(conn, material_id, source_id, axis_entry, effective_polymorph):
    data_path = axis_entry["data_path"]
    dataset_label = axis_entry["dataset_label"]
    yaml_path = RI_DATA_ROOT / data_path
    wl_nm, n_val, k_val, refs, temp_c = parse_file(yaml_path)

    n_inserted = 0
    for i in range(len(wl_nm)):
        n = float(n_val[i])
        k = None
        if k_val is not None and not np.isnan(k_val[i]):
            k = float(k_val[i])
        if n is None and k is None:
            continue
        conn.execute(
            "INSERT INTO optical_dispersion "
            "(material_id, wavelength_nm, n, k, temperature_c, dataset_label, raw_record_table, raw_record_id, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (material_id, float(wl_nm[i]), n, k, temp_c, dataset_label, data_path, i, source_id),
        )
        n_inserted += 1
    return n_inserted


def load_physical_properties(conn, material_id, row, mp_source_id, literature_source_id, periodictable_source_id, effective_polymorph):
    density = row.get("density_g_cm3")
    density_source = row.get("density_source")

    if pd.notna(density):
        src = mp_source_id if density_source == "MP_DFT" else literature_source_id
        conn.execute(
            "INSERT INTO physical_properties (material_id, density_g_cm3, dataset_label, source_id) "
            "VALUES (?, ?, ?, ?)",
            (material_id, float(density), label_join(effective_polymorph, f"density_{density_source}"), src),
        )

    if pd.notna(row.get("xray_sld_real")):
        conn.execute(
            "INSERT INTO physical_properties (material_id, xray_sld, energy_ev, wavelength_nm, dataset_label, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (material_id, float(row["xray_sld_real"]), XRAY_ENERGY_EV, XRAY_WAVELENGTH_NM,
             label_join(effective_polymorph, "xray_sld_real", "periodictable_CuKalpha"), periodictable_source_id),
        )
    if pd.notna(row.get("xray_sld_imag")):
        conn.execute(
            "INSERT INTO physical_properties (material_id, xray_sld, energy_ev, wavelength_nm, dataset_label, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (material_id, float(row["xray_sld_imag"]), XRAY_ENERGY_EV, XRAY_WAVELENGTH_NM,
             label_join(effective_polymorph, "xray_sld_imag", "periodictable_CuKalpha"), periodictable_source_id),
        )
    if pd.notna(row.get("neutron_sld_real")):
        conn.execute(
            "INSERT INTO physical_properties (material_id, neutron_sld, wavelength_nm, dataset_label, source_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (material_id, float(row["neutron_sld_real"]), NEUTRON_WAVELENGTH_NM,
             label_join(effective_polymorph, "neutron_sld_real", "periodictable_thermal"), periodictable_source_id),
        )
    if pd.notna(row.get("neutron_sld_imag")):
        conn.execute(
            "INSERT INTO physical_properties (material_id, neutron_sld, wavelength_nm, dataset_label, source_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (material_id, float(row["neutron_sld_imag"]), NEUTRON_WAVELENGTH_NM,
             label_join(effective_polymorph, "neutron_sld_imag", "periodictable_thermal"), periodictable_source_id),
        )


def main():
    df = pd.read_csv(CSV_PATH)
    selections = json.load(open(SELECTIONS_PATH))

    conn = fresh_db()
    conn.execute("PRAGMA foreign_keys = ON")
    source_cache = {}
    stats = dict(materials=0, physical_properties=0, optical_dispersion=0, sources=0)

    try:
        mp_source_id = get_or_create_source(
            conn, source_cache, "mp",
            title="Materials Project", authors="Materials Project Consortium", year=2013,
            technique="DFT (Materials Project)", url="https://materialsproject.org",
            doi="10.1063/1.4812323",
            notes="mp-api queries against the Materials Project summary endpoint; see mp_id/mp_space_group/"
                  "mp_energy_above_hull_ev provenance recorded per-material in data/oxides_50.csv and "
                  "data/raw_cache/mp/*.json",
        )
        pubchem_source_id = get_or_create_source(
            conn, source_cache, "pubchem",
            title="PubChem", authors="National Center for Biotechnology Information", year=2024,
            technique="PubChem PUG REST/PUG-View", url="https://pubchem.ncbi.nlm.nih.gov",
            notes="cid/smiles/inchikey/molecular_weight/CAS from PubChem PUG REST + PUG-View CAS heading; "
                  "raw responses cached under data/raw_cache/pubchem/",
        )
        periodictable_source_id = get_or_create_source(
            conn, source_cache, "periodictable",
            title="periodictable: x-ray and neutron scattering length density calculation",
            authors="periodictable Python package", technique="calculated",
            url="https://periodictable.readthedocs.io",
            notes=f"xray_sld at {XRAY_ENERGY_EV} eV (Cu K-alpha, {XRAY_WAVELENGTH_NM} nm); "
                  f"neutron_sld at {NEUTRON_WAVELENGTH_NM} nm (thermal, 2200 m/s reference), natural isotopic abundance",
        )
        literature_source_id = get_or_create_source(
            conn, source_cache, "literature_density",
            title="Literature density estimate (amorphous/glass materials with no MP structure)",
            technique="literature", notes="Used for SiO, SiO2, GeO2, Ta2O5 -- see flags column in "
                                           "data/oxides_50.csv for the specific value and rationale per material; "
                                           "verify against a primary source before relying on it.",
        )
        stats["sources"] += 4

        for _, row in df.iterrows():
            formula = row["formula"]
            sel = selections.get(formula, {})
            effective_polymorph = sel.get("effective_polymorph") or (row["polymorph"] if pd.notna(row.get("polymorph")) else None)

            cur = conn.execute(
                "INSERT INTO materials (name, formula, smiles, inchikey, molecular_weight, cas_number, pubchem_cid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row["name"], formula,
                 row["smiles"] if pd.notna(row.get("smiles")) else None,
                 row["inchikey"] if pd.notna(row.get("inchikey")) else None,
                 float(row["molecular_weight"]) if pd.notna(row.get("molecular_weight")) else None,
                 row["cas_number"] if pd.notna(row.get("cas_number")) else None,
                 int(row["pubchem_cid"]) if pd.notna(row.get("pubchem_cid")) else None),
            )
            material_id = cur.lastrowid
            stats["materials"] += 1

            load_physical_properties(conn, material_id, row, mp_source_id, literature_source_id, periodictable_source_id, effective_polymorph)
            stats["physical_properties"] += conn.execute(
                "SELECT COUNT(*) FROM physical_properties WHERE material_id = ?", (material_id,)
            ).fetchone()[0]

            for axis_entry in sel.get("axes", []):
                ref = parse_ri_references(axis_entry["data_path"])
                src_id = get_or_create_source(
                    conn, source_cache, axis_entry["data_path"],
                    doi=ref["doi"], title=ref["title"], authors=ref["authors"], year=ref["year"],
                    technique="refractiveindex.info", url=ref["url"] or "https://refractiveindex.info",
                    notes=ref["notes"],
                )
                n_pts = load_optical_axis(conn, material_id, src_id, axis_entry, effective_polymorph)
                stats["optical_dispersion"] += n_pts

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    print("Committed. Row counts:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\nPRAGMA integrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("PRAGMA foreign_key_check:", "OK (no violations)" if not fk_violations else fk_violations)

    print("\nActual table row counts:")
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"  {name}: {n}")

    conn.close()


if __name__ == "__main__":
    main()
