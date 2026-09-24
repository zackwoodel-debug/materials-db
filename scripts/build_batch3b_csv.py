#!/usr/bin/env python3
"""
scripts/build_batch3b_csv.py
================================
Batch 3b: Carbon (Diamond + Graphite, two materials rows sharing formula
"C"), Tin, Boron -- the 4 materials held back from the main pure-element
pass (scripts/build_pure_element_csv.py) because each combines a polymorph
trap WITH a process-condition/amorphous question at once. See
scripts/pure_element_material_list.py's BATCH 3b section and
docs/batch3_scoping_report.md Part H.

A separate script, not an extension of build_pure_element_csv.py, matching
the established per-phase pattern (build_oxides_csv.py / build_batch2_csv.py
/ build_pure_element_csv.py are each their own script) -- the 50-element
pass is a completed, already-reported-on phase and should not be re-run or
have its CSV regenerated as a side effect of adding these 4.

Iterates the 4 new dict entries in MATERIALS_PURE_ELEMENTS (idx 260-263,
appended after the original 50) directly, rather than importing a separate
list module, since pure_element_material_list.py already scopes them as
"BATCH 3b" additions to the same canonical list.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_oxides_csv as base  # noqa: E402
from pure_element_material_list import (  # noqa: E402
    MATERIALS_PURE_ELEMENTS, EXPECTED_SPACEGROUP, EXPERIMENTAL_DENSITY_OVERRIDE,
    VERIFIED_BULK_SAMPLE_FORMULAS, FORCE_NO_MP_BATCH_3B, LITERATURE_DENSITY_BATCH_3B,
)
from materials_db.pipeline.process_condition import BULK_ELEMENTAL_APPROXIMATION  # noqa: E402

OUT_CSV = _ROOT / "data" / "batch3b_4.csv"

MATERIALS_BATCH_3B = [m for m in MATERIALS_PURE_ELEMENTS if m["idx"] >= 260]
assert len(MATERIALS_BATCH_3B) == 4, f"expected exactly 4 batch-3b materials, found {len(MATERIALS_BATCH_3B)}"

base.EXPECTED_SPACEGROUP = EXPECTED_SPACEGROUP
base.EXPERIMENTAL_DENSITY_OVERRIDE = EXPERIMENTAL_DENSITY_OVERRIDE
base.FORCE_NO_MP = FORCE_NO_MP_BATCH_3B
base.LITERATURE_DENSITY = LITERATURE_DENSITY_BATCH_3B
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
        for mat in MATERIALS_BATCH_3B:
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

            if (formula not in VERIFIED_BULK_SAMPLE_FORMULAS
                    and formula not in EXPERIMENTAL_DENSITY_OVERRIDE
                    and row.get("density_source") == "MP_DFT"):
                row["density_source"] = BULK_ELEMENTAL_APPROXIMATION
                flags.append(f"density relabeled bulk_elemental_approximation: no RI.info page "
                             f"for {mat['name']} states a measured film density, and the default "
                             f"dataset is not confirmed genuinely bulk/single-crystal -- MP's "
                             f"bulk-crystal DFT density is a stand-in, not a verified value.")

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
