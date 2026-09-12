#!/usr/bin/env python3
"""
calculators/xrr_engine.py
=========================
X-ray reflectometry electron density and SLD calculator.

Reads the material's formula and density from the database, then computes:
  Mw      = Sigma(n_i * atomic_weight_i)                      [g/mol]
  Z_total = Sigma(n_i * Z_i)                                   [electrons/formula unit]
  rho_e   = (rho * NA * Z_total) / (Mw * 1e24)                [e-/A^3]
  SLD     = xray_sld(formula, density, energy) via periodictable [A^-2]

Supports two database schemas, auto-detected from the DB itself:
  - legacy  (data/materials.db): materials.density_g_cm3 is a direct column,
    one row per material, no dataset_label concept.
  - oxide   (data/materials_oxide_test.db, updated_sql_schema.sql): density
    lives in physical_properties, keyed by (material_id, dataset_label) --
    e.g. "rutile | density_MP_DFT". A material may have exactly one density
    row (the common case) or several (different polymorphs of the same
    material name), in which case a dataset_label must be given to
    disambiguate -- see read_material().

SLD is computed via periodictable (energy-dependent f1/f2 anomalous
dispersion + absorption), not the narrower hardcoded ATOMS table this
module used previously -- that table only covered 17 elements and raised
"Element(s) not in atomic table" for most of the 50-oxide dataset's
elements (Bi, Ge, Hf, Ta, Nb, Lu, Tb, Sc, Dy, Cs, Mo, W, V, Y). Note this is
a behavior change for existing legacy-schema materials too: the old path
computed a real-only, energy-independent (Z-only, no anomalous dispersion)
approximation; periodictable's energy-dependent SLD is more physically
accurate and also yields the imaginary (absorption) part, previously
unavailable here.

Usage:
    python xrr_engine.py --material PMMA --db ../../../data/materials.db
    python xrr_engine.py --material TiO2 --dataset-label rutile \\
        --db ../../../data/materials_oxide_test.db
"""

import argparse
import re
import sqlite3
from pathlib import Path
from typing import Optional

import periodictable

from materials_db.calculators.sld_calculator import NA

_ROOT = Path(__file__).resolve().parents[3]

XRAY_ENERGY_KEV = 8.048  # Cu K-alpha, 1.5406 A -- matches scripts/build_oxides_csv.py

# data/materials.db stores polymer repeat-unit formulas like "(C5H8O2)n" or
# "(C8H8)n" -- periodictable's strict parser rejects the trailing "n", so
# strip the wrapper to the bare repeat unit first (SLD is intensive, so
# computing it per-repeat-unit at the given bulk density is correct).
_POLYMER_REPEAT_RE = re.compile(r"^\((.+)\)[A-Za-z]?\d*$")


def _normalize_formula(formula: str) -> str:
    m = _POLYMER_REPEAT_RE.match(formula.strip())
    return m.group(1) if m else formula


def compute_xrr(formula: str, density_g_cm3: float, energy_kev: float = XRAY_ENERGY_KEV) -> dict:
    """
    Physical purpose: Convert a material's chemical formula and bulk mass density into its X-ray scattering length density and the intermediate quantities (Mw, Z_total, rho_e) needed for Parratt simulation.
    Args/Returns: formula -- chemical formula string (periodictable syntax, parentheses supported); density_g_cm3 -- bulk mass density in g/cm3; energy_kev -- X-ray energy in keV; returns dict with keys counts, Mw, Z_total, rho_e, SLD, SLD_imag.
    """
    f = periodictable.formula(_normalize_formula(formula), density=density_g_cm3)

    mw = f.mass
    z_total = sum(el.number * cnt for el, cnt in f.atoms.items())
    counts = {el.symbol: cnt for el, cnt in f.atoms.items()}

    # rho_e [e-/A^3]:  (rho [g/cm3] * NA [mol^-1] * Z_total) / (Mw [g/mol] * 1e24 [A^3/cm3])
    rho_e = (density_g_cm3 * NA * z_total) / (mw * 1e24)
    # periodictable returns xray_sld in units of 1e-6 A^-2 -- convert to plain
    # A^-2 to match parratt()'s convention (q_j = sqrt(q^2 - 16*pi*sld)) and
    # this module's previous (sld_calculator-based) output units.
    xr, xi = f.xray_sld(energy=energy_kev)

    return {
        "counts":   counts,
        "Mw":       mw,
        "Z_total":  z_total,
        "rho_e":    rho_e,
        "SLD":      float(xr) * 1e-6,
        "SLD_imag": float(xi) * 1e-6,
    }


