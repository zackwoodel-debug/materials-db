#!/usr/bin/env python3
"""Regenerate src/materials_db/export/mp_ids.json from data/*.csv (materials_db.export.mp_ids.build_map). Run after adding or
changing a family CSV; tests/test_mp_id_map.py fails while the packaged map is stale.

    python3 scripts/build_mp_id_map.py
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.mp_ids import MAP_PATH, build_map  # noqa: E402


def main():
    ids, files = build_map(_ROOT / "data")
    doc = dict(description="formula -> Materials Project id, derived from the family tables in data/*.csv by "
                           "materials_db.export.mp_ids.build_map; Materials Project data, CC BY 4.0 (see DATA_LICENSE.md)",
               source_files=files, formulas=ids)
    MAP_PATH.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"{MAP_PATH.relative_to(_ROOT)}: {len(ids)} formulas ({sum(1 for v in ids.values() if v)} with an id) from {len(files)} files")


if __name__ == "__main__":
    main()
