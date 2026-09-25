#!/usr/bin/env python3
"""
scripts/load_liquids_db.py
===========================
Thin wrapper: loads data/liquids.csv + data/step1_selections_liquids.json into a FRESH data/materials_liquid_test.db via
load_family_db.run_family (no new loader). Touches no other database. Schema frozen (Aiden): phase lives in dataset_label.
DNA and silk fibroin have no single molecular formula, so NULL formulas are allowed (as for the proprietary polymers).
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import build_parser, load_physical_properties, run_family  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_liquid_test.db"
CSV_PATH = _ROOT / "data" / "liquids.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_liquids.json"

LITERATURE_TITLE = "Bulk density used for a film or powder sample (liquids and biomolecules family)"
LITERATURE_TECHNIQUE = "bulk density used as a film/powder approximation"
LITERATURE_NOTE = "Used when the optical sample is a film or powder and only the bulk (crystal) density is known. See flags in data/liquids.csv."


def main(argv=()):
    a = build_parser(default_family="liquid").parse_args(list(argv))
    return run_family("liquid", CSV_PATH, SELECTIONS_PATH, DB_PATH, fresh=True, dry_run=a.dry_run, strict=a.strict, report_path=a.report,
                      load_physical_fn=load_physical_properties, literature_title=LITERATURE_TITLE, literature_technique=LITERATURE_TECHNIQUE,
                      literature_note=LITERATURE_NOTE, allow_null_formula=True)


if __name__ == "__main__":
    main(sys.argv[1:])