def _detect_schema(conn: sqlite3.Connection) -> str:
    """Return 'legacy' if materials.density_g_cm3 exists as a direct column
    (data/materials.db), or 'oxide' if the updated_sql_schema.sql shape is
    present (density in physical_properties, keyed by dataset_label)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(materials)").fetchall()}
    if "density_g_cm3" in cols:
        return "legacy"
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "physical_properties" in tables:
        return "oxide"
    raise ValueError(
        "Unrecognized database schema: 'materials' has no density_g_cm3 column, "
        "and no 'physical_properties' table exists either."
    )


def _find_material(conn: sqlite3.Connection, name: str, select_cols: str):
    """Look up a materials row by name first, falling back to formula --
    the oxide dataset's materials.name is a full descriptive name (e.g.
    "Titanium dioxide (rutile / anatase)") while users naturally look up
    by formula ("TiO2"); the legacy DB's name IS the common short name
    (e.g. "PMMA") so this fallback is a no-op there unless it also happens
    to match a formula."""
    row = conn.execute(f"SELECT {select_cols} FROM materials WHERE name = ?", (name,)).fetchone()
    if row is None:
        row = conn.execute(f"SELECT {select_cols} FROM materials WHERE formula = ?", (name,)).fetchone()
    return row


def read_material(db_path: str, name: str, dataset_label: Optional[str] = None) -> tuple[str, float]:
    """
    Physical purpose: Fetch a material's formula and bulk density from either
    database schema so compute_xrr can derive its SLD without manual data entry.
    Args/Returns: db_path -- path to the SQLite database; name -- material name
    as stored in the materials table; dataset_label -- optional prefix filter
    (e.g. "rutile") to disambiguate when a material has more than one density
    row in the oxide schema; ignored (must be None) for the legacy schema.
    Returns (formula, density_g_cm3) or raises ValueError if the material,
    its density, or an unambiguous dataset_label match cannot be resolved.
    """
    conn = sqlite3.connect(db_path)
    try:
        schema = _detect_schema(conn)

        if schema == "legacy":
            if dataset_label is not None:
                raise ValueError(
                    f"'{name}' is in a legacy-schema database ({db_path}) with no dataset_label "
                    "concept -- drop the [dataset_label] stack syntax for this database."
                )
            row = _find_material(conn, name, "formula, density_g_cm3")
            if row is None:
                raise ValueError(f"Material '{name}' not found in {db_path}")
            formula, density = row

        else:  # schema == "oxide"
            mat_row = _find_material(conn, name, "material_id, formula")
            if mat_row is None:
                raise ValueError(f"Material '{name}' not found in {db_path}")
            material_id, formula = mat_row

            query = ("SELECT density_g_cm3, dataset_label FROM physical_properties "
                      "WHERE material_id = ? AND density_g_cm3 IS NOT NULL")
            params: list = [material_id]
            if dataset_label:
                query += " AND dataset_label LIKE ?"
                params.append(f"{dataset_label}%")
            rows = conn.execute(query, params).fetchall()

            if not rows:
                all_labels = [r[0] for r in conn.execute(
                    "SELECT DISTINCT dataset_label FROM physical_properties WHERE material_id = ?",
                    (material_id,),
                ).fetchall()]
                hint = f" Available dataset_labels for '{name}': {all_labels}" if all_labels else \
                       f" No physical_properties rows exist for '{name}' at all."
                label_clause = f" matching dataset_label '{dataset_label}'" if dataset_label else ""
                raise ValueError(f"No density found for '{name}'{label_clause} in {db_path}.{hint}")

            if len(rows) > 1:
                labels = [r[1] for r in rows]
                example = labels[0].split(" | ")[0]
                raise ValueError(
                    f"Ambiguous: {len(rows)} density rows found for '{name}' in {db_path}. "
                    f"Specify a dataset_label to disambiguate, e.g. '{name}[{example}]'. "
                    f"Available: {labels}"
                )

            density = rows[0][0]

        if formula is None:
            raise ValueError(f"'{name}' has no formula stored in the database")
        if density is None:
            raise ValueError(f"'{name}' has no density stored in the database")
        return formula, density
    finally:
        conn.close()


def main() -> None:
    """
    Physical purpose: Command-line entry point that prints the electron density and SLD for one material looked up from a materials database (either schema).
    Args/Returns: reads --material, --dataset-label, and --db from sys.argv; writes a formatted report to stdout; exits non-zero if the material is missing, its data is incomplete, or the dataset_label is ambiguous/unmatched.
    """
    ap = argparse.ArgumentParser(description="XRR electron density / SLD from a materials database")
    ap.add_argument("--material", required=True, help="Material name as stored in DB (e.g. PMMA, TiO2)")
    ap.add_argument("--dataset-label", default=None,
                     help="Optional dataset_label prefix (e.g. 'rutile') to disambiguate a material "
                          "with multiple density rows. Oxide schema only.")
    ap.add_argument("--db", default=str(_ROOT / "data" / "materials.db"), help="Path to the database")
    args = ap.parse_args()

    db = args.db
    if not Path(db).exists():
        raise FileNotFoundError(f"Database not found: {db}")

    formula, density = read_material(db, args.material, dataset_label=args.dataset_label)
    r = compute_xrr(formula, density)

    print(f"\nXRR -- {args.material}")
    print(f"  Formula    : {formula}  ->  {r['counts']}")
    print(f"  Density    : {density:.4f} g/cm3")
    print(f"  Mw         : {r['Mw']:.4f} g/mol")
    print(f"  Z_total    : {r['Z_total']} e-/formula unit")
    print(f"  rho_e      : {r['rho_e']:.6f} e-/A^3")
    print(f"  SLD        : {r['SLD']:.4e} A^-2")
    print(f"  SLD (imag) : {r['SLD_imag']:.4e} A^-2\n")


if __name__ == "__main__":
    main()
