#!/usr/bin/env python3
"""
scripts/build_nitrides_csv.py
==============================
Builds data/nitrides.csv (same columns as oxides_50.csv, plus polymorph_hint and materialclass=nitride) and
data/nitride_gaps.csv from data/nitride_ri_matches.json (run match_ri_info_nitrides.py first).

  * candidates already processed in batches 2/3b (AlN, GaN, h-BN, TiN, VN): row carried over VERBATIM from
    data/batch2_31.csv / data/batch3b_4.csv (no API re-hit, no value re-derived).
  * Si3N4: optical = amorphous thin film (user-selected Luke/Philipp); physical = calculated crystalline beta (mp-988,
    on hull), SLDs derived from that density via periodictable. Different phases -- stated in flags and source notes.
  * everything else (no RI catalog page, no in-repo density source; excluded non-stoichiometric SiNx datasets) -> a row in
    nitride_gaps.csv, never in nitrides.csv.
MP_API_KEY comes from .env / the environment and is never printed or written.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_oxides_csv as base  # noqa: E402
from nitride_material_list import CANDIDATES, EXCLUDED_DATASETS, SI3N4_MP_ID, SI3N4_PHASE_NOTE  # noqa: E402

DATA = _ROOT / "data"
OUT_CSV, GAPS_CSV = DATA / "nitrides.csv", DATA / "nitride_gaps.csv"
CARRY_SOURCES = ["batch2_31.csv", "batch3b_4.csv"]


def carried_row(cand):
    for fn in CARRY_SOURCES:
        df = pd.read_csv(DATA / fn)
        hit = df[df["name"] == cand["name"]]
        if len(hit) == 1:
            r = hit.iloc[0].to_dict()
            r["flags"] = base.FLAG_JOIN.join(
                [f for f in [r.get("flags") if pd.notna(r.get("flags")) else None,
                             f"carried over unchanged from data/{fn}; already loaded in materials_oxide_test.db"] if f])
            return r
    raise SystemExit(f"carry-over row for {cand['name']} not found in {CARRY_SOURCES}")


def si3n4_row(cand, match):
    """Si3N4: optical = the two user-selected amorphous-film datasets; physical = calculated crystalline beta (mp-988).
    The two phases differ and the row says so (flags + density source notes). Anything MP can't supply stays NULL."""
    row = dict(name=cand["name"], formula=cand["formula"], polymorph="beta")
    flags = []
    pc = base.fetch_pubchem(dict(idx=0, name=cand["name"], formula=cand["formula"], pubchem_name=cand["pubchem_name"]))
    flags += pc.pop("flags")
    row.update(pc)

    doc = None
    try:
        from dotenv import load_dotenv
        from mp_api.client import MPRester
        load_dotenv(_ROOT / ".env")
        with MPRester(os.environ["MP_API_KEY"]) as mpr:
            docs = mpr.materials.summary.search(formula="Si3N4", fields=["material_id", "symmetry", "energy_above_hull", "density"])
        doc = next((d for d in docs if str(d.material_id) == SI3N4_MP_ID), None)
        if doc is None or doc.energy_above_hull != 0 or doc.symmetry.symbol != "P6_3/m":
            raise ValueError(f"{SI3N4_MP_ID} is not the expected on-hull P6_3/m entry")
        (DATA / "raw_cache" / "mp").mkdir(parents=True, exist_ok=True)
        (DATA / "raw_cache" / "mp" / "Si3N4_mp-988.json").write_text(json.dumps(dict(
            material_id=SI3N4_MP_ID, spacegroup=doc.symmetry.symbol, number=doc.symmetry.number,
            energy_above_hull=doc.energy_above_hull, density=doc.density)))
    except Exception as e:  # quarantined + flagged, never silently skipped; values stay NULL
        doc = None
        base.quarantine("mp", "Si3N4", f"{SI3N4_MP_ID} query failed: {type(e).__name__}: {e}", None)
        flags.append(f"MP evidence query failed ({type(e).__name__}); quarantined")

    density = None
    if doc is not None:
        density = float(doc.density)
        row.update(mp_id=SI3N4_MP_ID, mp_space_group=f"{doc.symmetry.symbol} (#{doc.symmetry.number})",
                   mp_energy_above_hull_ev=float(doc.energy_above_hull), density_g_cm3=density, density_source="MP_DFT",
                   density_citation_title="Materials Project mp-988 (beta-Si3N4): DFT-relaxed density",
                   density_citation_authors="Materials Project Consortium",
                   density_citation_notes=f"Calculated (DFT-derived), not measured. https://materialsproject.org/materials/{SI3N4_MP_ID}. "
                                          + SI3N4_PHASE_NOTE)
        flags.append(f"density = MP {SI3N4_MP_ID} beta-Si3N4 (P6_3/m, on hull), calculated/DFT-derived, not measured")
    flags.append(SI3N4_PHASE_NOTE)
    flags.append("other MP candidates (mp-2245 alpha P31c and 4 higher-energy entries) deliberately ignored this run")

    row["xray_energy_ev"] = base.XRAY_ENERGY_KEV * 1000
    sld = base.compute_sld("Si3N4", density)
    flags += sld.pop("flags")
    row.update(sld)
    row["strong_neutron_absorber"] = base.strong_neutron_absorber("Si3N4")

    sel = json.loads((DATA / "step1_selections_nitrides.json").read_text())["Si3N4"]
    for i, ax in enumerate(sel["axes"], start=1):
        interp = base.interpolate_axis(ax["data_path"])
        flags += [f"[{ax['page']}] {f}" for f in interp.pop("flags")]
        if i == 1:
            row.update(ri_shelf="main", ri_book="Si3N4", ri_page_primary=ax["page"], axis_primary=ax["axis"],
                       n_633=interp["n_633"], k_633=interp["k_633"],
                       ri_wl_min_nm=interp["wl_min_nm"], ri_wl_max_nm=interp["wl_max_nm"])
        else:
            row.update({f"axis_{i}": ax["axis"], f"n_633_axis{i}": interp["n_633"], f"k_633_axis{i}": interp["k_633"],
                        f"ri_page_axis{i}": ax["page"]})
    flags.append(f"optical: amorphous, isotropic; primary {sel['axes'][0]['page']}, secondary {sel['axes'][1]['page']}. {sel['basis']}")
    row["flags"] = base.FLAG_JOIN.join(flags)
    return row


