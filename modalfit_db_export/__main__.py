"""
__main__.py -- command line entry point
========================================
    python -m modalfit_db_export --db <database.db> --out <dir> [options]

Three modes, all taking the same --db / --out pair:

  --list                 print every material in the database and exit
  (default)              export EVERY material as its own layer JSON
  --layer SPEC [SPEC..]  build ONE stack from the given layers

A layer SPEC is  MATERIAL[:THICKNESS_A[:ROUGHNESS_A]]  with an optional
@POLYMORPH for a multi-polymorph material, e.g.
    TiO2@rutile:500:5      SiO2:1000      Gold@:200
Outermost film first; the ambient and substrate are added automatically.
"""

import argparse
import sys
from pathlib import Path


def _parse_layer_spec(spec: str) -> dict:
    """MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]] -> layer dict.

    Splits on '@' BEFORE ':' so a polymorph containing neither is safe,
    and rejects a non-numeric thickness/roughness loudly instead of
    letting float() raise a bare ValueError with no context about which
    spec was malformed."""
    parts = spec.split(":")
    material = parts[0]
    dataset_label = None
    if "@" in material:
        material, dataset_label = material.split("@", 1)
        dataset_label = dataset_label or None
    if not material:
        raise argparse.ArgumentTypeError(f"Layer spec {spec!r} has no material name.")

    layer = {"material": material}
    if dataset_label:
        layer["dataset_label"] = dataset_label
    for index, key in ((1, "thickness_a"), (2, "roughness_a")):
        if len(parts) > index and parts[index] != "":
            try:
                layer[key] = float(parts[index])
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Layer spec {spec!r}: {key} must be a number in Angstrom, "
                    f"got {parts[index]!r}."
                )
    if len(parts) > 3:
        raise argparse.ArgumentTypeError(
            f"Layer spec {spec!r} has too many ':' fields -- expected "
            f"MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]]."
        )
    return layer


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m modalfit_db_export",
        description="Export materials-db SQLite content as ModalFit slab-model JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--db", required=True, type=Path,
                   help="Path to the materials SQLite database.")
    p.add_argument("--out", type=Path,
                   help="Output directory (required unless --list).")
    p.add_argument("--list", action="store_true",
                   help="List every material in the database and exit.")
    p.add_argument("--layer", nargs="+", metavar="SPEC",
                   help="Build one stack from these layers, outermost first: "
                        "MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]]")
    p.add_argument("--substrate", default="Silicon",
                   help="Substrate material name or formula (default: Silicon).")
    p.add_argument("--substrate-polymorph", default=None,
                   help="dataset_label disambiguating a multi-polymorph substrate.")
    p.add_argument("--substrate-roughness", type=float, default=None, metavar="ANGSTROM",
                   help="Film/substrate interface roughness. ModalFit reads this from "
                        "the SUBSTRATE entry, not the last film -- omitting it leaves a "
                        "perfectly sharp interface. Set it for any stack meant to be fit "
                        "against real reflectivity data.")
    p.add_argument("--ambient", default="air", choices=["air"],
                   help="Ambient medium (default: air). Non-air ambients are not "
                        "DB-sourced -- pass a pre-built entry dict via the Python API.")
    p.add_argument("--stack-id", default=None, help="stack_id written into the JSON.")
    p.add_argument("--sample-id", default=None, help="sample_id written into the JSON.")
    p.add_argument("--filename", default="stack.json",
                   help="Stack JSON filename inside --out (default: stack.json).")
    p.add_argument("--strict", action="store_true",
                   help="Whole-catalog mode: assert the skip set matches KNOWN_EXCLUSIONS "
                        "exactly. Use against the materials-db database in CI.")
    args = p.parse_args(argv)

    if not args.db.exists():
        p.error(f"Database not found: {args.db}")

    from .bulk import export_all_layers, export_stack_json, list_materials
    from .exporter import ExportError

    if args.list:
        materials = list_materials(args.db)
        for m in materials:
            print(f"{m['name']:<40} {m['formula']}")
        print(f"\n{len(materials)} materials in {args.db}")
        return 0

    if args.out is None:
        p.error("--out is required unless --list is given.")

    if args.layer:
        try:
            layers = [_parse_layer_spec(s) for s in args.layer]
        except argparse.ArgumentTypeError as e:
            p.error(str(e))
        try:
            json_path = export_stack_json(
                args.db, args.out, layers,
                ambient=args.ambient, substrate=args.substrate,
                substrate_dataset_label=args.substrate_polymorph,
                substrate_roughness_a=args.substrate_roughness,
                stack_id=args.stack_id, sample_id=args.sample_id,
                filename=args.filename,
            )
        except ExportError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"Wrote {json_path}")
        print(f"Sidecar n,k CSVs are in {args.out} -- keep them beside the JSON.")
        return 0

    summary = export_all_layers(args.db, args.out, strict=args.strict)
    print(f"Exported {summary['n_ok']}/{summary['n_total']} materials, "
          f"{summary['n_skipped']} skipped.")
    print(f"Report: {summary['report_path']}")
    if summary["n_skipped"]:
        print("\nSkipped:")
        for r in summary["results"]:
            if r["status"] == "SKIPPED":
                print(f"  {r['name']} ({r['formula']}): {r['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
