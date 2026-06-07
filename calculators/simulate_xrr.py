#!/usr/bin/env python3
"""
calculators/simulate_xrr.py
============================
Parratt-recursion XRR simulator.

SLD values are computed by xrr_engine.py (reads formula + density from materials.db).
Only NumPy is required; no external reflectometry packages.

Usage:
    python simulate_xrr.py --stack "Vacuum,PMMA:120,Gold:250,Silicon" \\
                            --db ../materials.db
"""

import argparse
import csv
import importlib.util as _ilu
from pathlib import Path

import numpy as np

# ── load xrr_engine from the same directory without mutating sys.path ─────────
def _import_sibling(name: str):
    """Import a .py module from the same directory as this script."""
    path = Path(__file__).parent / f"{name}.py"
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)   # type: ignore[union-attr]
    return mod

_xrr         = _import_sibling("xrr_engine")
compute_xrr  = _xrr.compute_xrr
read_material = _xrr.read_material

# Default DB path is the project root (parent of this script's directory)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB    = str(_PROJECT_ROOT / "materials.db")


# ── Parratt recursion ─────────────────────────────────────────────────────────

def parratt(q_arr: np.ndarray,
            slds: np.ndarray,
            thicknesses: np.ndarray) -> np.ndarray:
    """
    Specular reflectivity via exact Parratt recursion.

    Parameters
    ----------
    q_arr       : (M,)   momentum transfer in Å⁻¹
    slds        : (L,)   SLD of each layer in Å⁻²;
                         slds[0] = superstrate (semi-∞), slds[-1] = substrate (semi-∞)
    thicknesses : (L,)   layer thickness in Å;
                         thicknesses[0] and thicknesses[-1] are ignored by the recursion

    Returns
    -------
    R : (M,)   reflectivity ∈ [0, 1]

    Recursion (exactly as specified):
        q_j   = sqrt(q² − 16π·SLD_j + 0j),   enforce q_j.real ≥ 0
        r_jk  = (q_j − q_k) / (q_j + q_k)    where k = j + 1
        init  : X = r_{N-1,N}                 (deepest interface)
        loop j = N-2 → 0:
            phase = exp(2i · q_{j+1} · d_{j+1})
            X_j   = (r_{j,j+1} + X_{j+1}·phase) / (1 + r_{j,j+1}·X_{j+1}·phase)
        R = |X_0|²   clamped to [0, 1]
    """
    n_media = len(slds)                        # superstrate + films + substrate = N+1

    # Wavevector in each medium; shape (n_media, M)
    q_j = np.sqrt(
        q_arr[np.newaxis, :] ** 2
        - 16.0 * np.pi * slds[:, np.newaxis]
        + 0j
    )
    # Physical root: q_j.real >= 0 (sign convention for decaying evanescent wave)
    q_j = np.where(q_j.real < 0.0, -q_j, q_j)

    # Fresnel reflection coefficients at each interface; shape (n_media-1, M)
    # r[j] = (q_j − q_{j+1}) / (q_j + q_{j+1})
    num   = q_j[:-1] - q_j[1:]
    denom = q_j[:-1] + q_j[1:]
    # denom == 0 only if both layers have SLD=0 and q=0 simultaneously
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(denom == 0.0, np.complex128(-1.0), num / denom)

    # Init: X_{N-1} = r_{N-1, N}  →  r[-1]  (substrate interface)
    X = r[-1].copy()

    # Parratt loop: j = N-2 → 0  (interface indices n_media-3 → 0)
    for j in range(n_media - 3, -1, -1):
        phase = np.exp(2j * q_j[j + 1] * thicknesses[j + 1])
        rj    = r[j]
        X     = (rj + X * phase) / (1.0 + rj * X * phase)

    R = np.abs(X) ** 2
    np.clip(R, 0.0, 1.0, out=R)       # handles total external reflection & fp edge cases
    return R


# ── Stack parser ──────────────────────────────────────────────────────────────

