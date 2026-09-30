#!/usr/bin/env python3
"""
scripts/verify_modalfit_pin.py
================================
Check whether a ModalFit clone is at the exact commit
src/materials_db/export/modalfit_contract.py's schema assumptions were
verified against. Run this FIRST whenever ModalFit-integration behavior
looks wrong -- it tells you immediately whether to suspect materials-db's
exporter or upstream drift, before re-deriving anything.

Usage:
    python scripts/verify_modalfit_pin.py /path/to/modalfit/clone
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit_contract import CONFIRMED_BEHAVIORS, MODALFIT_COMMIT_SHA  # noqa: E402
from materials_db.export.modalfit_pin import check_pin  # noqa: E402,F401 (library entry point; re-exported for old imports)


def main():
    if len(sys.argv) != 2:
        sys.exit(f"Usage: python {sys.argv[0]} /path/to/modalfit/clone")

    try:
        result = check_pin(sys.argv[1])
    except FileNotFoundError as e:
        sys.exit(f"ERROR: {e}")

    print(f"Pinned:  {result['pinned_repo']} @ {result['pinned_sha']}")
    print(f"Clone:   {result['actual_remote']} @ {result['actual_sha']}")
    print()

    if result["match"]:
        print("MATCH -- clone is at the exact pinned commit. Any schema mismatch "
              "you're seeing is a materials-db bug, not upstream drift.")
        return 0

    print("MISMATCH -- this clone has moved since the pin. Before assuming a "
          "materials-db bug, check whether these confirmed behaviors still hold "
          "in the new commit:")
    for name, info in CONFIRMED_BEHAVIORS.items():
        print(f"\n  [{name}]")
        print(f"    was confirmed at: {info['file']} lines {info['lines']} ({info['function']})")
    print(f"\nDiff the pinned commit against HEAD to see what changed:")
    print(f"  git -C {sys.argv[1]} diff {MODALFIT_COMMIT_SHA} HEAD -- physics.py slab_model_builder.py server.py model_predictor.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
