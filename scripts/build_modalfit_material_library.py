#!/usr/bin/env python3
"""
scripts/build_modalfit_material_library.py
===============================================
Generates data/modalfit_material_library/materials_library.json: every
selectable material in materials_oxide_test.db, in the schema
slab_model_builder.py's own "Load Library..." button reads -- letting
ModalFit's native stack-BUILDER tool browse this whole catalog directly,
a different and complementary workflow from scripts/modalfit_launcher.py
(which assembles a whole stack externally and hands ModalFit one
finished model).

Persistent, not a temp directory (unlike modalfit_launcher.py's one-shot
export): a material library is meant to be loaded once and reused across
many future ModalFit model-building sessions, so its sidecar n,k CSVs are
written to a stable location and referenced by ABSOLUTE path -- see
launcher/library_export.py's docstring for why relative paths (the
convention every OTHER export in this project uses) don't work here.
Gitignored, like data/modalfit_export/ -- a regenerated build artifact,
not source.

Usage:
    python scripts/build_modalfit_material_library.py
    # then in ModalFit's slab_model_builder.py: Load Library... ->
    # data/modalfit_material_library/materials_library.json
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit import DEFAULT_DB  # noqa: E402
from materials_db.launcher.library_export import build_material_library  # noqa: E402

OUT_DIR = _ROOT / "data" / "modalfit_material_library"
OUT_JSON = OUT_DIR / "materials_library.json"


def main():
    library, errors = build_material_library(str(DEFAULT_DB), OUT_DIR)

    OUT_JSON.write_text(json.dumps(library, indent=2))

    n = len(library["materials"])
    print(f"Wrote {OUT_JSON} ({n} materials, {len(list(OUT_DIR.glob('*.csv')))} sidecar CSVs)")

    if errors:
        print(f"\n{len(errors)} material(s) failed (unexpected -- list_materials() should have "
              f"already filtered these out as named exclusions):")
        for name, msg in errors:
            print(f"  {name}: {msg}")
        raise AssertionError(f"{len(errors)} unexpected export failures -- see above")

    n_bulk = sum(1 for m in library["materials"]
                 if "BULK_APPROXIMATION" in m["label"])
    print(f"Density confidence visible in every entry's label: {n_bulk} flagged bulk_approximation, "
          f"{n - n_bulk} verified.")


if __name__ == "__main__":
    main()
