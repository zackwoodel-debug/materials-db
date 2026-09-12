#!/usr/bin/env python3
"""
scripts/export_all_materials_modalfit.py
===========================================
Full-catalog equivalent of export_all_oxides_modalfit.py: exports every
material across every batch from data/materials_oxide_test.db, asserting
the skip set matches KNOWN_EXCLUSIONS exactly -- same
invariant-not-vibe-check treatment as the oxide batch's 49/50.

Which materials that is is discovered, not hardcoded: globs data/*.csv
for any file with "formula" and "name" columns (the shape every batch's
build_*_csv.py produces), same technique as _lookup_mp_id in
materials_db/export/modalfit.py -- a hardcoded 3-filename list here would
be the exact same failure shape that function had twice (see that
module's _lookup_mp_id docstring): silently missing a batch's materials
because a file was renamed or a new batch's CSV was added without
updating a list in a second place. The expected total is cross-checked
against the live DB's own materials count, not a hardcoded number that
also needs manual updating every batch.
"""

import glob
import json
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit import export_layer, ExportError, KNOWN_EXCLUSIONS  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_oxide_test.db"
OUT_DIR = _ROOT / "data" / "modalfit_export"


def _safe_dirname(name: str) -> str:
    """Filesystem-safe directory name derived from a material's `name`
    (the schema's real UNIQUE identity key -- see materials.name in
    updated_sql_schema.sql), not its formula. Formula cannot be used as
    the export key or directory name: batch 3b's Diamond and Graphite
    genuinely share formula "C" (two distinct, optically unrelated
    materials), the same ambiguity _find_material() (modalfit.py) raises
    ExportError on rather than silently resolving."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def _discover_materials() -> "pd.DataFrame":
    frames = []
    for csv_path in sorted(glob.glob(str(_ROOT / "data" / "*.csv"))):
        df = pd.read_csv(csv_path)
        if "formula" in df.columns and "name" in df.columns:
            frames.append(df[["formula", "name"]])
    if not frames:
        raise RuntimeError(f"No enrichment CSVs with formula/name columns found under {_ROOT / 'data'}")
    materials = pd.concat(frames, ignore_index=True)

    # `name` is the schema's real UNIQUE identity key (materials.name);
    # `formula` is NOT unique by design -- batch 3b's Diamond and Graphite
    # are two distinct materials genuinely sharing formula "C" -- so only
    # a duplicate `name` is a real conflict worth failing loudly over.
    dupes = materials[materials.duplicated("name", keep=False)]
    if not dupes.empty:
        raise AssertionError(
            f"Name(s) appear in more than one batch's enrichment CSV -- a real "
            f"conflict, not expected: {sorted(dupes['name'].unique())}"
        )

    # Case-insensitive collision check on the derived directory name: two
    # DISTINCT names ("Tin" / "Titanium nitride" -> "Titanium_nitride")
    # normally can't collide, but this guards against the case that bit
    # this batch once already (a stale directory from an old naming
    # scheme) recurring under a new guise -- fail loudly instead of
    # silently overwriting one material's export with another's.
    lowered = materials["name"].apply(lambda n: _safe_dirname(n).lower())
    case_dupes = materials[lowered.duplicated(keep=False)]
    if not case_dupes.empty:
        raise AssertionError(
            f"Material name(s) collide case-insensitively once turned into a directory "
            f"name -- would silently overwrite each other's export on a case-insensitive "
            f"filesystem: {sorted(case_dupes['name'].unique())}"
        )
    return materials


def main():
    materials = _discover_materials()

    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    db_count = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    conn.close()
    assert len(materials) == db_count, (
        f"Discovered {len(materials)} materials across data/*.csv enrichment files, but "
        f"the DB has {db_count} materials rows -- these must match exactly. Either a CSV "
        f"is missing/stale, a batch was loaded without its CSV, or a CSV wasn't loaded yet."
    )

    # Wipe and recreate OUT_DIR fresh every run rather than mkdir-if-missing:
    # a stale directory left over from a prior naming scheme (this run
    # switched the export key from `formula` to `name`) can silently
    # collide on a case-insensitive filesystem with a NEW directory this
    # run creates -- exactly what happened once during batch 3b, where a
    # leftover formula-keyed "TiN/" directory collided with this run's
    # name-keyed "Tin/" and got overwritten. A full rebuild each run makes
    # that class of collision structurally impossible, not just unlikely.
    import shutil
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for _, row in materials.iterrows():
        formula = row["formula"]
        name = row["name"]
        dirname = _safe_dirname(name)
        mat_dir = OUT_DIR / dirname
        try:
            # Look up by `name`, not `formula`: name is the schema's real
            # UNIQUE key, and passing a formula shared by multiple
            # materials (batch 3b's "C") would hit _find_material's
            # ambiguity ExportError for every such material, not just the
            # ones actually ambiguous.
            layer = export_layer(str(DB_PATH), name, nk_csv_dir=mat_dir, label=name)
            layer_path = mat_dir / f"{dirname}_layer.json"
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
