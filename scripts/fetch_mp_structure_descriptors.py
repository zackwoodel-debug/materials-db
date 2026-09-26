#!/usr/bin/env python3
"""
scripts/fetch_mp_structure_descriptors.py
==========================================
Fetches crystal-structure descriptors from the Materials Project for every mp_id that a family build CSV already chose
(the density-selection rules made that choice; this script never picks an entry itself) and caches them in
data/descriptors/mp_structural.json, so scripts/build_release.py can run offline and without an API key.

Everything cached here is CALCULATED (DFT) by the Materials Project, CC BY 4.0 (see DATA_LICENSE.md). MP_API_KEY comes
from .env and is never printed or written.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
FAMILY_CSVS = ["oxides_50.csv", "batch2_31.csv", "batch3b_4.csv", "pure_elements_50.csv", "nitrides.csv", "polymers.csv",
               "inorganic3.csv", "halides.csv", "chalcogenides.csv", "semiconductors.csv", "inorganic4.csv"]
OUT = _ROOT / "data" / "descriptors" / "mp_structural.json"
FIELDS = ["material_id", "formula_pretty", "symmetry", "structure", "nsites", "nelements", "volume", "density", "density_atomic",
          "energy_above_hull", "formation_energy_per_atom", "band_gap", "is_gap_direct", "is_metal", "is_magnetic", "ordering",
          "theoretical", "deprecated"]


def chosen_mp_ids():
    ids = set()
    for name in FAMILY_CSVS:
        df = pd.read_csv(_ROOT / "data" / name)
        if "mp_id" in df.columns:
            ids |= {str(x) for x in df["mp_id"].dropna()}
    return sorted(ids)


def _enum(v):
    return None if v is None else getattr(v, "value", str(v))


def _num(v, nd=6):
    """MP leaves some fields unset (e.g. no thermo data for an entry): keep them None, never 0."""
    return None if v is None else round(float(v), nd)


def record(doc):
    """Lattice parameters are for the CONVENTIONAL standard cell (NaCl a = 5.69 A cubic), not MP's stored primitive cell
    (a = 3.95 A, 60 deg), because that is what a reader expects; symprec 0.1 matches MP's own symmetry analysis."""
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    sga = SpacegroupAnalyzer(doc.structure, symprec=0.1)
    conv = sga.get_conventional_standard_structure()
    lat = conv.lattice
    z = conv.composition.get_reduced_composition_and_factor()[1]
    return dict(
        formula_pretty=doc.formula_pretty,
        crystal_system=_enum(doc.symmetry.crystal_system), space_group_symbol=doc.symmetry.symbol,
        space_group_number=int(doc.symmetry.number), point_group=doc.symmetry.point_group,
        space_group_number_recomputed=int(sga.get_space_group_number()),
        lattice_a_angstrom=round(lat.a, 6), lattice_b_angstrom=round(lat.b, 6), lattice_c_angstrom=round(lat.c, 6),
        lattice_alpha_deg=round(lat.alpha, 6), lattice_beta_deg=round(lat.beta, 6), lattice_gamma_deg=round(lat.gamma, 6),
        conventional_cell_volume_angstrom3=round(lat.volume, 6), conventional_cell_sites=len(conv), formula_units_per_conventional_cell=int(z),
        primitive_cell_volume_angstrom3=_num(doc.volume), primitive_cell_sites=int(doc.nsites), n_elements=int(doc.nelements),
        density_g_cm3=_num(doc.density), volume_per_atom_angstrom3=_num(doc.density_atomic),
        energy_above_hull_ev_per_atom=_num(doc.energy_above_hull),
        formation_energy_ev_per_atom=_num(doc.formation_energy_per_atom),
        band_gap_ev=_num(doc.band_gap), band_gap_is_direct=doc.is_gap_direct,
        is_metal=doc.is_metal, is_magnetic=doc.is_magnetic, magnetic_ordering=_enum(doc.ordering),
        theoretical=bool(doc.theoretical), deprecated=bool(doc.deprecated),
    )


def main():
    import dotenv
    from mp_api.client import MPRester
    dotenv.load_dotenv(_ROOT / ".env")
    ids = chosen_mp_ids()
    with MPRester(os.environ["MP_API_KEY"]) as mpr:
        version = getattr(mpr, "db_version", None) or mpr.get_database_version()
        docs = mpr.materials.summary.search(material_ids=ids, fields=FIELDS, all_fields=False)
    entries = {str(d.material_id): record(d) for d in docs}
    missing = sorted(set(ids) - set(entries))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(
        source="Materials Project (materials.summary), CC BY 4.0; values are DFT-calculated, not measured",
        mp_database_version=version, retrieved_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        requested=len(ids), missing=missing, entries=dict(sorted(entries.items()))), indent=1) + "\n")
    print(f"MP database {version}: {len(entries)}/{len(ids)} entries cached -> {OUT.relative_to(_ROOT)}; missing: {missing or 'none'}")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
