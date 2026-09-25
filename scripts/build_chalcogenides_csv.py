#!/usr/bin/env python3
"""
scripts/build_chalcogenides_csv.py
===================================
Builds data/chalcogenides.csv (oxides_50.csv column template + materialclass + selection_key) and data/chalcogenide_gaps.csv from
data/step1_selections_chalcogenides.json (run match_ri_info_chalcogenides.py first). PubChem, Materials Project and periodictable enrichment
reuse build_oxides_csv.py; MP_API_KEY comes from .env and is never printed or written.

Density rules (nothing is inferred):
  1. a density STATED on the selected RI.info page wins, cited to that paper;
  2. materials with an entry in chalcogenide_material_list.AMBIENT_STRUCTURE: the MP entry of that space group (exactly one within 5 meV of the
     lowest of them), MP_DFT = calculated, never measured; the lowest-energy MP entry is often another phase, so it is never used blindly;
  3. otherwise ONE non-theoretical MP entry within 5 meV of the lowest such entry and <= 25 meV above the hull, flagged "polymorph NOT verified";
  4. film samples (As2Se3) get the bulk_elemental_approximation label; ambiguity or absence leaves density and SLD NULL, with the candidates in `flags`.
Multi-paper materials load every paper as its own dataset; n_633 columns are the primary paper's axes, other papers' values are flags.
n_633 of formula pages is evaluated exactly (not read off the 500-point sampled grid).
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
from chalcogenide_material_list import AMBIENT_STRUCTURE, CANDIDATES, DEFERRED, EXCLUDED_PAGES, OUT_OF_FAMILY  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from load_family_db import parse_ri_references  # noqa: E402
from materials_db.pipeline.process_condition import BULK_ELEMENTAL_APPROXIMATION  # noqa: E402

DATA = _ROOT / "data"
PUBCHEM_NAMES = {"Ag3AsS3": "Silver thioarsenate", "AgGaS2": "Silver gallium sulfide", "AgGaSe2": "Silver gallium selenide",
                 "CuGaS2": "Copper gallium sulfide", "PbSe": "Lead selenide", "ZnSe": "Zinc selenide", "CdSe": "Cadmium selenide",
                 "SnSe": "Tin selenide", "GaSe": "Gallium selenide", "As2Se3": "Arsenic selenide"}
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


def exact_formula_n633(data_path, sampled):
    """n at 633 nm evaluated from the dispersion formula itself. base.interpolate_axis interpolates the 500-point sampled grid, which is up to
    3e-3 off for wide-range fits (TlBr Palik 0.57-39 um). Tabulated pages keep the interpolated value (their points ARE the data)."""
    import numpy as np
    import yaml
    for b in yaml.safe_load(open(RI_DATA / data_path))["DATA"]:
        if b["type"].startswith("formula"):
            lo, hi = (float(x) for x in b["wavelength_range"].split())
            if lo <= 0.633 <= hi:
                return float(fod.eval_formula(b, np.array([0.633]))[0][0])
    return sampled


def main():
    import dotenv
    from mp_api.client import MPRester
    base.ensure_dirs()
    dotenv.load_dotenv(_ROOT / ".env")
    sel = json.loads((DATA / "step1_selections_chalcogenides.json").read_text())
    matches = {c["key"]: c for c in json.loads((DATA / "chalcogenide_ri_matches.json").read_text())["candidates"]}
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
            for a_ in axes:  # RI.info also states the sample form in the page title ("400-nm film")
                if re.search(r"\bfilm\b", ds[a_["page"]]["title"], re.I) and "film" not in state:
                    state.append("film")
            stated = re.search(r"Density:\s*([\d.]+)\s*g/cm3", comments)
            try:
                docs = mp_query(mpr, c["formula"])
            except Exception as e:
                docs = []
                base.quarantine("mp", key, f"query failed: {type(e).__name__}: {e}", None)
                flags.append(f"MP query failed ({type(e).__name__}); quarantined")
            if docs:
                flags.append("MP candidates (evidence): " + evidence(docs))

            if stated:  # 1. density stated by the source page
                page = next(a["page"] for a in axes if re.search(r"Density:", ds[a["page"]]["comments"] or ""))
                ref = parse_ri_references(ds[page]["data_path"])
                row.update(density_g_cm3=float(stated.group(1)), density_source="literature (density stated on the RI.info page)",
                           density_citation_doi=ref["doi"], density_citation_title=ref["title"], density_citation_authors=ref["authors"],
                           density_citation_year=ref["year"])
                flags.append(f"density {stated.group(1)} g/cm3 is STATED by the selected RI.info page ({'film' if 'film' in state else 'sample'}); not an MP value")
            elif key in AMBIENT_STRUCTURE:  # 2. MP entry of the AMBIENT structure (chalcogenide_material_list.AMBIENT_STRUCTURE)
                sname, sg_num, sg_sym = AMBIENT_STRUCTURE[key]
                same = [d for d in docs if d.symmetry.number == sg_num]
                near_sg = [d for d in same if d.energy_above_hull <= same[0].energy_above_hull + HULL_WINDOW_EV] if same else []
                if len(near_sg) == 1:
                    d = near_sg[0]
                    row.update(mp_id=str(d.material_id), mp_space_group=f"{d.symmetry.symbol} (#{d.symmetry.number})",
                               mp_energy_above_hull_ev=float(d.energy_above_hull), density_g_cm3=float(d.density),
                               density_source=BULK_ELEMENTAL_APPROXIMATION if state else "MP_DFT")
                    flags.append(f"density = MP DFT (calculated, not measured) for the ambient structure {sname} ({sg_sym}), {d.material_id}, "
                                 f"{d.energy_above_hull * 1000:.1f} meV/atom above the hull; the ambient structure is standard crystallography, "
                                 "not stated on the RI.info page")
                    if key == "CdSe":  # the source pages themselves say "Hexagonal CdSe": the physical row shares that stated label
                        row["polymorph"] = "hexagonal"
                    if d is not docs[0]:
                        flags.append(f"lowest-energy MP entry is a different phase ({docs[0].material_id} {docs[0].symmetry.symbol}); not used")
                else:
                    why = (f"no MP entry with the ambient space group {sg_sym} (#{sg_num})" if not same
                           else f"{len(near_sg)} MP entries with {sg_sym} within 5 meV of each other (need a polymorph decision)")
                    flags.append("density/SLD left NULL: " + why)
            else:  # 3. no ambient structure on record: one NON-theoretical entry within 5 meV of the lowest such entry and <= 25 meV above the hull
                exp = [d for d in docs if not d.theoretical]
                near = [d for d in exp if d.energy_above_hull <= exp[0].energy_above_hull + HULL_WINDOW_EV] if exp else []
                if len(near) == 1 and near[0].energy_above_hull <= MAX_HULL_EV:
                    d = near[0]
                    row.update(mp_id=str(d.material_id), mp_space_group=f"{d.symmetry.symbol} (#{d.symmetry.number})",
                               mp_energy_above_hull_ev=float(d.energy_above_hull), density_g_cm3=float(d.density),
                               density_source=BULK_ELEMENTAL_APPROXIMATION if state else "MP_DFT")
                    flags.append(f"MP entry = the only non-theoretical one within 5 meV of the lowest, {d.energy_above_hull * 1000:.1f} meV/atom above the hull: "
                                 "calculated (DFT) density; polymorph NOT verified against the sample")
                    if state:
                        flags.append(f"density relabeled bulk approximation: sample is {', '.join(state)}, MP value is a bulk (crystalline) stand-in")
                else:
                    why = ("no non-theoretical MP entry" if not exp else
                           f"{len(near)} non-theoretical MP entries within 5 meV of the lowest (need a polymorph decision)" if len(near) > 1 else
                           f"the lowest non-theoretical MP entry is {near[0].energy_above_hull * 1000:.0f} meV/atom above the hull (not a supported pick)")
                    flags.append("density/SLD left NULL: " + why)

            row["xray_energy_ev"] = base.XRAY_ENERGY_KEV * 1000
            sld = base.compute_sld(c["formula"], row.get("density_g_cm3"))
            flags += sld.pop("flags")
            row.update(sld)
            row["strong_neutron_absorber"] = base.strong_neutron_absorber(c["formula"])

            first = axes[0]
            row.update(ri_shelf="main", ri_book=c["book"], ri_page_primary=first["page"], axis_primary=first["axis"])
            paper = lambda ax: (ax["phase"], ax.get("tag"))
            primary_paper = [a for a in axes if paper(a) == paper(first)]
            other = [a for a in axes if paper(a) != paper(first)]
            for j, a in enumerate(primary_paper[:3], start=1):
                interp = base.interpolate_axis(a["data_path"])
                flags += [f"[{a['page']}] {f}" for f in interp.pop("flags")]
                interp["n_633"] = exact_formula_n633(a["data_path"], interp["n_633"])
                if j == 1:
                    row["n_633"], row["k_633"] = interp["n_633"], interp["k_633"]
                    row["ri_wl_min_nm"], row["ri_wl_max_nm"] = interp["wl_min_nm"], interp["wl_max_nm"]
                else:
                    row.update({f"axis_{j}": a["axis"], f"n_633_axis{j}": interp["n_633"], f"k_633_axis{j}": interp["k_633"], f"ri_page_axis{j}": a["page"]})
            if len(primary_paper) > 3:
                flags.append(f"primary paper has {len(primary_paper)} datasets; n_633 columns cover the first three only (the DB holds all)")
            prim_n = {a["axis"]: exact_formula_n633(a["data_path"], base.interpolate_axis(a["data_path"])["n_633"]) for a in primary_paper}
            for a in other:  # a further PAPER: its n(633 nm) is evidence in flags, not an axis column
                interp = base.interpolate_axis(a["data_path"])
                interp.pop("flags")
                n633 = exact_formula_n633(a["data_path"], interp["n_633"])
                flags.append(f"additional source {a['dataset_label']}: n(633 nm)={n633}" + (f", k={interp['k_633']}" if interp["k_633"] is not None else ""))
                ref = prim_n.get(a["axis"])  # compare like with like (same optical axis)
                if n633 is not None and ref and abs(n633 - ref) / ref > 0.02:
                    flags.append(f"SOURCES DISAGREE at 633 nm by {abs(n633 - ref) / ref * 100:.1f}% ({first['dataset_label'].split(' | ')[-2 if first['axis'] else -1]} "
                                 f"{ref:.4f} vs {a['dataset_label']} {n633:.4f}, axis {a['axis'] or 'isotropic'}); both kept, none preferred on quality")
            if other:
                flags.append(f"{len({paper(a) for a in axes})} papers loaded as separate datasets; n_633/k_633 columns are the primary paper "
                             f"({first['dataset_label']}, widest span among those covering 633 nm)")
            if state:
                flags.append("sample state stated by the source: " + ", ".join(state))
            if c["note"]:
                flags.append(c["note"])
            for (k_, page), why in EXCLUDED_PAGES.items():
                if k_ == key:
                    flags.append(f"page {page} NOT loaded: {why}")
            row["flags"] = base.FLAG_JOIN.join(flags)
            rows.append(row)
            if row.get("density_g_cm3") is None:
                gaps.append(dict(key=key, name=c["name"], gap_kind="density", reason="no stated density and no supported single MP entry (see flags)", evidence=evidence(docs, 3) if docs else None))
    template = list(pd.read_csv(DATA / "oxides_50.csv", nrows=0).columns)
    df = pd.DataFrame(rows)
    df = df.reindex(columns=template + [c for c in df.columns if c not in template])
    df.to_csv(DATA / "chalcogenides.csv", index=False)
    for k, why in DEFERRED.items():
        gaps.append(dict(key=k, name=k, gap_kind="deferred_decision", reason=why, evidence=None))
    for (k, page), why in EXCLUDED_PAGES.items():
        gaps.append(dict(key=k, name=f"{k} page {page}", gap_kind="excluded_page", reason=why, evidence=None))
    for k, why in OUT_OF_FAMILY.items():
        gaps.append(dict(key=k, name=k, gap_kind="out_of_family", reason=why, evidence=None))
    pd.DataFrame(gaps).to_csv(DATA / "chalcogenide_gaps.csv", index=False)
    print(f"Wrote chalcogenides.csv: {len(df)} rows x {len(df.columns)} cols;  chalcogenide_gaps.csv: {len(gaps)} rows")


if __name__ == "__main__":
    main()
