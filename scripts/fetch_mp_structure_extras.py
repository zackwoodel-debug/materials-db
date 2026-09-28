#!/usr/bin/env python3
"""
scripts/fetch_mp_structure_extras.py
====================================
Local-structure and elastic descriptors (descriptors v2) for every Materials Project entry already cached in
data/descriptors/mp_structural.json (the family builds chose them; this script never picks an entry). Cached in
data/descriptors/mp_structure_extras.json with each entry's primitive structure, so scripts/build_release.py runs offline and
the tests can recompute every derived number from the structure.

Per entry (all DFT / geometry, never measured; Materials Project, CC BY 4.0):
  coordination        CrystalNN (pymatgen) coordination number per site: site-averaged mean, min, max
  bond_length         CrystalNN nearest-neighbour distances (angstrom): mean over all site-neighbour pairs, min
  packing_fraction    sum of atomic-radius spheres (pymatgen Element.atomic_radius, empirical) / cell volume
  elastic             bulk and shear modulus (Voigt-Reuss-Hill, GPa), universal anisotropy, Poisson ratio, where MP has
                      an elastic tensor for the entry (not all entries have one)
Drift check: the structure's volume per atom must equal mp_structural.json's (same entry, maybe a newer MP database).

    python3 scripts/fetch_mp_structure_extras.py      # needs MP_API_KEY in .env (never printed or written)
"""
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
MP_CACHE = _ROOT / "data" / "descriptors" / "mp_structural.json"
OUT = _ROOT / "data" / "descriptors" / "mp_structure_extras.json"


def local_environment(structure):
    """CrystalNN coordination numbers and nearest-neighbour distances, and the atomic-radius packing fraction."""
    from pymatgen.analysis.local_env import CrystalNN
    cnn = CrystalNN()
    cns, dists = [], []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i in range(len(structure)):
            nn = cnn.get_nn_info(structure, i)
            cns.append(len(nn))
            dists += [structure[i].distance(n["site"]) for n in nn]
        radii = [site.specie.atomic_radius for site in structure]
    out = dict(coordination_number_mean=round(float(np.mean(cns)), 6), coordination_number_min=int(min(cns)),
               coordination_number_max=int(max(cns)), coordination_method="CrystalNN (pymatgen), site-averaged")
    if dists:
        out.update(bond_length_mean_angstrom=round(float(np.mean(dists)), 6), bond_length_min_angstrom=round(float(min(dists)), 6))
    if all(r is not None for r in radii):
        out["packing_fraction"] = round(float(sum(4 / 3 * np.pi * float(r) ** 3 for r in radii) / structure.volume), 6)
        out["packing_fraction_basis"] = "spheres of pymatgen's empirical atomic radius per site / cell volume"
    return out


def elastic(doc):
    def vrh(v):
        if v is None:
            return None
        v = v if isinstance(v, dict) else getattr(v, "model_dump", lambda: None)() or {}
        x = v.get("vrh")
        return None if x is None else round(float(x), 4)
    k, g = vrh(getattr(doc, "bulk_modulus", None)), vrh(getattr(doc, "shear_modulus", None))
    if k is None and g is None:
        return None
    out = dict(bulk_modulus_vrh_gpa=k, shear_modulus_vrh_gpa=g)
    for f, key in (("universal_anisotropy", "universal_anisotropy"), ("homogeneous_poisson", "poisson_ratio")):
        v = getattr(doc, f, None)
        out[key] = None if v is None else round(float(v), 6)
    return out


def main():
    import dotenv
    from mp_api.client import MPRester
    dotenv.load_dotenv(_ROOT / ".env")
    base = json.loads(MP_CACHE.read_text())
    ids = sorted(base["entries"])
    with MPRester(os.environ["MP_API_KEY"]) as mpr:
        version = getattr(mpr, "db_version", None) or mpr.get_database_version()
        docs = mpr.materials.summary.search(material_ids=ids, all_fields=False,
                                            fields=["material_id", "structure", "density_atomic", "bulk_modulus", "shear_modulus",
                                                    "universal_anisotropy", "homogeneous_poisson"])
    entries, drift = {}, []
    for d in docs:
        mid = str(d.material_id)
        s = d.structure
        vpa = s.volume / len(s)
        cached = base["entries"][mid]["volume_per_atom_angstrom3"]
        if cached and abs(vpa / cached - 1) > 1e-3:
            drift.append(dict(mp_id=mid, cached=cached, now=round(vpa, 6)))
        e = dict(local_environment(s), volume_per_atom_angstrom3=round(vpa, 6))
        el = elastic(d)
        e["elastic"] = el if el else dict(unavailable="no elastic tensor in the Materials Project for this entry")
        e["structure"] = s.as_dict()
        entries[mid] = e
    missing = sorted(set(ids) - set(entries))
    OUT.write_text(json.dumps(dict(
        source="Materials Project (materials.summary structure and elasticity), CC BY 4.0; DFT-calculated, not measured",
        mp_database_version=version, base_cache_mp_database_version=base["mp_database_version"],
        retrieved_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), requested=len(ids), missing=missing,
        volume_drift_vs_base_cache=drift, entries=dict(sorted(entries.items()))), indent=None, separators=(",", ":")) + "\n")
    with_el = sum("unavailable" not in e["elastic"] for e in entries.values())
    print(f"MP database {version}: {len(entries)}/{len(ids)} entries, {with_el} with elastic moduli, volume drift {len(drift)} "
          f"-> {OUT.relative_to(_ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB); missing: {missing or 'none'}")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
