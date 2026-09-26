#!/usr/bin/env python3
"""
scripts/fetch_mp_dielectric.py
==============================
Caches Materials Project's DFPT dielectric data (Petousis et al., Sci. Data 4, 160134 (2017); CC BY 4.0) for every MP entry in
data/descriptors/mp_structural.json into data/descriptors/mp_dielectric.json, which build_release.py reads offline.
Values are CALCULATED (DFT perturbation theory), not measured. MP_API_KEY comes from .env and is never written.

    python3 scripts/fetch_mp_dielectric.py
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
STRUCTURAL = _ROOT / "data" / "descriptors" / "mp_structural.json"
OUT = _ROOT / "data" / "descriptors" / "mp_dielectric.json"


def _tensor(t):
    return [[round(float(x), 6) for x in row] for row in t]


def main():
    import dotenv
    from mp_api.client import MPRester
    dotenv.load_dotenv(_ROOT / ".env")
    ids = sorted(json.loads(STRUCTURAL.read_text())["entries"])
    with MPRester(os.environ["MP_API_KEY"]) as mpr:
        version = getattr(mpr, "db_version", None) or mpr.get_database_version()
        docs = mpr.materials.dielectric.search(material_ids=ids)
    entries = {}
    for d in docs:
        total = np.array(d.total, dtype=float)
        entries[str(d.material_id)] = dict(
            e_total=round(float(d.e_total), 6), e_electronic=round(float(d.e_electronic), 6), e_ionic=round(float(d.e_ionic), 6),
            n=round(float(d.n), 6), eigenvalues_total=[round(float(x), 6) for x in sorted(np.linalg.eigvalsh((total + total.T) / 2))],
            total=_tensor(d.total), electronic=_tensor(d.electronic), ionic=_tensor(d.ionic),
            last_updated=d.last_updated.strftime("%Y-%m-%d") if d.last_updated else None)
    OUT.write_text(json.dumps(dict(
        source="Materials Project dielectric (DFPT), CC BY 4.0; Petousis et al., Sci. Data 4, 160134 (2017), doi:10.1038/sdata.2016.134. "
               "Calculated, not measured. e_total / e_electronic are the mean of the tensor's principal values.",
        mp_database_version=version, retrieved_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        requested=len(ids), without_dielectric=sorted(set(ids) - set(entries)), entries=dict(sorted(entries.items()))), indent=1) + "\n")
    print(f"MP database {version}: dielectric data for {len(entries)}/{len(ids)} entries -> {OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
