"""
bulk.py -- write ModalFit JSON to disk, given a database path and an out path
==============================================================================
exporter.py's export_layer()/export_stack() RETURN dicts (and write the
sidecar n,k CSVs). This module is the thin layer that also writes the JSON
itself, plus the whole-catalog sweep -- i.e. the "point it at a .db and a
directory" entry points.

One deliberate difference from materials-db's own bulk script
(scripts/export_all_materials_modalfit.py), called out because it is a
behavior change and not a port: that script discovers which materials to
export by globbing data/*.csv for the per-batch enrichment files and
asserting the count matches the DB's own materials count. Here the
database IS the source of truth -- `SELECT name, formula FROM materials`
-- because a drop-in cannot assume those CSVs travelled with it. The
resulting material set is identical whenever both are available (that
script asserts as much), and this version also works on a database
standing on its own. Set strict=True to keep the upstream assertion that
the skip set matches KNOWN_EXCLUSIONS exactly.
"""

import csv as _csv
import json
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from .exporter import ExportError, KNOWN_EXCLUSIONS, export_layer, export_stack


def _safe_dirname(name: str) -> str:
    """Filesystem-safe directory name derived from a material's `name`
    (the schema's real UNIQUE identity key), not its formula. Formula
    cannot be used as the export key: Diamond and Graphite genuinely
    share formula "C" -- two distinct, optically unrelated materials, the
    same ambiguity exporter._find_material() raises ExportError on rather
    than silently resolving."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def list_materials(db_path) -> list:
    """Every selectable material in the database: [{material_id, name,
    formula}, ...] ordered by name. `name` is what to pass as a layer's
    "material" -- it is the schema's UNIQUE key, whereas formula is not."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT material_id, name, formula FROM materials ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return [dict(material_id=r[0], name=r[1], formula=r[2]) for r in rows]


