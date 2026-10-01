#!/usr/bin/env python3
"""
scripts/load_batch3b_db.py
=============================
Step 3 for batch 3b: load data/batch3b_4.csv (Diamond, Graphite, Tin,
Boron) into the SAME data/materials_oxide_test.db the oxide + batch-2 +
pure-element (50) pipelines already populated (appends onto the existing
131 materials -- does not recreate).

Keyed by `name`, not `formula`: Diamond and Graphite share formula "C" and
must resolve to two distinct materials rows -- the same ambiguity
_find_material() (src/materials_db/export/modalfit.py) now raises on
rather than silently picking one.

A thin wrapper over the shared family loader (scripts/load_family_db.py
run_family), like every other family (Phase 5 pilot, 2026-09-30). The
batch's policies are passed explicitly here or kept in data:
  - selections: data/step1_selections_batch3b.json (generated from
    scripts/pure_element_material_list.py by build_batch3b_selections.py),
    keyed by name;
  - InChIKey: PubChem gives Diamond and Graphite one InChIKey; the later one
    is stored as NULL (materials.inchikey is UNIQUE; any number of NULLs are
    allowed, and `name` identifies the row);
  - sources: this batch's own source rows (its PubChem / periodictable /
    literature / bulk-approximation provenance text), never reusing a row
    from before the run, exactly as the original loader created them.
Parity with the original loader is proven in tests/test_batch3b_loader.py.
"""

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import load_oxides_db as base  # noqa: E402
from load_family_db import NEUTRON_WAVELENGTH_NM, XRAY_ENERGY_EV, XRAY_WAVELENGTH_NM, run_family  # noqa: E402

CSV_PATH = _ROOT / "data" / "batch3b_4.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_batch3b.json"
EXPECTED_BEFORE = 131  # 50 oxides + 31 batch 2 + 50 pure elements

NAMED_SOURCE_FIELDS = {
    "pubchem": dict(notes="cid/smiles/inchikey/molecular_weight/CAS from PubChem PUG REST + PUG-View CAS heading for batch 3b."),
    "periodictable": dict(notes=f"xray_sld at {XRAY_ENERGY_EV} eV (Cu K-alpha, {XRAY_WAVELENGTH_NM} nm); "
                                f"neutron_sld at {NEUTRON_WAVELENGTH_NM} nm (thermal), natural isotopic abundance"),
}
LITERATURE_TITLE = "Literature density estimate (batch-3b materials with no usable MP structure)"
LITERATURE_NOTE = ("Used for Boron: RI.info-stated film density (2.10 g/cm3), below every crystalline boron candidate MP offers "
                   "-- consistent with amorphous boron. See density_citation_* columns in data/batch3b_4.csv.")
BULK_APPROX_SOURCE = dict(
    title="MP bulk DFT density used as a film approximation (batch-3b materials)",
    technique="MP bulk DFT density used as film approximation",
    notes="Used for Sn: density_source=bulk_elemental_approximation, i.e. Materials Project's bulk-crystal DFT density (mp_id per "
          "material in data/batch3b_4.csv) standing in for a thin-film sample whose own density is not stated. Calculated, not "
          "measured. See the flags column in data/batch3b_4.csv.")
# Density-citation notes name this batch's own catalog (until v0.21.0 they wrongly named data/oxides_50.csv).
CITATION_CATALOG_NAME = "batch3b_4.csv"


def main(argv=()):
    db_path = base.DB_PATH
    with sqlite3.connect(str(db_path)) as conn:
        n_before = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    if n_before != EXPECTED_BEFORE:
        raise AssertionError(
            f"Expected exactly {EXPECTED_BEFORE} materials already loaded (50 oxides + 31 batch 2 + 50 pure elements) before "
            f"appending batch 3b, found {n_before}. Refusing to append onto an unexpected DB state -- investigate before proceeding.")
    return run_family("batch3b", CSV_PATH, SELECTIONS_PATH, db_path, fresh=False,
                      load_physical_fn=base.load_physical_properties, selection_key_column="name",
                      on_duplicate_inchikey="store_null", reuse_existing_source_rows=False,
                      named_source_fields=NAMED_SOURCE_FIELDS, literature_title=LITERATURE_TITLE, literature_note=LITERATURE_NOTE,
                      bulk_approx_source=BULK_APPROX_SOURCE, citation_catalog_name=CITATION_CATALOG_NAME)


if __name__ == "__main__":
    main(sys.argv[1:])
