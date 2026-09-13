#!/usr/bin/env python3
"""
scripts/modalfit_builder_launcher.py
=======================================
Zero-prompt launch: rebuild the materials-db material library (fresh,
every run -- cheap, ~1.5s, pure DB + file I/O, guarantees it reflects the
current database rather than a possibly-stale previous build) and open
ModalFit's own slab-model-BUILDER tool (slab_model_builder.py) with it
pre-loaded via its real "Load Library..." code path.

This is the double-click target for "just open it, ready to use, no
questions asked": unlike scripts/modalfit_launcher.py (which interactively
assembles ONE specific stack via search/thickness prompts and hands
ModalFit a finished model to predict/fit), this asks nothing at all --
ModalFit opens with all 133 materials already browsable through its own
native "Apply from Library" picker (density confidence visible in every
row), ready for the user to build a stack by hand entirely inside
ModalFit's own UI from that point on.

A WRAPPER, not a fork: ModalFit's source is never modified. See
src/materials_db/launcher/modalfit_bridge.py's launch_builder() docstring
for exactly how the pre-loaded launch is achieved.

Requires a local ModalFit clone -- pass --modalfit-path, set the
MODALFIT_PATH environment variable, or run
scripts/setup_modalfit_launcher.sh once to save a path.
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit import DEFAULT_DB  # noqa: E402
from materials_db.launcher.library_export import build_material_library  # noqa: E402
from materials_db.launcher.modalfit_bridge import (  # noqa: E402
    ModalFitBridgeError, launch_builder, locate_modalfit_clone, verify_pin_or_warn,
)

LIBRARY_DIR = _ROOT / "data" / "modalfit_material_library"
LIBRARY_JSON = LIBRARY_DIR / "materials_library.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to materials_oxide_test.db")
    parser.add_argument("--modalfit-path", default=None,
                         help="Path to a local ModalFit clone (or set MODALFIT_PATH)")
    args = parser.parse_args()

    try:
        clone_path = locate_modalfit_clone(args.modalfit_path)
    except ModalFitBridgeError as e:
        sys.exit(f"ERROR: {e}")
    print(verify_pin_or_warn(clone_path))

    print(f"Rebuilding material library from {args.db} ...")
    import json
    library, errors = build_material_library(args.db, LIBRARY_DIR)
    LIBRARY_JSON.write_text(json.dumps(library, indent=2))
    if errors:
        print(f"WARNING: {len(errors)} material(s) failed to export and will be missing "
              f"from the library:")
        for name, msg in errors:
            print(f"  {name}: {msg}")
    n_bulk = sum(1 for m in library["materials"] if "BULK_APPROXIMATION" in m["label"])
    print(f"Library ready: {len(library['materials'])} materials "
          f"({n_bulk} bulk_approximation, {len(library['materials']) - n_bulk} verified).")

    print(f"Opening ModalFit's stack builder ({clone_path}) with the library pre-loaded...")
    launch_builder(LIBRARY_JSON, clone_path)


if __name__ == "__main__":
    main()
