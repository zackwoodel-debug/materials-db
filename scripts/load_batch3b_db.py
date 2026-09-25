#!/usr/bin/env python3
"""
scripts/load_batch3b_db.py
=============================
Step 3 for batch 3b: load data/batch3b_4.csv (Diamond, Graphite, Tin,
Boron) into the SAME data/materials_oxide_test.db the oxide + batch-2 +
pure-element (50) pipelines already populated (appends onto the existing
131 materials -- does not recreate). Same pattern as load_batch2_db.py /
load_pure_element_db.py, reusing load_oxides_db.py's helpers directly.

Keyed by `name`, not `formula`: Diamond and Graphite share formula "C" and
must resolve to two distinct materials rows -- the same ambiguity
_find_material() (src/materials_db/export/modalfit.py) now raises on
rather than silently picking one.
"""

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqlite3
import load_oxides_db as base  # noqa: E402
from pure_element_material_list import MATERIALS_PURE_ELEMENTS  # noqa: E402

CSV_PATH = _ROOT / "data" / "batch3b_4.csv"

_BY_NAME = {m["name"]: m for m in MATERIALS_PURE_ELEMENTS if m["idx"] >= 260}
assert len(_BY_NAME) == 4, f"expected exactly 4 batch-3b materials, found {len(_BY_NAME)}"


def main():
    df = pd.read_csv(CSV_PATH)

    conn = sqlite3.connect(str(base.DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")

    n_before = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    if n_before != 131:
        conn.close()
        raise AssertionError(
            f"Expected exactly 131 materials already loaded (50 oxides + 31 batch 2 + 50 "
            f"pure elements) before appending batch 3b, found {n_before}. Refusing to "
            f"append onto an unexpected DB state -- investigate before proceeding."
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
                  "data/batch3b_4.csv.",
        )
        pubchem_source_id = base.get_or_create_source(
            conn, source_cache, "pubchem",
            title="PubChem", authors="National Center for Biotechnology Information", year=2024,
            technique="PubChem PUG REST/PUG-View", url="https://pubchem.ncbi.nlm.nih.gov",
            notes="cid/smiles/inchikey/molecular_weight/CAS from PubChem PUG REST + PUG-View "
                  "CAS heading for batch 3b.",
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
            conn, source_cache, "literature_density_batch3b",
            title="Literature density estimate (batch-3b materials with no usable MP structure)",
            technique="literature", notes="Used for Boron: RI.info-stated film density (2.10 "
                                           "g/cm3), below every crystalline boron candidate MP "
                                           "offers -- consistent with amorphous boron. See "
                                           "density_citation_* columns in data/batch3b_4.csv.",
        )
        bulk_approx_source_id = base.get_or_create_source(
            conn, source_cache, "bulk_approx_density_batch3b",
            title="MP bulk DFT density used as a film approximation (batch-3b materials)",
            technique="MP bulk DFT density used as film approximation",
            notes="Used for Sn: density_source=bulk_elemental_approximation, i.e. Materials Project's bulk-crystal "
                  "DFT density (mp_id per material in data/batch3b_4.csv) standing in for a thin-film sample whose own "
                  "density is not stated. Calculated, not measured. See the flags column in data/batch3b_4.csv.",
        )
        stats["sources"] += 5

        # materials.inchikey is UNIQUE (schema frozen, no migration -- see
        # data/CHECKPOINT_2_report.md / the standing schema-approval
        # process). PubChem does not distinguish carbon allotropes: Diamond
        # and Graphite both resolve to the same elemental-carbon CID/
        # InChIKey. Rather than crash on the constraint or silently
        # fabricate a distinct value, null out the InChIKey for whichever
        # of a colliding pair is inserted second -- SQLite's UNIQUE allows
        # any number of NULLs, and `name` (also UNIQUE, and the real
        # identity key used everywhere else in this pipeline) already
        # distinguishes the two rows unambiguously.
        seen_inchikeys = {
            row[0] for row in conn.execute("SELECT inchikey FROM materials WHERE inchikey IS NOT NULL")
        }

        for _, row in df.iterrows():
            name = row["name"]
            mat = _BY_NAME[name]
            formula = mat["formula"]
            effective_polymorph = mat["polymorph"]

            inchikey = row["inchikey"] if pd.notna(row.get("inchikey")) else None
            if inchikey is not None and inchikey in seen_inchikeys:
                print(f"  [{name}] InChIKey {inchikey} already used by another material in this "
                      f"batch (PubChem does not distinguish carbon allotropes) -- storing NULL "
                      f"for {name}, disambiguated by `name` instead.")
                inchikey = None
            elif inchikey is not None:
                seen_inchikeys.add(inchikey)

            cur = conn.execute(
                "INSERT INTO materials (name, formula, smiles, inchikey, molecular_weight, cas_number, pubchem_cid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row["name"], formula,
                 row["smiles"] if pd.notna(row.get("smiles")) else None,
                 inchikey,
                 float(row["molecular_weight"]) if pd.notna(row.get("molecular_weight")) else None,
                 row["cas_number"] if pd.notna(row.get("cas_number")) else None,
                 int(row["pubchem_cid"]) if pd.notna(row.get("pubchem_cid")) else None),
            )
            material_id = cur.lastrowid
            stats["materials"] += 1

            base.load_physical_properties(
                conn, material_id, row, mp_source_id, literature_source_id, periodictable_source_id,
                effective_polymorph, source_cache=source_cache, get_source_fn=base.get_or_create_source,
                bulk_approx_source_id=bulk_approx_source_id,
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

    print("Committed batch 3b. Row counts inserted this run:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\nPRAGMA integrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print("PRAGMA foreign_key_check:", "OK (no violations)" if not fk_violations else fk_violations)

    print("\nTotal table row counts (oxides + batch 2 + pure elements + batch 3b):")
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"  {name}: {n}")

    conn.close()


if __name__ == "__main__":
    main()