def main():
    base.ensure_dirs()
    matches = {m["selection_key"]: m for m in json.loads((DATA / "nitride_ri_matches.json").read_text())}
    selections = json.loads((DATA / "step1_selections_nitrides.json").read_text())
    rows, gaps = [], []
    for i, c in enumerate(CANDIDATES, start=1):
        m = matches[c["selection_key"]]
        if m["status"] == "MISSING":
            gaps.append(dict(name=c["name"], formula=c["formula"], selection_key=c["selection_key"],
                             polymorph_hint=c["polymorph_hint"], ri_books_searched="|".join(c["ri_aliases"]),
                             ri_match="none in catalog-nk.yml (main/other shelves)",
                             in_repo_density_source="none found (grep of repo CSV/py/json/md/sql + DBs)",
                             reason=m.get("note") or "no RI.info dataset and no in-repo density source; not fabricated"))
            continue
        row = carried_row(c) if m["prior_selection"] else si3n4_row(c, m)
        if m["prior_selection"]:  # batch 2/3b never recorded the range; take it from the carried primary axis's data
            interp = base.interpolate_axis(selections[c["selection_key"]]["axes"][0]["data_path"])
            row.update(ri_wl_min_nm=interp["wl_min_nm"], ri_wl_max_nm=interp["wl_max_nm"])
        row.update(idx=i, polymorph_hint=c["polymorph_hint"], materialclass="nitride", selection_key=c["selection_key"])
        rows.append(row)

    ds_by_key = {k: {d["page"]: d for d in m["datasets"]} for k, m in matches.items()}
    for key, pages in EXCLUDED_DATASETS.items():
        for page, _tag in pages:
            d = ds_by_key[key][page]
            gaps.append(dict(name=f"Non-stoichiometric silicon nitride (SiNx) - {page}", formula="SiNx",
                             selection_key=f"SiNx-{page}", polymorph_hint=None, ri_books_searched="Si3N4",
                             ri_match=d["data_path"], in_repo_density_source="n/a (not loaded)",
                             reason=f"non-stoichiometric SiNx ({d['page_name']}); deliberately NOT loaded, no SiNx material row "
                                    "created this run; follow-up"))

    template = list(pd.read_csv(DATA / "oxides_50.csv", nrows=0).columns)
    extra = [c for c in pd.DataFrame(rows).columns if c not in template]
    df = pd.DataFrame(rows).reindex(columns=template + extra)
    df.to_csv(OUT_CSV, index=False)
    pd.DataFrame(gaps).to_csv(GAPS_CSV, index=False)
    print(f"Wrote {OUT_CSV.name}: {len(df)} rows x {len(df.columns)} cols;  {GAPS_CSV.name}: {len(gaps)} gap rows")


if __name__ == "__main__":
    main()
