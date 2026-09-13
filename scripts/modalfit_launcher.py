#!/usr/bin/env python3
"""
scripts/modalfit_launcher.py
===============================
Interactive CLI: search materials_oxide_test.db, assemble an ambient /
film(s) / substrate stack, export it with export_stack() into a temp
directory, and launch ModalFit's own standalone desktop tool
(model_predictor.py) pre-loaded with the result.

A WRAPPER, not a fork: ModalFit's source is never modified. See
src/materials_db/launcher/modalfit_bridge.py's docstring for exactly how
the pre-loaded launch is achieved (driving ModalFit's own, unmodified
"Load Model" code path with the file dialog monkeypatched in THIS
process's memory only).

Requires a local ModalFit clone -- pass --modalfit-path, or set the
MODALFIT_PATH environment variable, to https://github.com/agauer/modalfit
(pinned commit: src/materials_db/export/modalfit_contract.py).

Uses a temp directory (tempfile.mkdtemp()), not a live DB connection held
open by the GUI: export_stack() opens materials_oxide_test.db, writes the
model JSON + sidecar n,k CSVs, and closes it before ModalFit ever launches
-- if ModalFit crashes mid-fit, that costs a temp directory, nothing else.
"""

import argparse
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.export.modalfit import DEFAULT_DB, ExportError, export_stack  # noqa: E402
from materials_db.launcher.ambient import AMBIENT_PRESETS, build_ambient_entry  # noqa: E402
from materials_db.launcher.catalog import describe_row, list_materials  # noqa: E402
from materials_db.launcher.modalfit_bridge import (  # noqa: E402
    ModalFitBridgeError, launch, locate_modalfit_clone, verify_pin_or_warn,
)

OPTIMIZER_TIP = (
    "Reminder (docs/xrr_fit_findings.md, stated rule 3): tightening bounds is NOT a "
    "substitute for choosing an appropriate optimizer, and doing one without the other "
    "can make a fit worse, not better. Tight, physically-reasonable bounds run with "
    "L-BFGS-B (a local optimizer) produced a real fit with chi^2 100x WORSE than the "
    "exporter's wide auto-defaults on an identical stack -- every varying parameter pinned "
    "at its bound edge (a local-minimum trap, not a bounds failure). The SAME tight bounds "
    "recovered the true values exactly under Differential Evolution (a global optimizer). "
    "Before trusting a fit with narrowed bounds, verify it under a global optimizer too --"
    " changing bounds AND optimizer in the same step means you can't tell which one moved "
    "the result."
)


