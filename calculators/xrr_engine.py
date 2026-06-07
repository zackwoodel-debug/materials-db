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

_ROOT = Path(__file__).resolve().parent.parent   # project root

# ── Physical constants ────────────────────────────────────────────────────────

NA  = 6.02214076e23   # Avogadro number  (mol⁻¹)
R_E = 2.8179403e-5    # classical electron radius  (Å)

# ── Atomic data ───────────────────────────────────────────────────────────────
# H C N O F Si S P Au only — expand on request.

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

# ── Formula parser ────────────────────────────────────────────────────────────

def parse_formula(formula: str) -> dict[str, int]:
    """
    Parse a chemical formula string into {element: count}.
    Handles outer-parenthesis polymer notation: "(C5H8O2)n" → C5H8O2.
    Does not support nested parentheses or multipliers other than the outer one.
    """
    clean = re.sub(r"^\((.+)\)[A-Za-z]?\d*$", r"\1", formula.strip())
    counts: dict[str, int] = {}
    for elem, num_str in re.findall(r"([A-Z][a-z]?)(\d*)", clean):
        if not elem:
            continue
        counts[elem] = counts.get(elem, 0) + (int(num_str) if num_str else 1)
    return counts


# ── XRR computation ───────────────────────────────────────────────────────────

def compute_xrr(formula: str, density_g_cm3: float) -> dict:
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


# ── DB lookup ─────────────────────────────────────────────────────────────────

def read_material(db_path: str, name: str) -> tuple[str, float]:
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


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
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
