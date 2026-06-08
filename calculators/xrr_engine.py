#!/usr/bin/env python3
"""
calculators/xrr_engine.py
=========================
X-ray reflectometry electron density and SLD calculator.

Reads the material's formula and density from materials.db, then computes:
  Mw      = Σ(nᵢ · atomic_weight_i)                          [g/mol]
  Z_total = Σ(nᵢ · Zᵢ)                                       [electrons/formula unit]
  ρₑ      = (ρ · Nₐ · Z_total) / (Mw · 1e24)                [e⁻/Å³]
  SLD     = ρₑ · r_e                                          [Å⁻²]

Usage:
    python xrr_engine.py --material PMMA --db materials.db
    python xrr_engine.py --material Water --db ../materials.db
"""

import argparse
import re
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# NA and R_E together convert bulk electron density to the X-ray scattering length
# density needed by the Parratt recursion.
NA  = 6.02214076e23   # Avogadro number  (mol⁻¹)
R_E = 2.8179403e-5    # classical electron radius  (Å)

# ATOMS maps each element to its proton number Z and IUPAC atomic weight; only
# elements common to organic thin films and noble metals are included here.

ATOMS: dict[str, tuple[int, float]] = {
    #       Z    atomic_weight (g/mol)
    "H":  ( 1,   1.00794),
    "C":  ( 6,  12.0107),
    "N":  ( 7,  14.0067),
    "O":  ( 8,  15.9994),
    "F":  ( 9,  18.9984),
    "Si": (14,  28.0855),
    "P":  (15,  30.97376),
    "S":  (16,  32.065),
    "Au": (79, 196.9665),
}

def parse_formula(formula: str) -> dict[str, int]:
    """
    Physical purpose: Strip polymer repeat-unit notation and tally each element's atom count from a chemical formula string.
    Args/Returns: formula — string such as "(C5H8O2)n" or "Au"; returns dict mapping element symbol to integer count.
    """
    clean = re.sub(r"^\((.+)\)[A-Za-z]?\d*$", r"\1", formula.strip())
    counts: dict[str, int] = {}
    for elem, num_str in re.findall(r"([A-Z][a-z]?)(\d*)", clean):
        if not elem:
            continue
        counts[elem] = counts.get(elem, 0) + (int(num_str) if num_str else 1)
    return counts


def compute_xrr(formula: str, density_g_cm3: float) -> dict:
    """
    Physical purpose: Convert a material's chemical formula and bulk mass density into its X-ray scattering length density and the intermediate quantities (Mw, Z_total, ρₑ) needed for Parratt simulation.
    Args/Returns: formula — chemical formula string; density_g_cm3 — bulk mass density in g/cm³; returns dict with keys counts, Mw, Z_total, rho_e, SLD.
    """
    counts = parse_formula(formula)

    unknown = [e for e in counts if e not in ATOMS]
    if unknown:
        raise ValueError(
            f"Element(s) not in atomic table: {unknown}. "
            "Expand ATOMS dict or request support."
        )

    mw      = sum(cnt * ATOMS[el][1] for el, cnt in counts.items())
    z_total = sum(cnt * ATOMS[el][0] for el, cnt in counts.items())

    # ρₑ [e⁻/Å³]:  (ρ [g/cm³] × Nₐ [mol⁻¹] × Z_total) / (Mw [g/mol] × 1e24 [Å³/cm³])
    rho_e = (density_g_cm3 * NA * z_total) / (mw * 1e24)
    sld   = rho_e * R_E

    return {
        "counts":   counts,
        "Mw":       mw,
        "Z_total":  z_total,
        "rho_e":    rho_e,
        "SLD":      sld,
    }


def read_material(db_path: str, name: str) -> tuple[str, float]:
    """
    Physical purpose: Fetch a material's formula and bulk density from materials.db so that compute_xrr can derive its SLD without manual data entry.
    Args/Returns: db_path — path to the SQLite database; name — material name as stored in the materials table; returns (formula, density_g_cm3) or raises ValueError if the material or either field is absent.
    """
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT formula, density_g_cm3 FROM materials WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"Material '{name}' not found in {db_path}")
    formula, density = row
    if formula is None:
        raise ValueError(f"'{name}' has no formula stored in the database")
    if density is None:
        raise ValueError(f"'{name}' has no density_g_cm3 stored in the database")
    return formula, density


def main() -> None:
    """
    Physical purpose: Command-line entry point that prints the electron density and SLD for one material looked up from materials.db.
    Args/Returns: reads --material and --db from sys.argv; writes a formatted report to stdout; exits non-zero if the material is missing or its data is incomplete.
    """
    ap = argparse.ArgumentParser(description="XRR electron density / SLD from materials.db")
    ap.add_argument("--material", required=True, help="Material name as stored in DB (e.g. PMMA)")
    ap.add_argument("--db", default=str(_ROOT / "materials.db"), help="Path to materials.db")
    args = ap.parse_args()

    db = args.db
    if not Path(db).exists():
        raise FileNotFoundError(f"Database not found: {db}")

    formula, density = read_material(db, args.material)
    r = compute_xrr(formula, density)

    print(f"\nXRR — {args.material}")
    print(f"  Formula    : {formula}  →  {r['counts']}")
    print(f"  Density    : {density:.4f} g/cm³")
    print(f"  Mw         : {r['Mw']:.4f} g/mol")
    print(f"  Z_total    : {r['Z_total']} e⁻/formula unit")
    print(f"  ρₑ         : {r['rho_e']:.6f} e⁻/Å³")
    print(f"  SLD        : {r['SLD']:.4e} Å⁻²\n")


if __name__ == "__main__":
    main()
