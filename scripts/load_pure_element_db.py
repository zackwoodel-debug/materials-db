#!/usr/bin/env python3
"""
scripts/load_pure_element_db.py
==================================
Step 3 for the batch-3 triage set: load data/pure_element_triage.csv into
the SAME materials_oxide_test.db the oxide + batch-2 pipelines populated
(appends onto the existing 81 materials -- does not recreate). Same
pattern as load_batch2_db.py, reusing load_oxides_db.py's helpers directly.
"""

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqlite3
import load_oxides_db as base  # noqa: E402
from pure_element_material_list import MATERIALS_ELEMENT_TRIAGE  # noqa: E402

CSV_PATH = _ROOT / "data" / "pure_element_triage.csv"

_BY_FORMULA = {m["formula"]: m for m in MATERIALS_ELEMENT_TRIAGE}


def main():
    df = pd.read_csv(CSV_PATH)

    conn = sqlite3.connect(str(base.DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")

    n_before = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    if n_before != 81:
        conn.close()
        raise AssertionError(
            f"Expected exactly 81 materials already loaded (50 oxides + 31 batch 2) before "
            f"appending the pure-element triage set, found {n_before}. Refusing to append "
            f"onto an unexpected DB state -- investigate before proceeding."
        )

    source_cache = {}
    stats = dict(materials=0, physical_properties=0, optical_dispersion=0, sources=0)

    try:
        mp_source_id = base.get_or_create_source(
            conn, source_cache, "mp",
            title="Materials Project", authors="Materials Project Consortium", year=2013,
            technique="DFT (Materials Project)", url="https://materialsproject.org",
            doi="10.1063/1.4812323",
            notes="mp-api queries against the Materials Project summary endpoint; see "
                  "mp_id/mp_space_group/mp_energy_above_hull_ev per-material in "
                  "data/pure_element_triage.csv.",
        )
        pubchem_source_id = base.get_or_create_source(
            conn, source_cache, "pubchem",
            title="PubChem", authors="National Center for Biotechnology Information", year=2024,
            technique="PubChem PUG REST/PUG-View", url="https://pubchem.ncbi.nlm.nih.gov",
            notes="cid/smiles/inchikey/molecular_weight/CAS from PubChem PUG REST + PUG-View "
                  "CAS heading for the pure-element triage set.",
        )
        periodictable_source_id = base.get_or_create_source(
            conn, source_cache, "periodictable",
            title="periodictable: x-ray and neutron scattering length density calculation",
            authors="periodictable Python package", technique="calculated",
            url="https://periodictable.readthedocs.io",
            notes=f"xray_sld at {base.XRAY_ENERGY_EV} eV (Cu K-alpha, {base.XRAY_WAVELENGTH_NM} nm); "
                  f"neutron_sld at {base.NEUTRON_WAVELENGTH_NM} nm (thermal), natural isotopic abundance",
        )
        literature_source_id = base.get_or_create_source(
            conn, source_cache, "literature_density_batch3",
            title="Literature density estimate (batch-3 materials with no trustworthy measured density)",
            technique="literature", notes="Placeholder source id for parity with other batches; "
                                           "no batch-3-triage material currently uses a literature "
                                           "density citation (Au/Se/Te are MP_DFT or bulk-"
                                           "approximation, not literature-cited).",
        )
        stats["sources"] += 4

        for _, row in df.iterrows():
            formula = row["formula"]
            mat = _BY_FORMULA[formula]
            effective_polymorph = mat["polymorph"]

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

            base.load_physical_properties(
                conn, material_id, row, mp_source_id, literature_source_id, periodictable_source_id,
                effective_polymorph, source_cache=source_cache, get_source_fn=base.get_or_create_source,
            )
            stats["physical_properties"] += conn.execute(
                "SELECT COUNT(*) FROM physical_properties WHERE material_id = ?", (material_id,)
            ).fetchone()[0]

            for axis_entry_raw in mat["ri_axes"]:
                data_path = axis_entry_raw["data_path"]
                axis_entry = dict(
                    data_path=data_path,
                    dataset_label=base.label_join(effective_polymorph, axis_entry_raw["source_label"],
                                                   axis_entry_raw["axis"]),
                )
                ref = base.parse_ri_references(data_path)
                src_id = base.get_or_create_source(
                    conn, source_cache, data_path,
                    doi=ref["doi"], title=ref["title"], authors=ref["authors"], year=ref["year"],
                    technique="refractiveindex.info", url=ref["url"] or "https://refractiveindex.info",
                    notes=ref["notes"],
                )
                n_pts = base.load_optical_axis(conn, material_id, src_id, axis_entry, effective_polymorph)
                stats["optical_dispersion"] += n_pts

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    print("Committed pure-element triage set. Row counts inserted this run:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\nPRAGMA integrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("PRAGMA foreign_key_check:", "OK (no violations)" if not fk_violations else fk_violations)

    print("\nTotal table row counts:")
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"  {name}: {n}")

    conn.close()


if __name__ == "__main__":
    main()
