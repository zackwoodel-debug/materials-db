#!/usr/bin/env python3
"""
scripts/load_oxides_db.py
==========================
Thin wrapper: Step 3 of the 50-oxide task. Loads data/oxides_50.csv +
data/step1_selections.json into a fresh data/materials_oxide_test.db via the
family-parameterized loader in scripts/load_family_db.py. Does NOT touch
data/materials.db.

Schema is frozen pending Aiden's approval (see data/CHECKPOINT_2_report.md):
polymorph, optical axis and SLD real-vs-imaginary distinctions are encoded in
`dataset_label` as "polymorph | source_or_quantity | axis".

The helpers other loaders import from here (load_batch2_db, load_batch3b_db,
load_pure_element_db) are re-exported unchanged.
"""

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import (  # noqa: E402,F401
    NEUTRON_WAVELENGTH_NM, RI_DATA_ROOT, SCHEMA_PATH, XRAY_ENERGY_EV, XRAY_WAVELENGTH_NM,
    build_parser, get_or_create_source, label_join, load_optical_axis, load_physical_properties,
    parse_file, parse_ri_references, run_family,
)

DB_PATH = _ROOT / "data" / "materials_oxide_test.db"
CSV_PATH = _ROOT / "data" / "oxides_50.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections.json"

OXIDE_LITERATURE_TITLE = "Literature density estimate (amorphous/glass materials with no MP structure)"
OXIDE_LITERATURE_NOTE = (
    "Used for SiO, SiO2, GeO2, Ta2O5 -- see flags column in data/oxides_50.csv for the specific value and "
    "rationale per material; verify against a primary source before relying on it."
)


def fresh_db() -> sqlite3.Connection:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def main(argv=()):
    """argv defaults to empty (not sys.argv) so callers/tests can invoke main() bare.
    Module globals are read at call time so DB_PATH / load_physical_properties can be patched."""
    a = build_parser(default_family="oxide").parse_args(list(argv))
    return run_family("oxide", CSV_PATH, SELECTIONS_PATH, DB_PATH, fresh=True, dry_run=a.dry_run,
                      strict=a.strict, report_path=a.report,
                      load_physical_fn=load_physical_properties, literature_note=OXIDE_LITERATURE_NOTE,
                      literature_title=OXIDE_LITERATURE_TITLE)


if __name__ == "__main__":
    main(sys.argv[1:])
