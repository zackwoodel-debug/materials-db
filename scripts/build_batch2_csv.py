#!/usr/bin/env python3
"""
scripts/build_batch2_csv.py
=============================
Batch 2 equivalent of build_oxides_csv.py: PubChem + Materials Project +
periodictable SLD + RI.info n,k enrichment for the fluoride/nitride/sulfide
set in scripts/fluoride_nitride_sulfide_material_list.py (31 materials --
28 original + TiN/VN/EuS folded in once process_condition existed).

Reuses build_oxides_csv.py's fetch_pubchem/fetch_mp/compute_sld/
interpolate_axis/parse_formula_counts directly rather than re-implementing
them -- those are already tested against the 50-oxide run. fetch_mp reads
its override dicts (FORCE_NO_MP, LITERATURE_DENSITY, EXPECTED_SPACEGROUP,
EXPERIMENTAL_DENSITY_OVERRIDE) as module globals, so this script points
those at build_oxides_csv's module namespace before calling in, rather than
forking the function body.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_oxides_csv as base  # noqa: E402
from fluoride_nitride_sulfide_material_list import (  # noqa: E402
    MATERIALS_31, EXPECTED_SPACEGROUP, EXPERIMENTAL_DENSITY_OVERRIDE,
    FORCE_NO_MP, LITERATURE_DENSITY, BULK_APPROXIMATION_FORMULAS,
)
from materials_db.pipeline.process_condition import BULK_ELEMENTAL_APPROXIMATION  # noqa: E402

OUT_CSV = _ROOT / "data" / "batch2_31.csv"

# Point the shared module's override dicts at batch 2's values for the
# duration of this run. fetch_mp/fetch_pubchem read these as globals.
base.EXPECTED_SPACEGROUP = EXPECTED_SPACEGROUP
base.EXPERIMENTAL_DENSITY_OVERRIDE = EXPERIMENTAL_DENSITY_OVERRIDE
base.FORCE_NO_MP = FORCE_NO_MP
base.LITERATURE_DENSITY = LITERATURE_DENSITY
base.REJECTED_ALTERNATE_NOTE = {}
base.PROVENANCE_CONFIRMED_NOTE = {}


def main():
    base.ensure_dirs()

    import os
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
    key = os.environ.get("MP_API_KEY")
    from mp_api.client import MPRester
    mpr_ctx = MPRester(key)
    mpr = mpr_ctx.__enter__()

    rows = []
    try:
        for mat in MATERIALS_31:
            formula = mat["formula"]
            print(f"[{mat['idx']}] {mat['name']} ({formula})", flush=True)
            row = dict(idx=mat["idx"], name=mat["name"], formula=formula, polymorph=mat["polymorph"])
            flags = []

            pc = base.fetch_pubchem(mat)
            flags += pc.pop("flags")
            row.update(pc)

            mpd = base.fetch_mp(mat, mpr)
            flags += mpd.pop("flags")
            citation = mpd.pop("density_citation", None)
            row.update(mpd)
            if citation:
                row["density_citation_doi"] = citation["doi"]
                row["density_citation_title"] = citation["title"]
                row["density_citation_authors"] = citation["authors"]
                row["density_citation_journal"] = citation["journal"]
                row["density_citation_year"] = citation["year"]

            # Structure trusted (see EXPECTED_SPACEGROUP), density number
            # is MP's bulk-crystal DFT relaxation standing in for an
            # unmeasured thin-film sample -- relabel density_source so it
            # reads DENSITY_BULK_APPROXIMATION, not DENSITY_VERIFIED, per
            # docs/batch3_scoping_report.md's density-state gate. Keeps
            # the same numeric density value; only the confidence label
            # changes.
            if formula in BULK_APPROXIMATION_FORMULAS and row.get("density_source") == "MP_DFT":
                row["density_source"] = BULK_ELEMENTAL_APPROXIMATION
                flags.append(f"density relabeled bulk_elemental_approximation: no RI.info page "
                             f"for {formula} states a measured film density; every entry is an "
                             f"explicit thin film (sputtered/ALD/evaporated), so MP's bulk-crystal "
                             f"DFT density is a stand-in, not a verified value for this sample.")

            row["xray_energy_ev"] = base.XRAY_ENERGY_KEV * 1000

            sld = base.compute_sld(formula, row.get("density_g_cm3"))
            flags += sld.pop("flags")
            row.update(sld)

            row["strong_neutron_absorber"] = base.strong_neutron_absorber(formula)

            axes = mat["ri_axes"]
            if axes:
                p0 = axes[0]
                row["ri_shelf"] = p0["data_path"].split("/")[0]
                row["ri_book"] = p0["data_path"].split("/")[1]
                row["ri_page_primary"] = p0["page"]
                row["axis_primary"] = p0["axis"]
                row["process_condition_primary"] = p0.get("process_condition")
                interp = base.interpolate_axis(p0["data_path"])
                flags += [f"[{p0['page']}] {f}" for f in interp.pop("flags")]
                row["n_633"], row["k_633"] = interp["n_633"], interp["k_633"]

                for extra_i, p in enumerate(axes[1:], start=2):
                    interp2 = base.interpolate_axis(p["data_path"])
                    flags += [f"[{p['page']}] {f}" for f in interp2.pop("flags")]
                    row[f"axis_{extra_i}"] = p["axis"]
                    row[f"n_633_axis{extra_i}"] = interp2["n_633"]
                    row[f"k_633_axis{extra_i}"] = interp2["k_633"]
                    row[f"ri_page_axis{extra_i}"] = p["page"]
                    row[f"process_condition_axis{extra_i}"] = p.get("process_condition")

            if formula == "As2S3":
                flags.append("RI.info default dataset is amorphous/glass")

            row["flags"] = base.FLAG_JOIN.join(flags)
            rows.append(row)
    finally:
        mpr_ctx.__exit__(None, None, None)

    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV} ({len(df)} rows, {len(df.columns)} columns)")


if __name__ == "__main__":
    main()
