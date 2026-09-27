#!/usr/bin/env python3
"""
scripts/load_liquid_crystals_db.py
====================================
Thin wrapper: loads data/liquid_crystals.csv + data/step1_selections_liquid_crystals.json into a FRESH data/materials_liquid_crystal_test.db via
load_family_db.run_family (no new loader). Liquid-crystal mixtures have no single formula, so NULL formulas are allowed (as for the proprietary
polymers). Touches no other database.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import build_parser, load_physical_properties, run_family  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_liquid_crystal_test.db"
CSV_PATH = _ROOT / "data" / "liquid_crystals.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_liquid_crystals.json"

LITERATURE_TITLE = "unused (no densities in the liquid-crystal family)"
LITERATURE_TECHNIQUE = "unused"
LITERATURE_NOTE = "unused"


def main(argv=()):
    a = build_parser(default_family="liquid_crystal").parse_args(list(argv))
    return run_family("liquid_crystal", CSV_PATH, SELECTIONS_PATH, DB_PATH, fresh=True, dry_run=a.dry_run, strict=a.strict, report_path=a.report,
                      load_physical_fn=load_physical_properties, literature_title=LITERATURE_TITLE,
                      literature_technique=LITERATURE_TECHNIQUE, literature_note=LITERATURE_NOTE, allow_null_formula=True)


if __name__ == "__main__":
    main(sys.argv[1:])
