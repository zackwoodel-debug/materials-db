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

import argparse
import glob
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit import export_layer, ExportError, KNOWN_EXCLUSIONS  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_oxide_test.db"
OUT_DIR = _ROOT / "data" / "modalfit_export"

# One row per database. A DB is exported with ITS OWN enrichment CSVs only: the CSVs of different families overlap by name
# (nitrides.csv repeats five materials that batch 2 already put in the oxide DB) and each family DB holds only its own materials,
# so globbing every data/*.csv against one DB can never match. Family scratch DBs are built by scripts/load_<family>_db.py.
FAMILIES = {
    "oxide": ("materials_oxide_test.db", ["oxides_50.csv", "batch2_31.csv", "batch3b_4.csv", "pure_elements_50.csv"], "modalfit_export"),
    "nitride": ("materials_nitride_test.db", ["nitrides.csv"], "modalfit_export_nitride"),
    "polymer": ("materials_polymer_test.db", ["polymers.csv"], "modalfit_export_polymer"),
    "inorganic3": ("materials_inorganic3_test.db", ["inorganic3.csv"], "modalfit_export_inorganic3"),
    "halide": ("materials_halide_test.db", ["halides.csv"], "modalfit_export_halide"),
    "chalcogenide": ("materials_chalcogenide_test.db", ["chalcogenides.csv"], "modalfit_export_chalcogenide"),
    "liquid": ("materials_liquid_test.db", ["liquids.csv"], "modalfit_export_liquid"),
}
OWNER_MARKER = ".modalfit_export_owned"  # written into an output dir this script created; only such a dir may be wiped


def _safe_dirname(name: str) -> str:
    """Filesystem-safe directory name derived from a material's `name`
    (the schema's real UNIQUE identity key -- see materials.name in
    updated_sql_schema.sql), not its formula. Formula cannot be used as
    the export key or directory name: batch 3b's Diamond and Graphite
    genuinely share formula "C" (two distinct, optically unrelated
    materials), the same ambiguity _find_material() (modalfit.py) raises
    ExportError on rather than silently resolving."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def _discover_materials(csv_paths=None) -> "pd.DataFrame":
    """csv_paths: the family's CSVs. None globs data/*.csv (legacy behaviour, kept for callers that pass nothing)."""
    frames = []
    for csv_path in (sorted(glob.glob(str(_ROOT / "data" / "*.csv"))) if csv_paths is None else [str(x) for x in csv_paths]):
        df = pd.read_csv(csv_path)
        if "formula" in df.columns and "name" in df.columns:
            frames.append(df[["formula", "name"]])
    if not frames:
        raise RuntimeError(f"No enrichment CSVs with formula/name columns found ({'under ' + str(_ROOT / 'data') if csv_paths is None else csv_paths})")
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


def prepare_out_dir(out_dir: Path) -> None:
    """Create `out_dir` fresh. An existing dir is wiped ONLY if this script created it (marker file present): a rebuild still makes the
    stale-directory collision class impossible, but a folder someone else populated (e.g. a hand-curated data/modalfit_export with
    copies) is refused, never deleted."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        if not (out_dir / OWNER_MARKER).exists():
            if any(out_dir.iterdir()):
                raise SystemExit(f"Refusing to wipe {out_dir}: it is not empty and was not created by this script (no {OWNER_MARKER}). "
                                 f"Pass --out-dir to a new or empty folder.")
        else:
            shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / OWNER_MARKER).write_text("created by scripts/export_all_materials_modalfit.py; safe to wipe on the next run\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--family", choices=sorted(FAMILIES), default="oxide")
    ap.add_argument("--strict", action="store_true", help="non-oxide families: fail on ANY skipped material (default: report them and exit 0)")
    ap.add_argument("--out-dir", type=Path, default=None, help="default: data/modalfit_export[_<family>]")
    a = ap.parse_args(argv)
    db_name, csv_names, out_name = FAMILIES[a.family]
    db_path = _ROOT / "data" / db_name
    out_dir = a.out_dir or (_ROOT / "data" / out_name)
    materials = _discover_materials([_ROOT / "data" / c for c in csv_names])

    import sqlite3
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
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
    prepare_out_dir(out_dir)

    results = []
    for _, row in materials.iterrows():
        formula = row["formula"]
        name = row["name"]
        dirname = _safe_dirname(name)
        mat_dir = out_dir / dirname
        try:
            # Look up by `name`, not `formula`: name is the schema's real
            # UNIQUE key, and passing a formula shared by multiple
            # materials (batch 3b's "C") would hit _find_material's
            # ambiguity ExportError for every such material, not just the
            # ones actually ambiguous.
            layer = export_layer(str(db_path), name, nk_csv_dir=mat_dir, label=name)
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
    report_path = out_dir / "export_report_all.csv"
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
    if a.family != "oxide":
        # KNOWN_EXCLUSIONS is the oxide DB's curated invariant. Other families skip for reasons that are properties of their data (no density
        # row -> no SLD -> no layer; optical/physical phase mismatch such as amorphous Si3N4 film vs crystalline beta density): reported, not asserted.
        print(f"\n{a.family}: {n_ok}/{len(materials)} exported; {n_skip} skipped (reasons in {report_path.name}).")
        if a.strict and n_skip:
            raise SystemExit(f"--strict: {n_skip} material(s) skipped")
        return report
    in_family = set(materials["formula"])
    expected_skips = set(KNOWN_EXCLUSIONS) & in_family  # exclusions that belong to another family's DB cannot be skipped here

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

    expected_ok = len(materials) - len(expected_skips)
    assert n_ok == expected_ok, (
        f"Expected exactly {expected_ok}/{len(materials)} successful exports "
        f"({len(materials)} materials minus {len(expected_skips)} known exclusions), got {n_ok}."
    )
    print(f"\nAsserted OK: {n_ok}/{len(materials)} exported, "
          f"skip set matches KNOWN_EXCLUSIONS exactly ({sorted(expected_skips)}).")


if __name__ == "__main__":
    main()
