#!/usr/bin/env python3
"""
scripts/export_all_materials_modalfit.py
===========================================
Full-catalog equivalent of export_all_oxides_modalfit.py: exports every
material across all three batches (50 oxides + 31 fluoride/nitride/sulfide
-- 28 original + TiN/VN/EuS folded in once process_condition existed + 3
pure-element triage materials) from data/materials_oxide_test.db,
asserting the skip set matches KNOWN_EXCLUSIONS exactly -- same
invariant-not-vibe-check treatment as the oxide batch's 49/50, extended to
82/84.
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
    oxides = pd.read_csv(_ROOT / "data" / "oxides_50.csv")[["formula", "name"]]
    batch2 = pd.read_csv(_ROOT / "data" / "batch2_31.csv")[["formula", "name"]]
    elements = pd.read_csv(_ROOT / "data" / "pure_element_triage.csv")[["formula", "name"]]
    materials = pd.concat([oxides, batch2, elements], ignore_index=True)

    assert len(materials) == 84, (
        f"Expected 84 materials (50 oxides + 31 batch 2 + 3 pure-element triage), got {len(materials)}"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for _, row in materials.iterrows():
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
    report_path = OUT_DIR / "export_report_all.csv"
    report.to_csv(report_path, index=False)

    n_ok = (report["status"] == "OK").sum()
    n_skip = (report["status"] == "SKIPPED").sum()
    print(f"Exported {n_ok}/{len(materials)} materials, {n_skip} skipped.")
    print(f"Report: {report_path}")
    if n_skip:
        print("\nSkipped:")
        for _, r in report[report["status"] == "SKIPPED"].iterrows():
            print(f"  {r['formula']}: {r['error']}")

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
            f"{newly_succeeding}. If their underlying gap was genuinely fixed, update "
            f"KNOWN_EXCLUSIONS in materials_db/export/modalfit.py to reflect it -- don't "
            f"let this pass silently."
        )

    expected_ok = len(materials) - len(KNOWN_EXCLUSIONS)
    assert n_ok == expected_ok, (
        f"Expected exactly {expected_ok}/{len(materials)} successful exports "
        f"({len(materials)} materials minus {len(KNOWN_EXCLUSIONS)} known exclusions), got {n_ok}."
    )
    print(f"\nAsserted OK: {n_ok}/{len(materials)} exported, "
          f"skip set matches KNOWN_EXCLUSIONS exactly ({sorted(expected_skips)}).")


if __name__ == "__main__":
    main()
