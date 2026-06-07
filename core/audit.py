#!/usr/bin/env python3
"""
core/audit.py
Audit materials.db + pipeline/fetch_optical_data.py.
Outputs PASS / WARN / FAIL per check, then inserts the DPPC 633 nm point.
Dependencies: stdlib only (sqlite3, re, pathlib).
"""

import re
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent   # project root

DB   = str(_ROOT / "materials.db")
CODE = str(_ROOT / "pipeline" / "fetch_optical_data.py")

results: list[tuple[str, str, str]] = []   # (status, check_id, detail)

def record(status: str, check_id: str, detail: str) -> None:
    results.append((status, check_id, detail))

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# DB CHECKS
# ─────────────────────────────────────────────────────────────────────────────

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# DB-1  Both tables exist and are non-empty
mat_count = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
nk_count  = conn.execute("SELECT COUNT(*) FROM optical_nk").fetchone()[0]

if mat_count >= 5 and nk_count > 0:
    record(PASS, "DB-1", f"materials={mat_count} rows, optical_nk={nk_count} rows")
elif mat_count > 0 and nk_count > 0:
    record(WARN, "DB-1", f"materials={mat_count}, optical_nk={nk_count} — low row count")
else:
    record(FAIL, "DB-1", f"materials={mat_count}, optical_nk={nk_count} — table(s) empty")

# DB-2  Per-material: wl range, n points, k NULL fraction, source_ref present
EXPECTED = {
    "Water":       dict(min_pts=10,  has_k=True,  wl_lo_max=250,  wl_hi_min=600),
    "Gold":        dict(min_pts=10,  has_k=True,  wl_lo_max=250,  wl_hi_min=500),
    "SiO2":        dict(min_pts=100, has_k=False, wl_lo_max=300,  wl_hi_min=500),
    "Polystyrene": dict(min_pts=100, has_k=False, wl_lo_max=500,  wl_hi_min=600),
    "DPPC":        dict(min_pts=0,   has_k=None,  wl_lo_max=None, wl_hi_min=None),
}

for row in conn.execute("""
    SELECT m.name,
           COUNT(o.id)                                     AS pts,
           MIN(o.wavelength_nm)                            AS wl_lo,
           MAX(o.wavelength_nm)                            AS wl_hi,
           SUM(o.k IS NULL)                                AS k_null,
           SUM(o.k IS NOT NULL)                            AS k_present,
           (MAX(o.source_ref) IS NOT NULL)                 AS has_src
    FROM materials m
    LEFT JOIN optical_nk o ON o.material_id = m.id
    GROUP BY m.id
    ORDER BY m.id
"""):
    name   = row["name"]
    pts    = row["pts"]
    wl_lo  = row["wl_lo"]
    wl_hi  = row["wl_hi"]
    k_null = row["k_null"] if row["k_null"] is not None else 0
    k_pres = row["k_present"] if row["k_present"] is not None else 0
    has_src= row["has_src"]
    exp    = EXPECTED.get(name, {})

    if pts == 0:
        if name == "DPPC":
            record(FAIL, f"DB-2[{name}]",
                   "0 optical rows — material not in RI.info (expected); manual INSERT needed")
        else:
            record(FAIL, f"DB-2[{name}]", f"0 n/k rows — unexpected parse failure")
        continue

    min_pts = exp.get("min_pts", 1)
    if pts < min_pts:
        record(FAIL, f"DB-2[{name}]", f"only {pts} n/k rows (expected ≥{min_pts})")
        continue

    parts = []

    if exp.get("wl_lo_max") and wl_lo > exp["wl_lo_max"]:
        parts.append(f"wl_lo={wl_lo:.1f} nm (expected ≤{exp['wl_lo_max']})")
    if exp.get("wl_hi_min") and wl_hi < exp["wl_hi_min"]:
        parts.append(f"wl_hi={wl_hi:.1f} nm (expected ≥{exp['wl_hi_min']})")

    if exp.get("has_k") is True and k_pres == 0:
        parts.append("k fully NULL but k data expected")
    if exp.get("has_k") is False and k_pres > 0:
        parts.append(f"unexpected k values ({k_pres} non-NULL)")

    if not has_src:
        parts.append("source_ref missing")

    if k_null > 0 and k_pres > 0:
        pct = 100 * k_null / (k_null + k_pres)
        parts.append(f"k partially NULL ({pct:.0f}% of rows) — check interp boundaries")

    summary = (f"pts={pts}, wl={wl_lo:.0f}–{wl_hi:.0f} nm, "
               f"k_pres={k_pres}/{pts}, k_null={k_null}/{pts}")
    if parts:
        record(WARN, f"DB-2[{name}]", summary + " | " + "; ".join(parts))
    else:
        record(PASS, f"DB-2[{name}]", summary)