def _prompt(msg, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{msg}{suffix}: ").strip()
    return val or default


def _pick_material(db, role_label, default_query=""):
    """Search/select loop shared by film-layer and substrate picking --
    same interface, same density-confidence display, per the launcher's
    design (a substrate is just a layer with role=substrate)."""
    query = default_query
    while True:
        query = _prompt(f"Search for {role_label} (name/formula substring, blank=list all)", query) or ""
        rows = list_materials(db, query=query)
        if not rows:
            print("  No matches. Try a different search.")
            continue
        for i, r in enumerate(rows, 1):
            print(f"  {i:3d}. {describe_row(r)}")
        choice = _prompt(f"Pick a number for {role_label}, or 's' to search again")
        if not choice or choice.lower() == "s":
            continue
        try:
            row = rows[int(choice) - 1]
        except (ValueError, IndexError):
            print("  Invalid choice.")
            continue
        if not row["selectable"]:
            print(f"  '{row['name']}' is a named exclusion and cannot be selected: {row['exclusion_reason']}")
            continue
        print(f"  Selected: {describe_row(row)}")
        return row


def _prompt_bounds(label, kind):
    """Prompt for a value plus optional min/max bounds. Prints the
    optimizer tip immediately when the caller actually narrows a bound --
    the exact moment this finding is relevant, not buried in a doc they
    have to go looking for."""
    val_str = _prompt(f"  {label} {kind} (Angstrom, blank = not set)")
    if not val_str:
        return None, None, None
    value = float(val_str)
    min_str = _prompt(f"  {label} {kind} min (blank = exporter auto-default)")
    max_str = _prompt(f"  {label} {kind} max (blank = exporter auto-default)")
    vmin = float(min_str) if min_str else None
    vmax = float(max_str) if max_str else None
    if vmin is not None or vmax is not None:
        print(f"\n  *** {OPTIMIZER_TIP} ***\n")
    return value, vmin, vmax


def _pick_ambient():
    print("\nAmbient presets:")
    for name, p in AMBIENT_PRESETS.items():
        print(f"  {name:8s} {p['label']}")
    choice = _prompt("Choose ambient", "air")
    return build_ambient_entry(choice)


def build_stack_interactively(db):
    print(f"\nUsing database: {db}\n")

    ambient_entry = _pick_ambient()

    print("\n--- Film layers (top of stack down to the substrate) ---")
    layers = []
    while True:
        add = _prompt("Add a film layer? (y/n)", "y" if not layers else "n")
        if add.lower() != "y":
            break
        row = _pick_material(db, "film layer")
        thickness, t_min, t_max = _prompt_bounds(row["name"], "thickness")
        roughness, r_min, r_max = _prompt_bounds(row["name"], "roughness")
        spec = dict(material=row["name"])
        if row["polymorph"]:
            spec["dataset_label"] = row["polymorph"]
        if thickness is not None:
            spec.update(thickness_a=thickness, thickness_min=t_min, thickness_max=t_max)
        if roughness is not None:
            spec.update(roughness_a=roughness, roughness_min=r_min, roughness_max=r_max)
        layers.append(spec)

    print("\n--- Substrate ---")
    sub_row = _pick_material(db, "substrate", default_query="Silicon")
    sub_roughness, sub_r_min, sub_r_max = _prompt_bounds(sub_row["name"], "roughness (film/substrate interface)")

    return dict(
        ambient=ambient_entry,
        layers=layers,
        substrate=sub_row["name"],
        substrate_dataset_label=sub_row["polymorph"],
        substrate_roughness_a=sub_roughness,
        substrate_roughness_min=sub_r_min,
        substrate_roughness_max=sub_r_max,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to materials_oxide_test.db")
    parser.add_argument("--modalfit-path", default=None,
                         help="Path to a local ModalFit clone (or set MODALFIT_PATH)")
    parser.add_argument("--stack-id", default=None)
    parser.add_argument("--sample-id", default=None)
    args = parser.parse_args()

    try:
        clone_path = locate_modalfit_clone(args.modalfit_path)
    except ModalFitBridgeError as e:
        sys.exit(f"ERROR: {e}")
    print(verify_pin_or_warn(clone_path))

    stack_spec = build_stack_interactively(args.db)

    out_dir = Path(tempfile.mkdtemp(prefix="modalfit_launch_"))
    print(f"\nExporting stack into temp directory: {out_dir}")
    try:
        result = export_stack(
            args.db, stack_spec["layers"],
            ambient=stack_spec["ambient"],
            substrate=stack_spec["substrate"],
            substrate_dataset_label=stack_spec["substrate_dataset_label"],
            substrate_roughness_a=stack_spec["substrate_roughness_a"],
            substrate_roughness_min=stack_spec["substrate_roughness_min"],
            substrate_roughness_max=stack_spec["substrate_roughness_max"],
            stack_id=args.stack_id, sample_id=args.sample_id,
            out_dir=out_dir,
        )
    except ExportError as e:
        sys.exit(f"Export failed: {e}")

    model_path = out_dir / f"{result['stack_id']}.json"
    import json
    model_path.write_text(json.dumps(result, indent=2))

    print(f"\nStack summary ({result['n_layers']} film layer(s)):")
    for entry in result["stack"]:
        conf = entry.get("molecular", {}).get("density_confidence", "n/a (no molecular density)")
        print(f"  [{entry['role']:9s}] {entry['label']:30s} density_confidence={conf}")
    print(f"\nWrote {model_path}")
    print(f"\n*** {OPTIMIZER_TIP} ***\n")

    print(f"Launching ModalFit ({clone_path}) with this model preloaded...")
    launch(model_path, clone_path)


if __name__ == "__main__":
    main()
