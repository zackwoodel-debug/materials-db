#!/usr/bin/env python3
"""Audit the database, print the schema, then start the MatChat API server."""

import sqlite3
import sys
from pathlib import Path

import uvicorn
from rich.console import Console

_ROOT = Path(__file__).resolve().parent
_DB   = str(_ROOT / "data" / "materials.db")
_con  = Console()

# Ensure the project root is on sys.path so core/ and api/ are importable.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.audit  import run_audit
from core.schema import get_schema_summary

if not run_audit():
    sys.exit(1)

conn   = sqlite3.connect(_DB)
schema = get_schema_summary(conn)
conn.close()

_con.print("\n[bold blue]Schema summary[/bold blue]")
_con.print(schema)
_con.print("\n[bold green]MatChat running at http://127.0.0.1:8000[/bold green]\n")

uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=False)