def export_stack_json(db_path, out_dir, layers: list, *,
                      ambient="air", substrate: str = "Silicon",
                      substrate_dataset_label: Optional[str] = None,
                      substrate_roughness_a: Optional[float] = None,
                      substrate_roughness_min: Optional[float] = None,
                      substrate_roughness_max: Optional[float] = None,
                      stack_id: Optional[str] = None,
                      sample_id: Optional[str] = None,
                      filename: str = "stack.json") -> Path:
    """Connect to `db_path`, build ambient + `layers` + substrate, and
    write the ModalFit slab-model JSON into `out_dir` alongside the
    sidecar n,k CSVs it references. Returns the JSON's path.

    `layers` is a list of dicts, outermost film first:
        {"material": "TiO2",            # DB name (preferred) or formula
         "dataset_label": "rutile",     # required only for a multi-polymorph material
         "thickness_a": 500.0,          # Angstrom
         "roughness_a": 5.0,            # Angstrom, interface ABOVE this layer
         "thickness_min"/"thickness_max"/"roughness_min"/"roughness_max": fit bounds,
         "label": "..."}                # optional; defaults to formula_polymorph

    The JSON and its CSVs MUST stay in the same directory: each layer's
    optical.params.file is a bare filename resolved relative to the JSON.
    Moving the JSON alone silently breaks every tabulated-n,k layer.

    Raises ExportError rather than emitting a null for a missing density,
    an unresolvable dataset_label, or missing optical data.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stack = export_stack(
        str(db_path), layers,
        ambient=ambient, substrate=substrate,
        substrate_dataset_label=substrate_dataset_label,
        substrate_roughness_a=substrate_roughness_a,
        substrate_roughness_min=substrate_roughness_min,
        substrate_roughness_max=substrate_roughness_max,
        stack_id=stack_id, sample_id=sample_id,
        out_dir=out_dir,
    )

    json_path = out_dir / filename
    json_path.write_text(json.dumps(stack, indent=2))
    return json_path


def export_all_layers(db_path, out_dir, *, strict: bool = False) -> dict:
    """Export EVERY material in `db_path` as its own single-layer ModalFit
    JSON: out_dir/<Material_Name>/<Material_Name>_layer.json, each beside
    its own sidecar n,k CSV. Writes an export_report.csv summarising every
    material's outcome. Returns
    {"n_ok", "n_skipped", "n_total", "out_dir", "report_path", "results"}.

    A material that legitimately cannot be exported (no citable density,
    no optical data) is recorded as SKIPPED with its ExportError message
    rather than failing the run -- see KNOWN_EXCLUSIONS.

    strict=True additionally asserts the skip set matches KNOWN_EXCLUSIONS
    exactly, so that BOTH a new failure (a regression) and a material that
    unexpectedly starts succeeding (its underlying gap got fixed, and
    KNOWN_EXCLUSIONS is now stale) raise instead of passing silently. Use
    it in CI against the materials-db database; leave it off when pointing
    this at a different or partial database, where the expected skip set
    is by definition different.

    out_dir is wiped and recreated each run rather than mkdir-if-missing:
    a stale directory from a prior naming scheme can silently collide on a
    case-insensitive filesystem with a directory this run creates (this
    happened once upstream -- a leftover formula-keyed "TiN/" collided
    with a name-keyed "Tin/" and got overwritten). A full rebuild makes
    that class of collision structurally impossible, not merely unlikely.
    """
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    materials = list_materials(db_path)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for mat in materials:
        name, formula = mat["name"], mat["formula"]
        dirname = _safe_dirname(name)
        mat_dir = out_dir / dirname
        try:
            # Look up by `name`, not `formula`: name is the schema's real
            # UNIQUE key, and passing a formula shared by several materials
            # (e.g. "C") would hit _find_material's ambiguity ExportError
            # for every such material, not only the genuinely ambiguous ones.
            layer = export_layer(str(db_path), name, nk_csv_dir=mat_dir, label=name)
            mat_dir.mkdir(parents=True, exist_ok=True)
            layer_path = mat_dir / f"{dirname}_layer.json"
            layer_path.write_text(json.dumps(layer, indent=2))
            results.append(dict(
                formula=formula, name=name, status="OK",
                dataset_label=layer["materials_db"]["dataset_label"],
                optical_dataset_label=layer["materials_db"]["optical_dataset_label"],
                density_confidence=layer["materials_db"]["density_confidence"],
                xray_sld_real=layer["xray"]["sld_real"]["value"],
                path=str(layer_path), error=None,
            ))
        except ExportError as e:
            results.append(dict(
                formula=formula, name=name, status="SKIPPED",
                dataset_label=None, optical_dataset_label=None,
                density_confidence=None, xray_sld_real=None,
                path=None, error=str(e),
            ))

    report_path = out_dir / "export_report.csv"
    fields = ["formula", "name", "status", "dataset_label", "optical_dataset_label",
              "density_confidence", "xray_sld_real", "path", "error"]
    with open(report_path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_skipped = sum(1 for r in results if r["status"] == "SKIPPED")

    if strict:
        actual_skips = {r["formula"] for r in results if r["status"] == "SKIPPED"}
        expected_skips = set(KNOWN_EXCLUSIONS)
        unexpected = actual_skips - expected_skips
        if unexpected:
            raise AssertionError(
                f"Export failed for material(s) not in KNOWN_EXCLUSIONS: {sorted(unexpected)}. "
                f"This is a regression, not an expected exclusion -- investigate before proceeding."
            )
        newly_succeeding = expected_skips - actual_skips
        if newly_succeeding:
            raise AssertionError(
                f"Material(s) previously in KNOWN_EXCLUSIONS now export successfully: "
                f"{sorted(newly_succeeding)}. If their underlying gap was genuinely fixed, "
                f"update KNOWN_EXCLUSIONS in exporter.py to reflect it -- don't let this "
                f"pass silently."
            )

    return dict(n_ok=n_ok, n_skipped=n_skipped, n_total=len(materials),
                out_dir=out_dir, report_path=report_path, results=results)
