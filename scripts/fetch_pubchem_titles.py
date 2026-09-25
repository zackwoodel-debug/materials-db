#!/usr/bin/env python3
"""
scripts/fetch_pubchem_titles.py
===============================
Caches PubChem's record title (its preferred common name) for every PubChem CID in the newest release, in
data/descriptors/pubchem_titles.json, which build_release.py reads offline for material_synonyms. The CIDs themselves were
chosen and checked by each family build; this only records the name PubChem gives them.

    python3 scripts/fetch_pubchem_titles.py [--release release/materials-db-vX.Y.Z]
"""
import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "data" / "descriptors" / "pubchem_titles.json"
URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{}/property/Title/JSON"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--release", type=Path, default=None)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(_ROOT / "scripts"))
    from generate_ml_release_set import latest_release
    db = next(Path(a.release or latest_release()).glob("materials-db-v*.sqlite"))
    cids = sorted({int(c) for (c,) in sqlite3.connect(str(db)).execute("SELECT pubchem_cid FROM materials WHERE pubchem_cid IS NOT NULL")})
    titles = {}
    for i in range(0, len(cids), 100):
        chunk = cids[i:i + 100]
        with urllib.request.urlopen(URL.format(",".join(map(str, chunk))), timeout=60) as r:
            for p in json.load(r)["PropertyTable"]["Properties"]:
                if p.get("Title"):
                    titles[str(p["CID"])] = p["Title"]
        time.sleep(0.3)
    missing = [c for c in cids if str(c) not in titles]
    OUT.write_text(json.dumps(dict(source="PubChem PUG REST compound Title (NCBI; public domain)",
                                   retrieved_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                   requested=len(cids), missing=missing, titles=dict(sorted(titles.items(), key=lambda kv: int(kv[0])))),
                              indent=1, ensure_ascii=False) + "\n")
    print(f"{len(titles)}/{len(cids)} PubChem titles cached -> {OUT.relative_to(_ROOT)}; missing: {missing or 'none'}")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
