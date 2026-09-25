#!/usr/bin/env python3
"""
scripts/load_chalcogenides_db.py
=================================
Thin wrapper: loads data/chalcogenides.csv + data/step1_selections_chalcogenides.json into a FRESH data/materials_chalcogenide_test.db via
load_family_db.run_family (no new loader). Touches no other database. Schema frozen (Aiden): phase/axis live in dataset_label.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import build_parser, load_physical_properties, run_family  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_chalcogenide_test.db"
CSV_PATH = _ROOT / "data" / "chalcogenides.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_chalcogenides.json"

LITERATURE_TITLE = "MP bulk DFT density used as a film approximation (chalcogenide family)"
LITERATURE_TECHNIQUE = "MP bulk DFT density used as film approximation (As2Se3)"
LITERATURE_NOTE = ("Used for As2Se3: density_source=bulk_elemental_approximation, i.e. Materials Project's crystalline DFT density standing in for the "
                   "400 nm / 700 nm films on glass the optical data were measured on (film density not stated). Calculated, not measured. "
                   "See flags in data/chalcogenides.csv.")


def main(argv=()):
    a = build_parser(default_family="chalcogenide").parse_args(list(argv))
    return run_family("chalcogenide", CSV_PATH, SELECTIONS_PATH, DB_PATH, fresh=True, dry_run=a.dry_run, strict=a.strict, report_path=a.report,
                      load_physical_fn=load_physical_properties, literature_title=LITERATURE_TITLE,
                      literature_technique=LITERATURE_TECHNIQUE, literature_note=LITERATURE_NOTE)


if __name__ == "__main__":
    main(sys.argv[1:])
