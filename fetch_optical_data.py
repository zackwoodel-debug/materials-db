#!/usr/bin/env python3
"""
fetch_optical_data.py
=====================
Clone the refractiveindex.info YAML database, parse n,k optical data for
selected soft-matter / substrate materials, and store everything in a
structured SQLite database (materials.db).

Materials: Water, Gold, SiO2, Polystyrene, DPPC (lipid)

Database schema
---------------
materials  : id, name, formula, material_class, notes
optical_nk : id, material_id (FK), wavelength_nm, n, k, source_ref, temperature_C
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import yaml

# ─── Configuration ────────────────────────────────────────────────────────────

DB_FILE  = "materials.db"
REPO_URL = "https://github.com/polyanskiy/refractiveindex.info-database.git"
REPO_DIR = "refractiveindex_db"

WL_MIN_NM = 200.0    # fetch window – ultraviolet
WL_MAX_NM = 3000.0   # fetch window – near-infrared
N_FORMULA = 500      # sample points for formula-based dispersion entries

# Each entry lists preferred YAML files (relative to the data/ root) in order
# of preference, then fallback search directories.
MATERIALS: List[dict] = [
    dict(
        name="Water",
        formula="H2O",
        material_class="solvent",
        notes="Hale & Querry 1973; broad UV–IR coverage; essential solvent reference",
        candidates=[
            "main/H2O/nk/Hale.yml",
            "main/H2O/nk/Segelstein.yml",
            "main/H2O/nk/Daimon-19.0C.yml",
        ],
        search_dirs=["main/H2O/nk", "main/H2O/n"],
    ),
    dict(
        name="Gold",
        formula="Au",
        material_class="metal",
        notes="Johnson & Christy 1972; 188–1937 nm; SPR substrate reference",
        candidates=[
            "main/Au/nk/Johnson.yml",
            "main/Au/nk/McPeak.yml",
            "main/Au/nk/Rakic-LD.yml",
        ],
        search_dirs=["main/Au/nk"],
    ),
    dict(
        name="SiO2",
        formula="SiO2",
        material_class="oxide",
        notes="Malitson 1965; fused silica 210–6700 nm; XRR/ellipsometry substrate",
        candidates=[
            "main/SiO2/nk/Malitson.yml",
            "main/SiO2/nk/Philipp.yml",
            "main/SiO2/nk/Popova.yml",
            "main/SiO2/nk/Lemarchand.yml",
        ],
        search_dirs=["main/SiO2/nk", "main/SiO2/n"],
    ),
    dict(
        name="Polystyrene",
        formula="(C8H8)n",
        material_class="polymer",
        notes="Sultanova 2009; visible-range dispersion; common NP / thin-film material",
        candidates=[
            "organic/(C8H8)n - polystyrene/nk/Sultanova.yml",
            "organic/(C8H8)n - polystyrene/nk/Zhang.yml",
            "organic/(C8H8)n - polystyrene/nk/Inagaki.yml",
        ],
        search_dirs=[
            "organic/(C8H8)n - polystyrene/nk",
            "organic/(C8H8)n - polystyrene/n",
        ],
    ),
    dict(
        name="DPPC",
        formula="C40H80NO8P",
        material_class="lipid",
        notes=(
            "Dipalmitoylphosphatidylcholine; lipid bilayer model. "
            "Not in refractiveindex.info — see Chou et al. Biophys J 2010 "
            "or van der Meer et al. J Phys Chem B 2019 for n,k values."
        ),
        candidates=[
            "organic/lipids/DPPC.yml",
            "organic/phospholipids/DPPC.yml",
        ],
        search_dirs=["organic/lipids", "organic/phospholipids"],
    ),
]


# ─── Repository access ────────────────────────────────────────────────────────

def clone_repo(repo_dir: str) -> Path:
    """Shallow-clone the database repo (once); return path to data/ directory."""
    if not Path(repo_dir).exists():
        print(f"Cloning refractiveindex.info-database (shallow, ~200 MB) …")
        subprocess.run(
            ["git", "clone", "--depth=1", REPO_URL, repo_dir],
            check=True,
        )
        print("Clone complete.\n")
    else:
        print(f"Using cached repo at '{repo_dir}/'.\n")

    for sub in ["database/data", "data"]:
        p = Path(repo_dir) / sub
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot find data/ directory under {repo_dir}/")


def find_yaml(data_root: Path, mat: dict) -> Optional[Path]:
    """Return the best YAML file for a material, or None if absent."""
    for rel in mat["candidates"]:
        p = data_root / rel
        if p.exists():
            return p
    for d in mat.get("search_dirs", []):
        dp = data_root / d
        if dp.is_dir():
            ymls = sorted(p for p in dp.glob("*.yml") if p.name != "about.yml")
            if ymls:
                return ymls[0]
    return None


# ─── Dispersion formula evaluators ───────────────────────────────────────────
# Formula reference: https://refractiveindex.info/about
#
# Convention in the current database: c₀ is an additive offset to n², with
# c₀ = 0 meaning the standard Sellmeier form  n² = 1 + Σ Bᵢλ²/(λ²−Cᵢ).
# Hence Formula 1/2 start from  n² = 1 + c₀  (not just c₀).

def _coeffs(block: dict) -> np.ndarray:
    return np.array([float(x) for x in str(block["coefficients"]).split()])


def eval_formula(
    block: dict, lam: np.ndarray
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Evaluate a refractiveindex.info formula block at wavelengths *lam* (µm).
    Returns (n_array, k_array_or_None).
    """
    ftype = block["type"]
    c = _coeffs(block)

    if ftype == "formula 1":
        # Sellmeier:  n² = 1 + c₀ + Σ cᵢ·λ²/(λ²−cᵢ₊₁²)
        n2 = np.full_like(lam, 1.0 + c[0])
        for i in range(1, len(c) - 1, 2):
            n2 = n2 + c[i] * lam**2 / (lam**2 - c[i + 1] ** 2)
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 2":
        # Sellmeier-2:  n² = 1 + c₀ + Σ cᵢ·λ²/(λ²−cᵢ₊₁)   (Cᵢ not squared)
        n2 = np.full_like(lam, 1.0 + c[0])
        for i in range(1, len(c) - 1, 2):
            n2 = n2 + c[i] * lam**2 / (lam**2 - c[i + 1])
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 3":
        # Polynomial in n²:  n² = Σ cᵢ·λ^cᵢ₊₁
        n2 = np.zeros_like(lam)
        for i in range(0, len(c) - 1, 2):
            n2 = n2 + c[i] * lam ** c[i + 1]
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 4":
        # Extended Sellmeier (same pair structure as F1)
        n2 = np.full_like(lam, 1.0 + c[0])
        for i in range(1, len(c) - 1, 2):
            n2 = n2 + c[i] * lam**2 / (lam**2 - c[i + 1] ** 2)
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 5":
        # Cauchy:  n = Σ cᵢ·λ^cᵢ₊₁
        n = np.zeros_like(lam)
        for i in range(0, len(c) - 1, 2):
            n = n + c[i] * lam ** c[i + 1]
        return n, None

    if ftype == "formula 6":
        # Gases:  n−1 = c₀ + Σ cᵢ/(cᵢ₊₁−λ⁻²)
        n_m1 = np.full_like(lam, c[0])
        for i in range(1, len(c) - 1, 2):
            n_m1 = n_m1 + c[i] / (c[i + 1] - lam**-2)
        return 1.0 + n_m1, None

    if ftype == "formula 7":
        # Herzberger
        A, B, C, D, E, F = (float(c[i]) if i < len(c) else 0.0 for i in range(6))
        L = lam**2 - 0.028
        n = A + B / L + C / L**2 + D * lam**2 + E * lam**4 + F * lam**6
        return n, None

    raise ValueError(f"Unsupported formula type: '{ftype}'")


