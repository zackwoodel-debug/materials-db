#!/usr/bin/env python3
"""
init_db.py
Full database initialisation pipeline. Run from the project root.

Steps (sequential, hard-fail on any nonzero exit):
  1. core/schema.sql          — create tables, indexes, spr_data view
  2. pipeline/fetch_optical_data.py — clone RI.info, parse, populate DB
  3. core/seed_manual.sql     — unique indexes + manual-entry inserts
  4. core/audit.py            — integrity checks and DPPC auto-remediation
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB   = ROOT / "materials.db"


def step(label: str, cmd: list[str], stdin_path: Path | None = None) -> None:
    print(f"[ ] Running: {label} ...", flush=True)
    kwargs: dict = {"cwd": str(ROOT)}
    if stdin_path is not None:
        kwargs["stdin"] = open(stdin_path)
    result = subprocess.run(cmd, **kwargs)
    if stdin_path is not None:
        kwargs["stdin"].close()
    if result.returncode != 0:
        print("[✗] Failed — abort.", flush=True)
        sys.exit(result.returncode)
    print("[✓] Done\n", flush=True)


if __name__ == "__main__":
    step(
        "1/4  core/schema.sql (tables + view)",
        ["sqlite3", str(DB)],
        stdin_path=ROOT / "core" / "schema.sql",
    )
    step(
        "2/4  pipeline/fetch_optical_data.py",
        [sys.executable, str(ROOT / "pipeline" / "fetch_optical_data.py")],
    )
    step(
        "3/4  core/seed_manual.sql (unique indexes + manual inserts)",
        ["sqlite3", str(DB)],
        stdin_path=ROOT / "core" / "seed_manual.sql",
    )
    step(
        "4/4  core/audit.py",
        [sys.executable, str(ROOT / "core" / "audit.py")],
    )
    print("Pipeline complete.")
