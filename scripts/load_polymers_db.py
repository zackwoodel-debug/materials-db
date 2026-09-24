#!/usr/bin/env python3
"""
scripts/load_polymers_db.py
============================
Thin wrapper: loads data/polymers.csv + data/step1_selections_polymers.json into a FRESH data/materials_polymer_test.db via
load_family_db.run_family (no new loader). Touches no other database.

Polymer family config: NULL formula is valid (grade-specific commercial materials; the material NAME carries the grade), no
reference sources (no polymer here has a traceable density, so nothing would cite MP / periodictable / a literature-density
estimate), deferred selection entries are skipped, and formula-vs-tabulated duplicates at a shared wavelength are collapsed
(tabulated row kept, every drop reported). Density and SLD stay NULL. No chemical descriptors are ever created.
Schema frozen (Aiden): polymorph/axis conventions live in dataset_label; nothing here adds a column.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import build_parser, load_physical_properties, run_family  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_polymer_test.db"
CSV_PATH = _ROOT / "data" / "polymers.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_polymers.json"


def main(argv=()):
    a = build_parser(default_family="polymer").parse_args(list(argv))
    return run_family("polymer", CSV_PATH, SELECTIONS_PATH, DB_PATH, fresh=True, dry_run=a.dry_run, strict=a.strict,
                      report_path=a.report, load_physical_fn=load_physical_properties,
                      allow_null_formula=True, reference_sources=False, collapse_block_duplicates=True)


if __name__ == "__main__":
    main(sys.argv[1:])