# ─── YAML parser ──────────────────────────────────────────────────────────────

def _parse_table(data_str: str, ncols: int) -> np.ndarray:
    rows = []
    for line in data_str.strip().splitlines():
        parts = line.split()
        if len(parts) >= ncols:
            try:
                rows.append([float(x) for x in parts[:ncols]])
            except ValueError:
                pass
    return np.array(rows) if rows else np.zeros((0, ncols))


def parse_file(
    yaml_path: Path,
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], str, Optional[float]]:
    """
    Parse a refractiveindex.info YAML file.

    Returns
    -------
    wavelengths_nm : 1-D array, sorted ascending
    n              : 1-D array (real refractive index)
    k              : 1-D array or None  (extinction coefficient; None → absent)
    source_ref     : str  (truncated to 512 chars)
    temperature_C  : float or None
    """
    with open(yaml_path) as fh:
        raw = yaml.safe_load(fh)

    refs = raw.get("REFERENCES") or raw.get("COMMENTS") or ""
    if isinstance(refs, list):
        refs = " | ".join(str(r) for r in refs)
    refs = str(refs)[:512]

    # Temperature heuristic from filename, e.g. "Daimon-19.0C.yml"
    temp: Optional[float] = None
    m = re.search(r"[-_](\d+(?:\.\d+)?)[Cc](?:\b|$)", yaml_path.stem)
    if m:
        temp = float(m.group(1))
    # Also check the CONDITIONS block
    cond = raw.get("CONDITIONS") or {}
    if isinstance(cond, dict) and "temperature" in cond and temp is None:
        try:
            t_k = float(cond["temperature"])
            temp = t_k - 273.15 if t_k > 200 else t_k  # assume Kelvin if > 200
        except (ValueError, TypeError):
            pass

    wl_min_um = WL_MIN_NM / 1000.0
    wl_max_um = WL_MAX_NM / 1000.0

    n_wl: List[float] = []
    n_val: List[float] = []
    k_wl: List[float] = []
    k_val: List[float] = []

    for block in raw.get("DATA", []):
        btype = str(block.get("type", "")).strip()

        if btype == "tabulated nk":
            arr = _parse_table(block["data"], 3)
            if arr.shape[0] == 0:
                continue
            mask = (arr[:, 0] >= wl_min_um) & (arr[:, 0] <= wl_max_um)
            n_wl.extend((arr[mask, 0] * 1000).tolist())
            n_val.extend(arr[mask, 1].tolist())
            k_wl.extend((arr[mask, 0] * 1000).tolist())
            k_val.extend(arr[mask, 2].tolist())

        elif btype == "tabulated n":
            arr = _parse_table(block["data"], 2)
            if arr.shape[0] == 0:
                continue
            mask = (arr[:, 0] >= wl_min_um) & (arr[:, 0] <= wl_max_um)
            n_wl.extend((arr[mask, 0] * 1000).tolist())
            n_val.extend(arr[mask, 1].tolist())

        elif btype == "tabulated k":
            arr = _parse_table(block["data"], 2)
            if arr.shape[0] == 0:
                continue
            mask = (arr[:, 0] >= wl_min_um) & (arr[:, 0] <= wl_max_um)
            k_wl.extend((arr[mask, 0] * 1000).tolist())
            k_val.extend(arr[mask, 1].tolist())

        elif btype.startswith("formula"):
            wr = block.get("wavelength_range", f"{wl_min_um} {wl_max_um}")
            parts = str(wr).split()
            lo = max(float(parts[0]), wl_min_um)
            hi = min(float(parts[1]), wl_max_um)
            if lo >= hi:
                continue
            lam = np.linspace(lo, hi, N_FORMULA)
            try:
                n_f, k_f = eval_formula(block, lam)
            except (ValueError, ZeroDivisionError, FloatingPointError) as exc:
                print(f"    [formula warn] {exc}")
                continue
            n_wl.extend((lam * 1000).tolist())
            n_val.extend(n_f.tolist())
            if k_f is not None:
                k_wl.extend((lam * 1000).tolist())
                k_val.extend(k_f.tolist())

    if not n_wl:
        raise ValueError("No n data found in any DATA block")

    # Sort by wavelength
    n_wl_a = np.array(n_wl)
    n_val_a = np.array(n_val)
    idx = np.argsort(n_wl_a)
    n_wl_a = n_wl_a[idx]
    n_val_a = n_val_a[idx]

    k_out: Optional[np.ndarray] = None
    if k_wl:
        k_wl_a = np.array(k_wl)
        k_val_a = np.array(k_val)
        kidx = np.argsort(k_wl_a)
        # Interpolate k onto the n wavelength grid; NaN outside k range
        k_out = np.interp(
            n_wl_a, k_wl_a[kidx], k_val_a[kidx], left=np.nan, right=np.nan
        )

    return n_wl_a, n_val_a, k_out, refs, temp


