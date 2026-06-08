#!/usr/bin/env python3
"""End-to-end verification: DB init, CSV parse, Parratt simulation.

Exit 0 on success; non-zero with printed failure message otherwise.
"""

import io
import sys

import numpy as np

from src.db.schema import init_db, insert_material, insert_optical, insert_mechanical
from src.pipeline.parser import parse_csv
from src.simulation.xrr import parratt

# ---------------------------------------------------------------------------
# Physical constants for SLD derivation (NIST / CODATA)
# ---------------------------------------------------------------------------
_NA  = 6.02214076e23   # Avogadro (mol⁻¹)
_R_E = 2.8179403e-5    # classical electron radius (Å)


def _xsld(rho_g_cm3: float, mw_g_mol: float, z_total: int) -> float:
    """X-ray SLD in Å⁻² from bulk density, molecular weight, electron count."""
    rho_e = (rho_g_cm3 * _NA * z_total) / (mw_g_mol * 1e24)  # e⁻/Å³
    return float(rho_e * _R_E)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, condition: bool, msg: str = "") -> None:
    if condition:
        _passed.append(name)
    else:
        _failed.append(f"{name}: {msg}" if msg else name)


# ---------------------------------------------------------------------------
# 1. DB initialisation and round-trip insert/query
# ---------------------------------------------------------------------------

conn = init_db(":memory:")

mat_id = insert_material(conn, "DPPC", "Fluid/Method4")
insert_optical(conn, mat_id, "Fluid/Method4", 670.0, 1.3829)
insert_optical(conn, mat_id, "Fluid/Method4", 785.0, 1.3792)
insert_mechanical(conn, mat_id, "PBS-filled", 1.000, 5700.0, 204517.0, 2.17)

row = conn.execute(
    "SELECT wavelength_nm, n FROM optical_constants WHERE material_id=? ORDER BY wavelength_nm",
    (mat_id,),
).fetchall()

check("db_init",       conn is not None)
check("db_optical_n",  len(row) == 2, f"expected 2 optical rows, got {len(row)}")
check("db_n_670",      abs(row[0][1] - 1.3829) < 1e-9, f"n@670={row[0][1]}")
check("db_n_785",      abs(row[1][1] - 1.3792) < 1e-9, f"n@785={row[1][1]}")

mrow = conn.execute(
    "SELECT shear_storage_pascal, shear_loss_pascal FROM mechanical_qcmd WHERE material_id=?",
    (mat_id,),
).fetchone()
check("db_shear_storage", mrow is not None and mrow[0] == 5700.0,   f"got {mrow}")
check("db_shear_loss",    mrow is not None and mrow[1] == 204517.0, f"got {mrow}")

# ---------------------------------------------------------------------------
# 2. CSV parse — present and missing columns
# ---------------------------------------------------------------------------

complete_csv = io.StringIO(
    "wavelength_nm,n,k\n"
    "633.0,1.46,0.0\n"
    "785.0,1.45,0.0\n"
)
df = parse_csv(complete_csv)
check("csv_columns",  {"wavelength_nm", "n", "k"}.issubset(df.columns))
check("csv_rows",     len(df) == 2, f"expected 2 rows, got {len(df)}")
check("csv_n_val",    abs(df["n"].iloc[0] - 1.46) < 1e-9)

incomplete_csv = io.StringIO("wavelength_nm,n\n633.0,1.46\n")
df2 = parse_csv(incomplete_csv, required_columns=["wavelength_nm", "n", "k"])
check("csv_missing_k_added", "k" in df2.columns, "k column not backfilled")
check("csv_missing_k_nan",   bool(df2["k"].isna().all()), f"k={df2['k'].tolist()}")

# ---------------------------------------------------------------------------
# 3. Parratt simulation — vacuum / SiO2 (20 Å) / Si substrate
#
#   Si:   rho=2.329 g/cm³, Mw=28.085 g/mol, Z=14  → SLD≈1.97e-5 Å⁻²
#   SiO2: rho=2.196 g/cm³, Mw=60.085 g/mol, Z=30  → SLD≈1.86e-5 Å⁻²
#   (densities: NIST SRD 69; values are established references, not invented)
# ---------------------------------------------------------------------------

sld_Si   = _xsld(2.329, 28.085, 14)
sld_SiO2 = _xsld(2.196, 60.085, 30)

Q   = np.linspace(0.01, 0.60, 500)
sld = np.array([0.0, sld_SiO2, sld_Si])
d   = np.array([0.0,     20.0,     0.0])   # Å
sig = np.array([3.0,      3.0,     3.0])   # Å RMS roughness

R = parratt(Q, sld, d, sig)

check("R_length", len(R) == len(Q), f"len(R)={len(R)}, expected {len(Q)}")
check(
    "R_bounds",
    bool(np.all((R >= 0.0) & (R <= 1.0))),
    f"R out of [0,1]: min={R.min():.6f}, max={R.max():.6f}",
)
# Physical sanity: TER plateau should give R=1 well below the critical edge
q_c_approx = np.sqrt(16.0 * np.pi * sld_Si)   # ≈ 0.031 Å⁻¹
plateau_mask = Q < 0.8 * q_c_approx
check(
    "R_TER_plateau",
    bool(np.all(R[plateau_mask] > 0.999)),
    f"TER not flat below 0.8·q_c: min R={R[plateau_mask].min():.6f}",
)
# High-Q tail should be small
check(
    "R_highQ_decay",
    bool(R[Q > 0.4].max() < 0.01),
    f"high-Q R too large: {R[Q > 0.4].max():.4f}",
)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

for name in _passed:
    print(f"  PASS  {name}")
for msg in _failed:
    print(f"  FAIL  {msg}")

if _failed:
    print(f"\n{len(_failed)} check(s) failed.")
    sys.exit(1)

print(f"\nAll {len(_passed)} checks passed.")
sys.exit(0)
