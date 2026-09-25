#!/usr/bin/env python3
"""
scripts/build_inorganic3_csv.py
================================
Builds data/inorganic3.csv (oxides_50.csv column template + materialclass + selection_key) and data/inorganic3_gaps.csv from
data/step1_selections_inorganic3.json (run match_ri_info_inorganic3.py first). PubChem, Materials Project and periodictable
enrichment reuse build_oxides_csv.py; MP_API_KEY comes from .env and is never printed or written.

Density rules (nothing is inferred):
  1. a density STATED on the selected RI.info page (COMMENTS "Density: x g/cm3") wins, cited to that paper (physical row = literature);
  2. else Materials Project's calculated density, ONLY if the lowest-energy entry is within 25 meV/atom of the hull AND exactly one entry
     lies within 5 meV of it (MP_DFT = calculated, never measured); every such pick is flagged "polymorph not verified against the sample";
  3. film samples / stated sub-stoichiometry get the bulk_elemental_approximation label (an MP bulk value standing in for a film);
  4. otherwise density and SLD stay NULL and the candidates are listed in `flags` as evidence.
SiC has several phases under ONE material (one InChIKey): no MP density is chosen for it; only the source-stated film density is used.
"""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_oxides_csv as base  # noqa: E402
from inorganic3_material_list import CANDIDATES, OUT_OF_FAMILY  # noqa: E402
from load_family_db import parse_ri_references  # noqa: E402
from materials_db.pipeline.process_condition import BULK_ELEMENTAL_APPROXIMATION  # noqa: E402

DATA = _ROOT / "data"
PUBCHEM_NAMES = {"CaMgCO32": "Dolomite", "Bi4Ge3O12": "Bismuth germanate", "Bi12SiO20": "Bismuth silicon oxide",
                 "ScAlMgO4": "Magnesium aluminate scandium oxide", "Yb2O3": "Ytterbium oxide", "BiFeO3": "Bismuth ferrite"}
HULL_WINDOW_EV = 0.005   # entries this close to the lowest one count as competing polymorphs
MAX_HULL_EV = 0.025      # the chosen entry must itself be this close to the hull (else it is not a supported pick)
RI_DATA = _ROOT / "refractiveindex_db" / "database" / "data"


def mp_query(mpr, formula):
    counts = base.parse_formula_counts(formula)
    flat = "".join(f"{el}{int(n)}" for el, n in sorted(counts.items()))
    docs = mpr.materials.summary.search(formula=flat, fields=["material_id", "symmetry", "energy_above_hull", "density", "theoretical", "nsites"])
    return sorted(docs, key=lambda d: d.energy_above_hull)


def evidence(docs, k=6):
    return "; ".join(f"{d.material_id} {d.symmetry.symbol} (#{d.symmetry.number}) hull={d.energy_above_hull:.4f}eV rho={d.density:.3f} nsites={d.nsites}"
                     + (" theoretical" if d.theoretical else "") for d in docs[:k])