# DB-3  n out-of-range [1.0, 4.0]
METAL_MATERIALS = {"Gold", "Silver", "Copper", "Aluminum"}

for row in conn.execute("""
    SELECT m.name, m.material_class,
           SUM(o.n < 1.0)  AS n_lo,
           SUM(o.n > 4.0)  AS n_hi,
           MIN(o.n)         AS n_min,
           MAX(o.n)         AS n_max
    FROM optical_nk o
    JOIN materials m ON m.id = o.material_id
    GROUP BY m.id
"""):
    name  = row["name"]
    n_lo  = row["n_lo"]  or 0
    n_hi  = row["n_hi"]  or 0
    n_min = row["n_min"]
    n_max = row["n_max"]
    is_metal = row["material_class"] == "metal"

    if n_hi > 0:
        record(FAIL, f"DB-3[{name}]",
               f"{n_hi} rows with n > 4.0 (max={n_max:.4f}) — unexpected for any optical material")
    elif n_lo > 0 and is_metal:
        record(WARN, f"DB-3[{name}]",
               f"{n_lo} rows with n < 1.0 (min={n_min:.4f}) — "
               f"physically valid for metals (free-electron plasma)")
    elif n_lo > 0:
        record(FAIL, f"DB-3[{name}]",
               f"{n_lo} rows with n < 1.0 (min={n_min:.4f}) — unexpected for non-metal")
    else:
        record(PASS, f"DB-3[{name}]", f"n in [{n_min:.4f}, {n_max:.4f}]")

# DB-4  k out-of-range [0, 10]
for row in conn.execute("""
    SELECT m.name, m.material_class,
           SUM(o.k < 0)     AS k_neg,
           SUM(o.k > 10)    AS k_hi,
           MAX(o.k)          AS k_max
    FROM optical_nk o
    JOIN materials m ON m.id = o.material_id
    WHERE o.k IS NOT NULL
    GROUP BY m.id
"""):
    name    = row["name"]
    k_neg   = row["k_neg"]  or 0
    k_hi    = row["k_hi"]   or 0
    k_max   = row["k_max"]
    is_metal = row["material_class"] == "metal"

    if k_neg > 0:
        record(FAIL, f"DB-4[{name}]", f"{k_neg} rows with k < 0 — nonphysical")
    elif k_hi > 0 and is_metal:
        record(WARN, f"DB-4[{name}]",
               f"{k_hi} rows with k > 10 (max={k_max:.4f}) — "
               f"physically real for metals at near-IR (free-carrier absorption)")
    elif k_hi > 0:
        record(FAIL, f"DB-4[{name}]",
               f"{k_hi} rows with k > 10 (max={k_max:.4f}) — unexpected for non-metal")
    else:
        if k_max is not None:
            record(PASS, f"DB-4[{name}]", f"k in [0, {k_max:.4e}]")

# DB-5  DPPC has n at 633 nm
dppc_row = conn.execute("SELECT id FROM materials WHERE name='DPPC'").fetchone()
dppc_id  = dppc_row[0] if dppc_row else None
dppc_633 = None
if dppc_id:
    dppc_633 = conn.execute(
        "SELECT * FROM optical_nk WHERE material_id=? AND ABS(wavelength_nm-633)<1",
        (dppc_id,)
    ).fetchone()

if dppc_633:
    record(PASS, "DB-5[DPPC@633nm]",
           f"n={dppc_633['n']}, k={dppc_633['k']}, "
           f"src={str(dppc_633['source_ref'])[:40]}")
else:
    record(FAIL, "DB-5[DPPC@633nm]", "no row near 633 nm — INSERT required")

conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# CODE CHECKS  (static — no import or exec)
# ─────────────────────────────────────────────────────────────────────────────

src = Path(CODE).read_text()
lines = src.splitlines()

def find_lines(pattern: str) -> list[int]:
    """Return 1-based line numbers matching a regex."""
    return [i + 1 for i, ln in enumerate(lines) if re.search(pattern, ln)]

# CODE-1  µm→nm conversion is explicit (multiply by 1000, not assumed)
um_to_nm_sites = find_lines(r"\*\s*1000")
div_sites       = find_lines(r"/ 1000")
um_var_sites    = find_lines(r"_um\b")
if um_to_nm_sites and div_sites and um_var_sites:
    record(PASS, "CODE-1[um→nm]",
           f"explicit *1000 at lines {um_to_nm_sites[:3]}; "
           f"_um variables at lines {um_var_sites[:3]}")
elif um_to_nm_sites:
    record(WARN, "CODE-1[um→nm]",
           f"*1000 present (lines {um_to_nm_sites}) but no _um-named variables")
else:
    record(FAIL, "CODE-1[um→nm]", "no explicit µm→nm conversion found")

