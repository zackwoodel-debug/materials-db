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

import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB   = ROOT / "materials.db"


def run_sql_file(db_path: Path, sql_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn.executescript(sql)
    conn.commit()
    conn.close()


def step(label: str, cmd: list[str] | None = None, sql_path: Path | None = None) -> None:
    print(f"[ ] Running: {label} ...", flush=True)
    try:
        if sql_path is not None:
            run_sql_file(DB, sql_path)
        elif cmd is not None:
            result = subprocess.run(cmd, cwd=str(ROOT))
            if result.returncode != 0:
                raise RuntimeError(f"Subprocess returned exit code {result.returncode}")
        print("[✓] Done\n", flush=True)
    except Exception as exc:
        print(f"[✗] Failed — abort: {exc}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    step(
        "1/4  core/schema.sql (tables + view)",
        sql_path=ROOT / "core" / "schema.sql",
    )
    step(
        "2/4  pipeline/fetch_optical_data.py",
        cmd=[sys.executable, str(ROOT / "pipeline" / "fetch_optical_data.py")],
    )
    step(
        "3/4  core/seed_manual.sql (unique indexes + manual inserts)",
        sql_path=ROOT / "core" / "seed_manual.sql",
    )
    step(
        "4/4  core/audit.py",
        cmd=[sys.executable, str(ROOT / "core" / "audit.py")],
    )
    print("Pipeline complete.")
