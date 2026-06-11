"""
Generate data/ML_feature_matrix.parquet — one row per material, ML-ready.

Pipeline
--------
1. Pull every property from materials_normalized.db.
2. Pivot to one row per material; split dielectric into two distinct targets:
     target_dielectric_static   – ε₀  (DC / quasi-static measurement)
     target_dielectric_optical  – ε∞  (computed as n²−k² at 633 nm from optical_dispersion)
3. Build feature blocks:
     A. Physical scalars  (density, SLD)
     B. Optical scalars   (n and k at 633 nm; broadband mean/std)
     C. Chemical descriptors (exact_mass, TPSA, logP, …)
     D. Stoichiometric fractions per element (parsed from formula)
     E. 512-bit Morgan fingerprints (radius 2, from SMILES via RDKit)
4. StandardScale continuous features A–C; save params to ML_feature_metadata.json.
   Stoichiometric and fingerprint columns are already in [0,1] — not rescaled.
5. Write Parquet to data/ML_feature_matrix.parquet.

Missing target values → NaN float (not imputed). Missing feature values → NaN float.
No values are invented.
"""

from __future__ import annotations

import json
import re
import sqlite3
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

warnings.filterwarnings("ignore", category=FutureWarning)

DB_PATH       = Path(__file__).parent.parent / "data" / "materials_normalized.db"
OUT_PARQUET   = Path(__file__).parent.parent / "data" / "ML_feature_matrix.parquet"
OUT_METADATA  = Path(__file__).parent.parent / "data" / "ML_feature_metadata.json"

# Wavelength for single-point optical features (nm)
REF_WL_NM = 633.0
REF_WL_TOL = 5.0        # ± nm when looking up n / k at reference wavelength

# Frequency thresholds for regime classification
_OPTICAL_FREQ_HZ = 3e12  # ≥ this → optical regime


# ══════════════════════════════════════════════════════════════════════════════
# DB READERS
# ══════════════════════════════════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def load_materials(con) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT material_id, name, formula, smiles, inchikey, molecular_weight "
        "FROM materials ORDER BY material_id",
        con,
        index_col="material_id",
    )


def load_optical(con) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT material_id, wavelength_nm, n, k FROM optical_dispersion",
        con,
    )


def load_physical(con) -> pd.DataFrame:
    """All physical property rows; regime tag derives from frequency_hz / wavelength_nm."""
    return pd.read_sql(
        """
        SELECT material_id, density_g_cm3, xray_sld, neutron_sld,
               dielectric_constant, temperature_c, frequency_hz,
               wavelength_nm, measurement_regime
        FROM physical_properties
        """,
        con,
    )