# ─── Database schema & helpers ────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    formula        TEXT,
    material_class TEXT,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS optical_nk (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id),
    wavelength_nm  REAL    NOT NULL,
    n              REAL    NOT NULL,
    k              REAL,               -- NULL when k data is absent for this material
    source_ref     TEXT,
    temperature_C  REAL
);

CREATE INDEX IF NOT EXISTS idx_nk_mat ON optical_nk(material_id);
CREATE INDEX IF NOT EXISTS idx_nk_wl  ON optical_nk(wavelength_nm);
"""


def setup_db(path: str) -> sqlite3.Connection:
    if Path(path).exists():
        Path(path).unlink()
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def insert_material(conn: sqlite3.Connection, mat: dict) -> int:
    cur = conn.execute(
        "INSERT INTO materials (name, formula, material_class, notes) VALUES (?,?,?,?)",
        (mat["name"], mat["formula"], mat["material_class"], mat["notes"]),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def insert_nk(
    conn: sqlite3.Connection,
    mat_id: int,
    wl: np.ndarray,
    n: np.ndarray,
    k: Optional[np.ndarray],
    ref: str,
    temp: Optional[float],
) -> int:
    rows = []
    for i in range(len(wl)):
        k_val: Optional[float] = None
        if k is not None:
            kv = float(k[i])
            k_val = None if (np.isnan(kv) or np.isinf(kv)) else kv
        rows.append((mat_id, float(wl[i]), float(n[i]), k_val, ref, temp))
    conn.executemany(
        "INSERT INTO optical_nk "
        "(material_id, wavelength_nm, n, k, source_ref, temperature_C) "
        "VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(conn: sqlite3.Connection) -> None:
    W = 90
    print("\n" + "=" * W)
    print(
        f"  {'Material':<14}  {'WL range (nm)':<22}  "
        f"{'Points':>7}  {'k data':>14}  Source (truncated)"
    )
    print("-" * W)
    for mat_id, name, notes in conn.execute(
        "SELECT id, name, notes FROM materials ORDER BY id"
    ):
        row = conn.execute(
            """
            SELECT MIN(wavelength_nm), MAX(wavelength_nm), COUNT(*),
                   SUM(CASE WHEN k IS NOT NULL THEN 1 ELSE 0 END),
                   source_ref
            FROM optical_nk WHERE material_id=?
            """,
            (mat_id,),
        ).fetchone()

        if row[0] is None:
            print(f"  {name:<14}  NOT FOUND in refractiveindex.info database")
            hint = notes[:70] if notes else ""
            print(f"  {'':14}  Hint: {hint}")
        else:
            lo, hi, n_pts, k_pts, src = row
            k_str = f"{k_pts:,}/{n_pts:,}" if k_pts else "NULL (absent)"
            src_short = (src or "")[:30]
            print(
                f"  {name:<14}  {lo:7.1f} – {hi:7.1f} nm  "
                f"{n_pts:>7,}  {k_str:>14}  {src_short}"
            )
    print("=" * W + "\n")


# ─── Spot-check ───────────────────────────────────────────────────────────────

def spot_check(conn: sqlite3.Connection) -> None:
    """Print n (and k if available) at a few reference wavelengths for sanity."""
    checks = [
        ("Water",       633),
        ("Gold",        532),
        ("SiO2",        589),
        ("Polystyrene", 589),
    ]
    print("Spot-check (n, k) at reference wavelengths:")
    for name, wl in checks:
        row = conn.execute(
            """
            SELECT o.wavelength_nm, o.n, o.k
            FROM optical_nk o
            JOIN materials m ON m.id = o.material_id
            WHERE m.name = ?
            ORDER BY ABS(o.wavelength_nm - ?)
            LIMIT 1
            """,
            (name, wl),
        ).fetchone()
        if row:
            wl_a, n, k = row
            k_str = f"{k:.4f}" if k is not None else "NULL"
            print(f"  {name:<14} @ {wl_a:.1f} nm   n={n:.4f}  k={k_str}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    data_root = clone_repo(REPO_DIR)
    print(f"Data root : {data_root}")

    conn = setup_db(DB_FILE)
    print(f"Database  : {DB_FILE}\n")

    for mat in MATERIALS:
        label = f"{mat['name']} ({mat['formula']})"
        print(f"[{label}]")

        mat_id = insert_material(conn, mat)
        yaml_path = find_yaml(data_root, mat)

        if yaml_path is None:
            print("  ✗  Not found — material record inserted, no optical data.\n")
            continue

        print(f"  → {yaml_path.relative_to(data_root)}")

        try:
            wl, n, k, ref, temp = parse_file(yaml_path)
        except Exception as exc:
            print(f"  ✗  Parse error: {exc}\n")
            continue

        n_rows = insert_nk(conn, mat_id, wl, n, k, ref, temp)

        if k is not None:
            k_finite = int(np.sum(np.isfinite(k) & ~np.isnan(k)))
            k_info = f"k: {k_finite:,}/{n_rows:,} finite pts"
        else:
            k_info = "k: NULL (absent for this material)"

        print(f"  ✓  {n_rows:,} rows inserted  |  {k_info}\n")

    print_summary(conn)
    spot_check(conn)
    conn.close()
    print(f"\nDone → {DB_FILE}")


if __name__ == "__main__":
    main()