def main():
    import dotenv
    from mp_api.client import MPRester
    base.ensure_dirs()
    dotenv.load_dotenv(_ROOT / ".env")
    sel = json.loads((DATA / "step1_selections_inorganic3.json").read_text())
    matches = {c["key"]: c for c in json.loads((DATA / "inorganic3_ri_matches.json").read_text())["candidates"]}
    rows, gaps = [], []
    with MPRester(os.environ["MP_API_KEY"]) as mpr:
        for i, c in enumerate(CANDIDATES, start=1):
            key, flags = c["key"], []
            axes = sel[key]["axes"]
            ds = {d["page"]: d for d in matches[key]["datasets"]}
            row = dict(idx=i, name=c["name"], formula=c["formula"], polymorph=None, materialclass=c["materialclass"], selection_key=key)
            pc = base.fetch_pubchem(dict(idx=i, name=c["name"], formula=c["formula"], pubchem_name=PUBCHEM_NAMES.get(key, c["name"].split(" (")[0])))
            flags += pc.pop("flags")
            row.update(pc)

            comments = " ".join(ds[a["page"]]["comments"] or "" for a in axes)
            state = []
            if re.search(r"\bfilm\b", comments, re.I):
                state.append("film")
            if key == "VC":
                state.append("sub-stoichiometric VC0.88 (MP entries are VC1.0)")
            stated = re.search(r"Density:\s*([\d.]+)\s*g/cm3", comments)
            try:
                docs = mp_query(mpr, c["formula"])
            except Exception as e:
                docs = []
                base.quarantine("mp", key, f"query failed: {type(e).__name__}: {e}", None)
                flags.append(f"MP query failed ({type(e).__name__}); quarantined")
            if docs:
                flags.append("MP candidates (evidence): " + evidence(docs))
            near = [d for d in docs if d.energy_above_hull <= docs[0].energy_above_hull + HULL_WINDOW_EV] if docs else []

            if stated:  # 1. density stated by the source page
                page = next(a["page"] for a in axes if re.search(r"Density:", ds[a["page"]]["comments"] or ""))
                ref = parse_ri_references(ds[page]["data_path"])
                row.update(density_g_cm3=float(stated.group(1)), density_source="literature (density stated on the RI.info page)",
                           density_citation_doi=ref["doi"], density_citation_title=ref["title"], density_citation_authors=ref["authors"],
                           density_citation_year=ref["year"])
                if key == "SiC":
                    row["polymorph"] = "thin film"
                flags.append(f"density {stated.group(1)} g/cm3 is STATED by the selected RI.info page ({'film' if 'film' in state else 'sample'}); not an MP value")
            elif key == "SiC":
                flags.append("SiC: several phases under one material; no MP density chosen")
            elif len(near) == 1 and near[0].energy_above_hull <= MAX_HULL_EV:  # 2. exactly one MP entry, and it is near the hull
                d = near[0]
                row.update(mp_id=str(d.material_id), mp_space_group=f"{d.symmetry.symbol} (#{d.symmetry.number})",
                           mp_energy_above_hull_ev=float(d.energy_above_hull), density_g_cm3=float(d.density),
                           density_source=BULK_ELEMENTAL_APPROXIMATION if state else "MP_DFT")
                flags.append(f"MP entry = the only one within 5 meV of the lowest, and it is {d.energy_above_hull * 1000:.1f} meV/atom above the hull: "
                             "calculated (DFT) density; polymorph NOT verified against the sample")
                if state:
                    flags.append(f"density relabeled bulk approximation: sample is {', '.join(state)}, MP value is a bulk stand-in")
            else:                 # 4. ambiguous or absent
                if not docs:
                    why = "no MP entry"
                elif len(near) > 1:
                    why = f"{len(near)} MP entries within 5 meV of the lowest (need a polymorph decision)"
                else:
                    why = (f"the lowest MP entry is {near[0].energy_above_hull * 1000:.0f} meV/atom above the hull"
                           + (" and theoretical" if near[0].theoretical else "") + " (not a supported pick)")
                flags.append("density/SLD left NULL: " + why)

            row["xray_energy_ev"] = base.XRAY_ENERGY_KEV * 1000
            sld = base.compute_sld(c["formula"], row.get("density_g_cm3"))
            flags += sld.pop("flags")
            row.update(sld)
            row["strong_neutron_absorber"] = base.strong_neutron_absorber(c["formula"])

            first = axes[0]
            row.update(ri_shelf="main", ri_book=c["book"], ri_page_primary=first["page"], axis_primary=first["axis"])
            for j, a in enumerate(axes[:3], start=1):
                interp = base.interpolate_axis(a["data_path"])
                flags += [f"[{a['page']}] {f}" for f in interp.pop("flags")]
                if j == 1:
                    row["n_633"], row["k_633"] = interp["n_633"], interp["k_633"]
                    row["ri_wl_min_nm"], row["ri_wl_max_nm"] = interp["wl_min_nm"], interp["wl_max_nm"]
                else:
                    row.update({f"axis_{j}": a["axis"], f"n_633_axis{j}": interp["n_633"], f"k_633_axis{j}": interp["k_633"], f"ri_page_axis{j}": a["page"]})
            if len(axes) > 3:
                flags.append(f"{len(axes)} datasets; n_633 columns cover the first three only (the DB holds all {len(axes)})")
            if state:
                flags.append("sample state stated by the source: " + ", ".join(state))
            if c["note"]:
                flags.append(c["note"])
            row["flags"] = base.FLAG_JOIN.join(flags)
            rows.append(row)
            if row.get("density_g_cm3") is None:
                gaps.append(dict(key=key, name=c["name"], gap_kind="density", reason="no stated density and no supported single MP entry (see flags)", evidence=evidence(docs, 3) if docs else None))
    template = list(pd.read_csv(DATA / "oxides_50.csv", nrows=0).columns)
    df = pd.DataFrame(rows)
    df = df.reindex(columns=template + [c for c in df.columns if c not in template])
    df.to_csv(DATA / "inorganic3.csv", index=False)
    for k, why in OUT_OF_FAMILY.items():
        gaps.append(dict(key=k, name=k, gap_kind="out_of_family", reason=why, evidence=None))
    pd.DataFrame(gaps).to_csv(DATA / "inorganic3_gaps.csv", index=False)
    print(f"Wrote inorganic3.csv: {len(df)} rows x {len(df.columns)} cols;  inorganic3_gaps.csv: {len(gaps)} rows")


if __name__ == "__main__":
    main()