def load_descriptors(con) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT material_id, exact_mass, tpsa, logp,
               heavy_atom_count, rotatable_bonds,
               hbond_donors, hbond_acceptors, aromatic_rings
        FROM chemical_descriptors
        """,
        con,
        index_col="material_id",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK A — PHYSICAL SCALARS
# ══════════════════════════════════════════════════════════════════════════════

def build_physical_features(phys: pd.DataFrame) -> pd.DataFrame:
    """One row per material; take first non-null value for each scalar."""
    out = {}
    for mid, grp in phys.groupby("material_id"):
        out[mid] = {
            "feat_density_g_cm3": _first_nonnull(grp, "density_g_cm3"),
            "feat_xray_sld":       _first_nonnull(grp, "xray_sld"),
            "feat_neutron_sld":    _first_nonnull(grp, "neutron_sld"),
        }
    return pd.DataFrame.from_dict(out, orient="index")


def _first_nonnull(df: pd.DataFrame, col: str):
    vals = df[col].dropna()
    return float(vals.iloc[0]) if len(vals) > 0 else np.nan


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK B — OPTICAL SCALARS
# ══════════════════════════════════════════════════════════════════════════════

def build_optical_features(opt: pd.DataFrame) -> pd.DataFrame:
    """
    For each material:
      feat_n_at_633nm  – n interpolated / nearest to 633 nm
      feat_k_at_633nm  – k at 633 nm (NaN if k column is NULL for all rows)
      feat_n_mean      – mean n across all wavelengths
      feat_n_std       – std  n across all wavelengths
      feat_k_mean      – mean k (only rows where k > 0)
      feat_k_std       – std  k (only rows where k > 0)
      feat_wl_min_nm   – min wavelength in dataset
      feat_wl_max_nm   – max wavelength in dataset
    """
    rows = {}
    for mid, grp in opt.groupby("material_id"):
        n_all = grp["n"].dropna()
        k_pos = grp.loc[grp["k"].notna() & (grp["k"] > 0), "k"]

        n633, k633 = _lookup_at_wl(grp, REF_WL_NM, REF_WL_TOL)
        rows[mid] = {
            "feat_n_at_633nm": n633,
            "feat_k_at_633nm": k633,
            "feat_n_mean":     float(n_all.mean()) if len(n_all) else np.nan,
            "feat_n_std":      float(n_all.std())  if len(n_all) > 1 else np.nan,
            "feat_k_mean":     float(k_pos.mean()) if len(k_pos) else np.nan,
            "feat_k_std":      float(k_pos.std())  if len(k_pos) > 1 else np.nan,
            "feat_wl_min_nm":  float(grp["wavelength_nm"].min()),
            "feat_wl_max_nm":  float(grp["wavelength_nm"].max()),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def _lookup_at_wl(
    grp: pd.DataFrame, wl: float, tol: float
) -> tuple[Optional[float], Optional[float]]:
    """Return (n, k) for the row nearest to wl within tolerance."""
    mask = (grp["wavelength_nm"] - wl).abs() <= tol
    near = grp.loc[mask]
    if near.empty:
        # no point within tolerance — take absolute nearest
        idx = (grp["wavelength_nm"] - wl).abs().idxmin()
        near = grp.loc[[idx]]
    n_val = near["n"].dropna()
    k_val = near["k"].dropna()
    n = float(n_val.iloc[0]) if len(n_val) else np.nan
    k = float(k_val.iloc[0]) if len(k_val) else np.nan
    return n, k


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK C — CHEMICAL DESCRIPTORS
# ══════════════════════════════════════════════════════════════════════════════

DESCRIPTOR_COLS = [
    "exact_mass", "tpsa", "logp",
    "heavy_atom_count", "rotatable_bonds",
    "hbond_donors", "hbond_acceptors", "aromatic_rings",
]


def build_descriptor_features(desc: pd.DataFrame) -> pd.DataFrame:
    renamed = {c: f"feat_{c}" for c in DESCRIPTOR_COLS if c in desc.columns}
    out = desc[[c for c in DESCRIPTOR_COLS if c in desc.columns]].rename(columns=renamed)
    return out.astype(float)


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK D — STOICHIOMETRIC FEATURES
# ══════════════════════════════════════════════════════════════════════════════

# Standard periodic table symbols (first 94 elements, enough for all materials here)
_ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*)")
_POLYMER_REPEAT = re.compile(r"^\((.+)\)[n\d]+$")  # e.g. (C2H6OSi)n


def parse_formula(formula: Optional[str]) -> dict[str, float]:
    """
    Parse a chemical formula string into {element: count} dict.
    Handles simple formulas, ionic fragments (splits on '.'), and
    polymer repeat units like (C2H6OSi)n.
    Returns mole-fraction normalized dict (values sum to 1.0).
    Returns {} if formula is None or unparseable.
    """
    if not formula:
        return {}

    # Unwrap polymer repeat unit
    m = _POLYMER_REPEAT.match(formula.strip())
    if m:
        formula = m.group(1)

    # Split ionic multi-fragment formulas (e.g. "[O-2].[Al+3].[Al+3]")
    fragments = re.split(r"\.", formula)
    counts: dict[str, float] = {}
    for frag in fragments:
        # Strip charge notation and brackets
        frag_clean = re.sub(r"[\[\]+\-\d?](?=[A-Z]|$)", "", frag)
        frag_clean = re.sub(r"\[", "", frag_clean)
        frag_clean = re.sub(r"\]", "", frag_clean)
        for sym, num in _ELEMENT_RE.findall(frag_clean):
            if not sym:
                continue
            n = int(num) if num else 1
            counts[sym] = counts.get(sym, 0) + n

    total = sum(counts.values())
    if total == 0:
        return {}
    return {el: cnt / total for el, cnt in counts.items()}


def build_stoich_features(mats: pd.DataFrame) -> pd.DataFrame:
    """
    One row per material_id; columns feat_stoich_<Element>.
    Values are element mole fractions (0–1).  Missing → 0.0.
    """
    all_fracs: dict[int, dict[str, float]] = {}
    all_elements: set[str] = set()

    for mid, row in mats.iterrows():
        fracs = parse_formula(row.get("formula"))
        all_fracs[mid] = fracs
        all_elements.update(fracs.keys())

    # Sort for reproducibility
    elements = sorted(all_elements)
    records = []
    for mid in mats.index:
        fracs = all_fracs.get(mid, {})
        records.append({f"feat_stoich_{el}": fracs.get(el, 0.0) for el in elements})

    df = pd.DataFrame(records, index=mats.index)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK E — MORGAN FINGERPRINTS
# ══════════════════════════════════════════════════════════════════════════════

FP_BITS   = 512
FP_RADIUS = 2


def build_morgan_fingerprints(mats: pd.DataFrame) -> pd.DataFrame:
    """
    512-bit radius-2 Morgan fingerprints from SMILES.
    Returns NaN rows for materials without valid SMILES.
    Columns: feat_fp_000 … feat_fp_511
    """
    try:
        from rdkit import Chem
        from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
        _morgan_gen = GetMorganGenerator(radius=FP_RADIUS, fpSize=FP_BITS)
        rdkit_ok = True
    except ImportError:
        rdkit_ok = False
        _morgan_gen = None

    fp_cols = [f"feat_fp_{i:03d}" for i in range(FP_BITS)]
    rows: dict[int, list] = {}

    for mid, row in mats.iterrows():
        smiles = row.get("smiles")
        if not rdkit_ok or not smiles:
            rows[mid] = [np.nan] * FP_BITS
            continue
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                rows[mid] = [np.nan] * FP_BITS
                continue
            fp = _morgan_gen.GetFingerprintAsNumPy(mol)
            rows[mid] = list(fp.astype(float))
        except Exception:
            rows[mid] = [np.nan] * FP_BITS

    return pd.DataFrame.from_dict(rows, orient="index", columns=fp_cols)


# ══════════════════════════════════════════════════════════════════════════════
# TARGETS
# ══════════════════════════════════════════════════════════════════════════════

def _is_optical_row(row) -> bool:
    """True if this physical_properties row was measured at optical frequency."""
    if row["measurement_regime"] == "optical":
        return True
    if pd.notna(row["wavelength_nm"]):
        return True
    freq = row["frequency_hz"]
    if pd.notna(freq) and float(freq) >= _OPTICAL_FREQ_HZ:
        return True
    return False


def _is_static_row(row) -> bool:
    """True if this is a DC / quasi-static measurement."""
    if row["measurement_regime"] in ("static", "low_frequency"):
        return True
    freq = row["frequency_hz"]
    if pd.notna(freq) and float(freq) < _OPTICAL_FREQ_HZ:
        return True
    # freq = 0 or NULL and no wavelength → treat as static
    if pd.isna(row["frequency_hz"]) and pd.isna(row["wavelength_nm"]):
        return True
    return False


def build_targets(phys: pd.DataFrame, opt: pd.DataFrame) -> pd.DataFrame:
    """
    target_dielectric_static   : DC / low-freq ε from physical_properties
    target_dielectric_optical  : ε∞ = n²−k² computed at 633 nm from optical_dispersion
    target_n_at_633nm          : n at 633 nm
    target_k_at_633nm          : k at 633 nm
    target_density             : density_g_cm3
    """
    all_mids = pd.concat([phys["material_id"], opt["material_id"]]).unique()
    records: dict[int, dict] = {mid: {} for mid in all_mids}

    # ── static dielectric ────────────────────────────────────────────────────
    for mid, grp in phys.groupby("material_id"):
        eps_col = grp["dielectric_constant"].dropna()
        if eps_col.empty:
            records[mid]["target_dielectric_static"] = np.nan
        else:
            # Filter to static / low-freq rows
            static_rows = grp[grp.apply(_is_static_row, axis=1)]
            eps_static = static_rows["dielectric_constant"].dropna()
            if not eps_static.empty:
                # Prefer DC (freq=0 or null) over 1 kHz
                dc_mask = (
                    static_rows["frequency_hz"].isna() |
                    (static_rows["frequency_hz"] == 0.0)
                )
                dc_vals = static_rows.loc[dc_mask, "dielectric_constant"].dropna()
                val = float(dc_vals.iloc[0]) if len(dc_vals) else float(eps_static.iloc[0])
                records[mid]["target_dielectric_static"] = val
            else:
                records[mid]["target_dielectric_static"] = np.nan

    # ── optical dielectric = ε∞ computed from optical data ──────────────────
    for mid, grp in opt.groupby("material_id"):
        n633, k633 = _lookup_at_wl(grp, REF_WL_NM, REF_WL_TOL)
        if np.isnan(n633):
            records[mid]["target_dielectric_optical"] = np.nan
        else:
            k = k633 if not np.isnan(k633) else 0.0
            records[mid]["target_dielectric_optical"] = float(n633**2 - k**2)

    # ── n / k at 633 nm ──────────────────────────────────────────────────────
    for mid, grp in opt.groupby("material_id"):
        n633, k633 = _lookup_at_wl(grp, REF_WL_NM, REF_WL_TOL)
        records[mid]["target_n_at_633nm"] = n633
        records[mid]["target_k_at_633nm"] = k633

    # ── density ──────────────────────────────────────────────────────────────
    for mid, grp in phys.groupby("material_id"):
        d = grp["density_g_cm3"].dropna()
        records[mid]["target_density"] = float(d.iloc[0]) if len(d) else np.nan

    return pd.DataFrame.from_dict(records, orient="index")


# ══════════════════════════════════════════════════════════════════════════════
# SCALING
# ══════════════════════════════════════════════════════════════════════════════

# Columns that get StandardScaled (continuous, variable magnitude)
_SCALE_PREFIXES = ("feat_density", "feat_xray", "feat_neutron",
                   "feat_n_", "feat_k_", "feat_wl_",
                   "feat_exact", "feat_tpsa", "feat_logp",
                   "feat_heavy", "feat_rotatable", "feat_hbond", "feat_aromatic")


def _should_scale(col: str) -> bool:
    return any(col.startswith(p) for p in _SCALE_PREFIXES)


def fit_and_scale(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Fit StandardScaler on continuous feature columns.
    Returns (scaled_df, scaler_params_dict).
    Columns with std=0 (or all-NaN) are left unchanged and flagged.
    """
    scale_cols = [c for c in df.columns if _should_scale(c)]
    scaler_params: dict[str, dict] = {}
    df_out = df.copy()

    for col in scale_cols:
        vals = df[col].dropna().astype(float)
        if len(vals) < 2:
            scaler_params[col] = {"mean": float("nan"), "std": float("nan"),
                                  "note": "too_few_values_skipped"}
            continue
        mu   = float(vals.mean())
        sigma = float(vals.std(ddof=0))
        scaler_params[col] = {"mean": mu, "std": sigma}
        if sigma > 1e-12:
            df_out[col] = (df[col] - mu) / sigma

    return df_out, scaler_params


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"[ml_matrix] database: {DB_PATH}")
    con = _connect()

    mats  = load_materials(con)
    opt   = load_optical(con)
    phys  = load_physical(con)
    desc  = load_descriptors(con)
    con.close()

    print(f"  materials: {len(mats)}  optical rows: {len(opt)}  physical rows: {len(phys)}")

    # ── build blocks ─────────────────────────────────────────────────────────
    print("[ml_matrix] building feature blocks …")
    blk_phys   = build_physical_features(phys)
    blk_opt    = build_optical_features(opt)
    blk_desc   = build_descriptor_features(desc)
    blk_stoich = build_stoich_features(mats)
    blk_fp     = build_morgan_fingerprints(mats)
    targets    = build_targets(phys, opt)

    # ── assemble ─────────────────────────────────────────────────────────────
    base = mats[["name", "formula", "smiles", "inchikey"]].copy()
    matrix = (
        base
        .join(targets,    how="left")
        .join(blk_phys,   how="left")
        .join(blk_opt,    how="left")
        .join(blk_desc,   how="left")
        .join(blk_stoich, how="left")
        .join(blk_fp,     how="left")
    )

    # ── scale continuous features ─────────────────────────────────────────────
    print("[ml_matrix] fitting StandardScaler on continuous features …")
    feat_cols    = [c for c in matrix.columns if c.startswith("feat_")]
    target_cols  = [c for c in matrix.columns if c.startswith("target_")]
    fp_cols      = [c for c in matrix.columns if c.startswith("feat_fp_")]
    stoich_cols  = [c for c in matrix.columns if c.startswith("feat_stoich_")]
    meta_cols    = ["name", "formula", "smiles", "inchikey"]

    matrix_scaled, scaler_params = fit_and_scale(matrix)

    # ── parquet export ────────────────────────────────────────────────────────
    print(f"[ml_matrix] writing {OUT_PARQUET} …")
    # Reset index so material_id becomes a column
    matrix_scaled.index.name = "material_id"
    table = pa.Table.from_pandas(matrix_scaled.reset_index(), preserve_index=False)
    pq.write_table(table, str(OUT_PARQUET), compression="snappy")

    # ── metadata JSON ─────────────────────────────────────────────────────────
    print(f"[ml_matrix] writing {OUT_METADATA} …")
    cont_feat_cols = [c for c in feat_cols if c not in fp_cols and c not in stoich_cols]

    missing_target_pct = {}
    for col in target_cols:
        n_nan = matrix_scaled[col].isna().sum()
        missing_target_pct[col] = round(100.0 * n_nan / len(matrix_scaled), 1)

    # Count materials with valid fingerprints
    fp_available = int((~matrix_scaled[fp_cols[0]].isna()).sum()) if fp_cols else 0

    stoich_elements = [c.replace("feat_stoich_", "") for c in stoich_cols]

    metadata = {
        "n_materials":           len(matrix_scaled),
        "n_features_total":      len(feat_cols),
        "n_features_continuous": len(cont_feat_cols),
        "n_features_stoich":     len(stoich_cols),
        "n_features_fp":         len(fp_cols),
        "fp_radius":             FP_RADIUS,
        "fp_bits":               FP_BITS,
        "fp_available_count":    fp_available,
        "optical_ref_wl_nm":     REF_WL_NM,
        "target_columns":        target_cols,
        "feature_columns":       cont_feat_cols,
        "stoich_columns":        stoich_cols,
        "fp_columns":            fp_cols,
        "stoich_elements":       stoich_elements,
        "missing_target_pct":    missing_target_pct,
        "scaler":                scaler_params,
    }
    with open(OUT_METADATA, "w") as fh:
        json.dump(metadata, fh, indent=2)

    # ── summary ───────────────────────────────────────────────────────────────
    print("\n[ml_matrix] SUMMARY")
    print(f"  shape            : {matrix_scaled.shape}")
    print(f"  parquet          : {OUT_PARQUET}")
    print(f"  metadata json    : {OUT_METADATA}")
    print(f"\n  Feature breakdown:")
    print(f"    continuous      : {len(cont_feat_cols)}")
    print(f"    stoichiometric  : {len(stoich_cols)}  ({len(stoich_elements)} elements: {stoich_elements})")
    print(f"    fingerprint     : {len(fp_cols)} bits  ({fp_available}/{len(mats)} materials have SMILES)")
    print(f"\n  Targets & missing%:")
    for col, pct in missing_target_pct.items():
        n_present = len(matrix_scaled) - int(round(pct * len(matrix_scaled) / 100))
        print(f"    {col:<36s}  {n_present:2d}/{len(matrix_scaled)} present  ({pct:.0f}% missing)")

    print("\n  Sample rows (targets only):")
    print(
        matrix_scaled[["name"] + target_cols]
        .to_string(index=True, float_format=lambda x: f"{x:8.3f}")
    )


if __name__ == "__main__":
    main()
