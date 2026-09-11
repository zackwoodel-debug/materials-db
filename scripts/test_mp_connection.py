#!/usr/bin/env python3
"""One-off connectivity check: confirm MP_API_KEY (from .env) authenticates
against the Materials Project API. Never prints or logs the key itself."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")

key = os.environ.get("MP_API_KEY")
if not key:
    print("FAIL: MP_API_KEY not set after loading .env")
    sys.exit(1)

from mp_api.client import MPRester

try:
    with MPRester(key) as mpr:
        doc = mpr.materials.summary.search(material_ids=["mp-149"], fields=["material_id", "formula_pretty", "structure"])
    if doc and doc[0].material_id == "mp-149":
        print(f"OK: authenticated, fetched {doc[0].material_id} ({doc[0].formula_pretty})")
    else:
        print("FAIL: query returned no result for mp-149")
        sys.exit(1)
except Exception as e:
    msg = str(e).replace(key, "<redacted>")
    print(f"FAIL: {type(e).__name__}: {msg}")
    sys.exit(1)
