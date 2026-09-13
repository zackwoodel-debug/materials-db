#!/usr/bin/env python3
"""
scripts/export_all_oxides_modalfit.py
=======================================
Bulk-export all 50 oxide materials from data/materials_oxide_test.db as
ModalFit layer JSON + sidecar n,k CSV pairs (a reusable layer library, not
yet assembled into a specific stack -- that's Step 3's demo).

Each material has exactly one polymorph in physical_properties (confirmed
in Step 2 CHECKPOINT work), so no dataset_label needs to be specified here
-- export_layer()'s own disambiguation logic only fires when there IS an
ambiguity, which none of these 50 currently have.

thickness/roughness are intentionally left unset (None) -- these are
building-block layers, not a specific stack; a caller assembling a real
stack (Step 3) supplies those.
"""

import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit import export_layer, ExportError, KNOWN_EXCLUSIONS  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_oxide_test.db"
OUT_DIR = _ROOT / "data" / "modalfit_export"


def main():
    oxides = pd.read_csv(_ROOT / "data" / "oxides_50.csv")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for _, row in oxides.iterrows():
        formula = row["formula"]
        name = row["name"]
        mat_dir = OUT_DIR / formula.replace("(", "").replace(")", "")
        try:
            layer = export_layer(str(DB_PATH), formula, nk_csv_dir=mat_dir, label=formula)
            layer_path = mat_dir / f"{formula}_layer.json"
            mat_dir.mkdir(parents=True, exist_ok=True)
            layer_path.write_text(json.dumps(layer, indent=2))
            results.append(dict(formula=formula, name=name, status="OK",
                                 dataset_label=layer["materials_db"]["dataset_label"],
                                 optical_dataset_label=layer["materials_db"]["optical_dataset_label"],
                                 xray_sld_real=layer["xray"]["sld_real"]["value"],
                                 path=str(layer_path), error=None))
        except ExportError as e:
            results.append(dict(formula=formula, name=name, status="SKIPPED",
                                 dataset_label=None, optical_dataset_label=None,
                                 xray_sld_real=None, path=None, error=str(e)))

    report = pd.DataFrame(results)
    report_path = OUT_DIR / "export_report.csv"
    report.to_csv(report_path, index=False)

    n_ok = (report["status"] == "OK").sum()
    n_skip = (report["status"] == "SKIPPED").sum()
    print(f"Exported {n_ok}/{len(oxides)} materials, {n_skip} skipped.")
    print(f"Report: {report_path}")
    if n_skip:
        print("\nSkipped:")
        for _, r in report[report["status"] == "SKIPPED"].iterrows():
            print(f"  {r['formula']}: {r['error']}")

    # 49/50 is an ASSERTED expected result, not "looks about right" -- an
    # unexpected skip (regression) or an unexpected success (this material's
    # gap got independently fixed and KNOWN_EXCLUSIONS is now stale) both
    # fail loudly instead of silently changing what "N/50" means run to run.
    actual_skips = set(report[report["status"] == "SKIPPED"]["formula"])
    expected_skips = set(KNOWN_EXCLUSIONS)

    unexpected_skips = actual_skips - expected_skips
    if unexpected_skips:
        raise AssertionError(
            f"Export failed for material(s) not in KNOWN_EXCLUSIONS: {unexpected_skips}. "
            f"This is a regression, not an expected exclusion -- investigate before proceeding."
        )

    newly_succeeding = expected_skips - actual_skips
    if newly_succeeding:
        raise AssertionError(
            f"Material(s) previously in KNOWN_EXCLUSIONS now exported successfully: "
            f"{newly_succeeding}. If their underlying gap (e.g. a missing density) was "
            f"genuinely fixed, update KNOWN_EXCLUSIONS in materials_db/export/modalfit.py "
            f"to reflect it -- don't let this pass silently."
        )

    expected_ok = len(oxides) - len(KNOWN_EXCLUSIONS)
    assert n_ok == expected_ok, (
        f"Expected exactly {expected_ok}/{len(oxides)} successful exports "
        f"({len(oxides)} materials minus {len(KNOWN_EXCLUSIONS)} known exclusions), got {n_ok}."
    )
    print(f"\nAsserted OK: {n_ok}/{len(oxides)} exported, "
          f"skip set matches KNOWN_EXCLUSIONS exactly ({sorted(expected_skips)}).")


if __name__ == "__main__":
    main()
