#!/usr/bin/env python3
"""
scripts/load_nitrides_db.py
============================
Thin wrapper: loads data/nitrides.csv + data/step1_selections_nitrides.json into a FRESH
data/materials_nitride_test.db via load_family_db.run_family. Touches no other database.
Schema frozen (Aiden): polymorph/axis live in dataset_label.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_family_db import build_parser, load_physical_properties, run_family  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_nitride_test.db"
CSV_PATH = _ROOT / "data" / "nitrides.csv"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections_nitrides.json"

LITERATURE_TITLE = "Literature density estimate (nitride materials with no trustworthy measured film density)"
LITERATURE_TECHNIQUE = "MP bulk DFT density used as film approximation (TiN, VN)"
LITERATURE_NOTE = (
    "Used for TiN and VN: density_source=bulk_elemental_approximation, i.e. Materials Project's bulk-crystal DFT "
    "density standing in for an unmeasured thin-film sample (every RI.info TiN/VN entry is a film). Calculated, "
    "not measured. See flags column in data/nitrides.csv."
)


def main(argv=()):
    """Default: rebuild the fresh test DB. With --merge-into PATH: idempotent, non-destructive upsert into an existing DB."""
    p = build_parser(default_family="nitride")
    p.add_argument("--merge-into", help="upsert into this existing DB instead of rebuilding the test DB")
    a = p.parse_args(list(argv))
    target, fresh = (Path(a.merge_into), False) if a.merge_into else (DB_PATH, True)
    return run_family("nitride", CSV_PATH, SELECTIONS_PATH, target, fresh=fresh, dry_run=a.dry_run, strict=a.strict,
                      report_path=a.report, load_physical_fn=load_physical_properties, literature_title=LITERATURE_TITLE,
                      literature_technique=LITERATURE_TECHNIQUE, literature_note=LITERATURE_NOTE)


if __name__ == "__main__":
    main(sys.argv[1:])
