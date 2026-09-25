#!/usr/bin/env python3
"""
scripts/build_halides_csv.py
================================
Builds data/halides.csv (oxides_50.csv column template + materialclass + selection_key) and data/halide_gaps.csv from
data/step1_selections_halides.json (run match_ri_info_halide.py first). PubChem, Materials Project and periodictable
enrichment reuse build_oxides_csv.py; MP_API_KEY comes from .env and is never printed or written.

Density rules (nothing is inferred):
  1. a density STATED on the selected RI.info page (COMMENTS "Density: x g/cm3") wins, cited to that paper (physical row = literature);
  2. else Materials Project's calculated density, ONLY if the lowest-energy entry is within 25 meV/atom of the hull AND exactly one entry
     lies within 5 meV of it (MP_DFT = calculated, never measured); every such pick is flagged "polymorph not verified against the sample";
  3. film samples / stated sub-stoichiometry get the bulk_elemental_approximation label (an MP bulk value standing in for a film);
  4. otherwise density and SLD stay NULL and the candidates are listed in `flags` as evidence.
Multi-paper halides (KCl, NaCl, AgBr, CsBr, TlBr, CsI, NaI) load every paper as its own dataset; n_633 columns are the primary's.
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
from halide_material_list import AMBIENT_STRUCTURE, CANDIDATES, OUT_OF_FAMILY  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from load_family_db import parse_ri_references  # noqa: E402
from materials_db.pipeline.process_condition import BULK_ELEMENTAL_APPROXIMATION  # noqa: E402

DATA = _ROOT / "data"
PUBCHEM_NAMES = {"CuCl": "Cuprous chloride", "TlCl": "Thallium chloride", "TlBr": "Thallium bromide", "PbI2": "Lead iodide"}
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
    sel = json.loads((DATA / "step1_selections_halides.json").read_text())
    matches = {c["key"]: c for c in json.loads((DATA / "halide_ri_matches.json").read_text())["candidates"]}
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
            else:  # 2. MP entry of the AMBIENT structure (see halide_material_list.AMBIENT_STRUCTURE); exactly one such entry within 5 meV of the lowest of them
                sname, sg_num, sg_sym = AMBIENT_STRUCTURE[key]
                same = [d for d in docs if d.symmetry.number == sg_num]
                near_sg = [d for d in same if d.energy_above_hull <= same[0].energy_above_hull + HULL_WINDOW_EV] if same else []
                if len(near_sg) == 1:
                    d = near_sg[0]
                    row.update(mp_id=str(d.material_id), mp_space_group=f"{d.symmetry.symbol} (#{d.symmetry.number})",
                               mp_energy_above_hull_ev=float(d.energy_above_hull), density_g_cm3=float(d.density), density_source="MP_DFT")
                    # NOT put in `polymorph`: that column becomes the physical row's dataset_label prefix, and the optical labels carry no polymorph
                    # (RI.info does not state one), so the exporter could not pair density with optical data. The structure is kept in mp_space_group + flags.
                    flags.append(f"density = MP DFT (calculated, not measured) for the ambient structure {sname} ({sg_sym}), {d.material_id} ({d.symmetry.symbol} #{d.symmetry.number}), "
                                 f"{d.energy_above_hull * 1000:.1f} meV/atom above the hull; the ambient structure is standard crystallography, "
                                 "not stated on the RI.info page")
                    if d is not docs[0]:
                        flags.append(f"lowest-energy MP entry is a different phase ({docs[0].material_id} {docs[0].symmetry.symbol}); not used")
                else:
                    why = (f"no MP entry with the ambient space group {sg_sym} (#{sg_num})" if not same
                           else f"{len(near_sg)} MP entries with {sg_sym} within 5 meV of each other (need a polymorph decision)")
                    flags.append("density/SLD left NULL: " + why)
            row["xray_energy_ev"] = base.XRAY_ENERGY_KEV * 1000
            sld = base.compute_sld(c["formula"], row.get("density_g_cm3"))
            flags += sld.pop("flags")
            row.update(sld)
            row["strong_neutron_absorber"] = base.strong_neutron_absorber(c["formula"])

            first = axes[0]
            row.update(ri_shelf="main", ri_book=c["book"], ri_page_primary=first["page"], axis_primary=first["axis"])
            for j, a in enumerate(axes):
                interp = base.interpolate_axis(a["data_path"])
                flags += [f"[{a['page']}] {f}" for f in interp.pop("flags")]
                interp["n_633"] = exact_formula_n633(a["data_path"], interp["n_633"])
                if j == 0:
                    row["n_633"], row["k_633"] = interp["n_633"], interp["k_633"]
                else:  # a further PAPER (cubic halides are isotropic): its n(633 nm) is evidence in flags, not an axis column
                    flags.append(f"additional source {a['dataset_label']}: n(633 nm)={interp['n_633']}"
                                 + (f", k={interp['k_633']}" if interp["k_633"] is not None else ""))
                    if interp["n_633"] is not None and row["n_633"] and abs(interp["n_633"] - row["n_633"]) / row["n_633"] > 0.02:
                        flags.append(f"SOURCES DISAGREE at 633 nm by {abs(interp['n_633'] - row['n_633']) / row['n_633'] * 100:.1f}% "
                                     f"({axes[0]['dataset_label']} {row['n_633']:.4f} vs {a['dataset_label']} {interp['n_633']:.4f}); both kept, none preferred on quality")
            if len(axes) > 1:
                flags.append(f"{len(axes)} sources loaded as separate datasets; n_633/k_633 columns are the primary ({first['dataset_label']}, widest span)")
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
    df.to_csv(DATA / "halides.csv", index=False)
    for k, why in OUT_OF_FAMILY.items():
        gaps.append(dict(key=k, name=k, gap_kind="out_of_family", reason=why, evidence=None))
    pd.DataFrame(gaps).to_csv(DATA / "halide_gaps.csv", index=False)
    print(f"Wrote halides.csv: {len(df)} rows x {len(df.columns)} cols;  halide_gaps.csv: {len(gaps)} rows")


if __name__ == "__main__":
    main()