# CODE-2  Formula 1/2 use  n² = 1 + c₀ + Σ  (not n² = c₀ + Σ)
correct_init = find_lines(r"np\.full_like\(lam,\s*1\.0\s*\+\s*c\[0\]\)")
wrong_init   = find_lines(r"np\.full_like\(lam,\s*c\[0\]\)")
if correct_init and not wrong_init:
    record(PASS, "CODE-2[formula-init]",
           f"n²=1+c₀+Σ confirmed at lines {correct_init}")
elif correct_init and wrong_init:
    record(WARN, "CODE-2[formula-init]",
           f"correct init at {correct_init}; possible wrong init also at {wrong_init}")
else:
    record(FAIL, "CODE-2[formula-init]",
           "could not confirm n²=1+c₀+Σ initialisation pattern")

# CODE-3a  Missing k stored as Python None → SQL NULL  (not 0.0)
null_guard = find_lines(r"k_val\s*=\s*None\s+if")
if null_guard:
    record(PASS, "CODE-3a[k-null-guard]",
           f"None-if guard found at line(s) {null_guard}")
else:
    record(FAIL, "CODE-3a[k-null-guard]",
           "no None-if guard for k — absent k may be stored as 0.0")

# CODE-3b  The formula evaluators return None for k, not 0.0
formula_ret_none = find_lines(r"return\s+np\.sqrt.*,\s*None")
if len(formula_ret_none) >= 3:
    record(PASS, "CODE-3b[formula-k-none]",
           f"formula evaluators return None for k at {len(formula_ret_none)} sites "
           f"(lines {formula_ret_none[:3]}…)")
else:
    record(WARN, "CODE-3b[formula-k-none]",
           f"only {len(formula_ret_none)} 'return …, None' in eval_formula — "
           f"check all formula branches")

# ─────────────────────────────────────────────────────────────────────────────
# PRINT REPORT
# ─────────────────────────────────────────────────────────────────────────────

WIDTH = 88
counts = {PASS: 0, WARN: 0, FAIL: 0}
for s, _, _ in results:
    counts[s] = counts.get(s, 0) + 1

print("=" * WIDTH)
print(f"  AUDIT REPORT — {DB}")
print(f"             — {CODE}")
print("=" * WIDTH)
for status, cid, detail in results:
    tag = f"[{status}]"
    indent = " " * (len(tag) + 2 + len(cid) + 3)
    words  = detail.split()
    lines_out, line = [], []
    length = 0
    for w in words:
        if length + len(w) + 1 > 68 and line:
            lines_out.append(" ".join(line))
            line, length = [], 0
        line.append(w)
        length += len(w) + 1
    if line:
        lines_out.append(" ".join(line))
    first = lines_out[0] if lines_out else ""
    rest  = ("\n" + indent).join(lines_out[1:])
    body  = first + (("\n" + indent + rest) if rest else "")
    print(f"  {tag:<6}  {cid:<28}  {body}")

print("-" * WIDTH)
print(f"  {counts[PASS]} PASS  |  {counts[WARN]} WARN  |  {counts[FAIL]} FAIL")
print("=" * WIDTH)

# ─────────────────────────────────────────────────────────────────────────────
# REMEDIATION — INSERT DPPC @ 633 nm if missing
# ─────────────────────────────────────────────────────────────────────────────

print()
if dppc_633:
    print("REMEDIATION: DPPC@633nm already present — no INSERT needed.")
else:
    print("REMEDIATION: Inserting DPPC n=1.48 k=NULL @ 633 nm …")
    conn2 = sqlite3.connect(DB)
    if dppc_id is None:
        cur = conn2.execute(
            "INSERT INTO materials (name, formula, material_class, notes) VALUES (?,?,?,?)",
            ("DPPC", "C40H80NO8P", "lipid",
             "Dipalmitoylphosphatidylcholine; lipid bilayer model."),
        )
        dppc_id = cur.lastrowid

    conn2.execute(
        """
        INSERT INTO optical_nk
            (material_id, wavelength_nm, n, k, source_ref, temperature_C)
        VALUES (?, 633.0, 1.48, NULL, ?, 25.0)
        """,
        (dppc_id,
         "Chou et al. Biophys J 2010 doi:10.1016/j.bpj.2010.07.026"),
    )
    conn2.commit()

    inserted = conn2.execute(
        "SELECT * FROM optical_nk WHERE material_id=? AND wavelength_nm=633.0",
        (dppc_id,)
    ).fetchone()
    conn2.close()

    if inserted:
        print(f"  Inserted: id={inserted[0]}, n={inserted[3]}, k={inserted[4]}")
        print("  DONE — re-run audit to confirm DB-5 becomes PASS.")
    else:
        print("  ERROR: INSERT appeared to succeed but row not found on re-query.")
