#!/usr/bin/env python3
"""Entry point: initialise the database if needed, then start the API server."""

import subprocess
import sys
from pathlib import Path

import uvicorn

_ROOT = Path(__file__).resolve().parent
_DATA_DIR = _ROOT / "data"
_DB = _DATA_DIR / "materials.db"

if not _DB.exists():
    print("Database missing - running init_db.py...")
    _DATA_DIR.mkdir(exist_ok=True)

    result = subprocess.run(
        [sys.executable, str(_ROOT / "init_db.py")],
        cwd=str(_ROOT),
    )
    if result.returncode != 0:
        sys.exit("[✗] init_db.py failed — cannot start server.")

    # init_db.py writes to the project root; link it into data/ so the API
    # can resolve data/materials.db without a second copy of the file.
    root_db = _ROOT / "materials.db"
    if root_db.exists() and not _DB.exists():
        _DB.symlink_to(f"../{root_db.name}")

print("MatChat running at http://127.0.0.1:8000")
uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=False)
