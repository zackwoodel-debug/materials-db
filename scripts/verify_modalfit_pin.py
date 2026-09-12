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

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit_contract import (  # noqa: E402
    CONFIRMED_BEHAVIORS, MODALFIT_COMMIT_SHA, MODALFIT_REPO_URL,
)


def main():
    if len(sys.argv) != 2:
        sys.exit(f"Usage: python {sys.argv[0]} /path/to/modalfit/clone")

    clone_path = Path(sys.argv[1])
    if not (clone_path / ".git").is_dir():
        sys.exit(f"ERROR: {clone_path} is not a git repository.")

    actual_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=clone_path, capture_output=True, text=True, check=True
    ).stdout.strip()

    actual_remote = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=clone_path, capture_output=True, text=True
    ).stdout.strip()

    print(f"Pinned:  {MODALFIT_REPO_URL} @ {MODALFIT_COMMIT_SHA}")
    print(f"Clone:   {actual_remote} @ {actual_sha}")
    print()

    if actual_sha == MODALFIT_COMMIT_SHA:
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
    print(f"  git -C {clone_path} diff {MODALFIT_COMMIT_SHA} HEAD -- physics.py slab_model_builder.py server.py model_predictor.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
