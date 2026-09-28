#!/usr/bin/env python3
"""
scripts/load_glass_catalogs_db.py
=================================
Thin wrapper: loads data/glass_catalogs.csv + data/step1_selections_glass_catalogs.json into a FRESH
data/materials_glass_catalog_test.db via load_family_db.run_family (no new loader). Catalog glasses have NULL formulas (allowed,
as for the glasses family); densities are the datasheets'. Touches no other database.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import build_parser, load_physical_properties, run_family  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_glass_catalog_test.db"
CSV_PATH = _ROOT / "data" / "glass_catalogs.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_glass_catalogs.json"

LITERATURE_TITLE = "Manufacturer glass catalog datasheets (via refractiveindex.info)"
LITERATURE_TECHNIQUE = "literature (manufacturer datasheet)"
LITERATURE_NOTE = "Density stated by the glass manufacturer's catalog datasheet."


def main(argv=()):
    a = build_parser(default_family="glass_catalog").parse_args(list(argv))
    return run_family("glass_catalog", CSV_PATH, SELECTIONS_PATH, DB_PATH, fresh=True, dry_run=a.dry_run, strict=a.strict,
                      report_path=a.report, load_physical_fn=load_physical_properties, literature_title=LITERATURE_TITLE,
                      literature_technique=LITERATURE_TECHNIQUE, literature_note=LITERATURE_NOTE, allow_null_formula=True)


if __name__ == "__main__":
    main(sys.argv[1:])