def parse_stack(stack_str: str, db_path: str) -> list[dict]:
    """
    Parse "Vacuum,PMMA:120,Gold:250,Silicon" into a validated list of layer dicts.

    First and last entries must not carry a thickness token (semi-infinite).
    All intermediate entries must specify thickness in Å as Name:thickness.

    Raises ValueError immediately if any material lookup fails.
    """
    entries = [s.strip() for s in stack_str.split(",")]
    if len(entries) < 2:
        raise ValueError("Stack must have at least two entries (superstrate, substrate).")

    layers: list[dict] = []

    for i, entry in enumerate(entries):
        semi_inf = (i == 0) or (i == len(entries) - 1)

        if ":" in entry:
            name, thick_str = entry.split(":", 1)
            if semi_inf:
                raise ValueError(
                    f"Semi-infinite layer '{name.strip()}' (position {i}) "
                    "must not have a thickness."
                )
            thickness = float(thick_str)
        else:
            if not semi_inf:
                raise ValueError(
                    f"Intermediate layer '{entry}' (position {i}) "
                    "must specify a thickness as Name:thickness_Å."
                )
            name = entry
            thickness = 0.0     # not used in recursion

        name = name.strip()

        # Vacuum / Air: SLD = 0 by definition, no DB lookup needed
        if name.lower() in ("vacuum", "air"):
            layers.append(dict(
                name=name, thickness_A=thickness,
                formula="—", density=0.0, rho_e=0.0, SLD=0.0,
            ))
            continue

        # All other materials: DB lookup + XRR computation
        formula, density = read_material(db_path, name)
        result = compute_xrr(formula, density)
        layers.append(dict(
            name=name, thickness_A=thickness,
            formula=formula, density=density,
            rho_e=result["rho_e"],
            SLD=result["SLD"],
        ))

    return layers


# ── Output helpers ────────────────────────────────────────────────────────────

def print_stack_table(layers: list[dict]) -> None:
    col_w = (7, 14, 14, 14, 13)
    header = (
        f"{'Layer #':>{col_w[0]}}  {'Material':<{col_w[1]}}  "
        f"{'Thickness (Å)':>{col_w[2]}}  {'SLD (Å⁻²)':>{col_w[3]}}  "
        f"{'ρₑ (e⁻/Å³)':>{col_w[4]}}"
    )
    sep = "─" * len(header)
    print(sep)
    print(header)
    print(sep)
    n = len(layers)
    for i, lay in enumerate(layers):
        thick_str = "∞" if (i == 0 or i == n - 1) else f"{lay['thickness_A']:.1f}"
        print(
            f"{i:>{col_w[0]}}  {lay['name']:<{col_w[1]}}  "
            f"{thick_str:>{col_w[2]}}  {lay['SLD']:>{col_w[3]}.4e}  "
            f"{lay['rho_e']:>{col_w[4]}.6f}"
        )
    print(sep)


def save_csv(path: str, q_arr: np.ndarray, R: np.ndarray) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["q (1/Ang)", "Reflectivity"])
        for q_val, r_val in zip(q_arr, R):
            writer.writerow([f"{q_val:.8f}", f"{r_val:.8e}"])


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Parratt XRR simulation from materials.db"
    )
    ap.add_argument(
        "--stack", required=True,
        help=(
            'Comma-separated layer stack, e.g. "Vacuum,PMMA:120,Gold:250,Silicon". '
            "First and last entries are semi-infinite (no thickness). "
            "Intermediate entries require Name:thickness_Å."
        ),
    )
    ap.add_argument("--db",     default=DEFAULT_DB,
                    help="Path to materials.db  [default: %(default)s]")
    ap.add_argument("--qmin",   type=float, default=0.01,
                    help="Minimum q in Å⁻¹  [default: %(default)s]")
    ap.add_argument("--qmax",   type=float, default=0.50,
                    help="Maximum q in Å⁻¹  [default: %(default)s]")
    ap.add_argument("--qpts",   type=int,   default=500,
                    help="Number of q points  [default: %(default)s]")
    ap.add_argument("--output", default="xrr_simulation_output.csv",
                    help="Output CSV filename  [default: %(default)s]")
    args = ap.parse_args()

    db = args.db
    if not Path(db).exists():
        sys.exit(f"ERROR: database not found: {db}")

    # ── Validate stack first (all lookups must succeed before any math) ──────
    print(f"\nStack  : {args.stack}")
    print(f"DB     : {db}\n")

    try:
        layers = parse_stack(args.stack, db)
    except (ValueError, FileNotFoundError) as exc:
        sys.exit(f"ERROR parsing stack: {exc}")

    print_stack_table(layers)

    # ── Simulation ────────────────────────────────────────────────────────────
    slds        = np.array([lay["SLD"]         for lay in layers])
    thicknesses = np.array([lay["thickness_A"] for lay in layers])

    q_arr = np.linspace(args.qmin, args.qmax, args.qpts)
    R     = parratt(q_arr, slds, thicknesses)

    save_csv(args.output, q_arr, R)

    print(f"\nq range   : {args.qmin:.4f} – {args.qmax:.4f} Å⁻¹  ({args.qpts} points)")
    print(f"R range   : [{R.min():.4e}, {R.max():.4e}]")
    print(f"Output    : {args.output}\n")


if __name__ == "__main__":
    main()
