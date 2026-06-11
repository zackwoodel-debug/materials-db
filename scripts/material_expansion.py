#!/usr/bin/env python3
"""
scripts/material_expansion.py
===============================
Steps 1-6: Add 6 new materials + rebuild analysis + correlation matrices
+ Maxwell/CM plots + significance report.
"""

import io
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

import sqlite3

sys.path.insert(0, "src")
from materials_db.calculators.sld_calculator import (
    parse_formula, compute_xray_sld, compute_neutron_sld,
)

DB_PATH = "data/materials.db"
FIG_DIR = "figures"
RPT_DIR = "reports"
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(RPT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_mid(name):
    r = cur.execute("SELECT id FROM materials WHERE name=?", (name,)).fetchone()
    return r[0] if r else None

def skip(msg):
    print(f"  SKIP  {msg}")

def inserted(msg):
    print(f"  INSERT {msg}")

def pearson_safe(a, b):
    sub = pd.DataFrame({"a": a, "b": b}).dropna()
    n = len(sub)
    if n < 2:
        return float("nan"), float("nan"), n
    r, p = stats.pearsonr(sub["a"].astype(float), sub["b"].astype(float))
    return float(r), float(p), n

def n_needed_80pct(r):
    if abs(r) < 1e-9:
        return float("inf")
    return int(np.ceil(((1.96 + 0.842) / np.arctanh(abs(r))) ** 2 + 3))

def make_heatmap(df_num, title, path, min_pairs=4):
    valid = [c for c in df_num.columns if df_num[c].notna().sum() >= min_pairs]
    corr  = df_num[valid].corr(method="pearson")
    n_v   = len(valid)
    sz    = max(9, n_v * 1.0)
    fig, ax = plt.subplots(figsize=(sz, sz * 0.85))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    sns.heatmap(
        corr, mask=mask, annot=True, fmt=".2f",
        cmap="RdBu_r", vmin=-1, vmax=1,
        linewidths=0.35, square=True, ax=ax,
        annot_kws={"size": 8},
        cbar_kws={"label": "Pearson r", "shrink": 0.65},
    )
    ax.set_title(title, fontsize=12, pad=12)
    plt.xticks(rotation=45, ha="right", fontsize=8.5)
    plt.yticks(rotation=0, fontsize=8.5)
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")
    return corr


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — ADD 6 MATERIALS WITH FULL COVERAGE
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 1 — ADD 6 MATERIALS WITH FULL COVERAGE")
print("=" * 65)

# SLD calculation wavelengths used by existing calculated_slds rows
SLD_WL = [
    (0.07093, 17400.0),   # Mo Kα
    (0.15406,  8040.0),   # Cu Kα
]

NEW_MATS = [
    dict(name="PTFE",    formula="C2F4",       smiles="FC(F)=C(F)F",
         density=2.20, n_633=1.350, k_633=0.0,
         eps_real=2.10, eps_imag=None, freq_hz=1000.0,
         MW=100.02, material_class="polymer"),
    dict(name="PEEK",    formula="C19H12O3",
         smiles="O=Cc1ccc(Oc2ccc(Oc3ccccc3)cc2)cc1",
         density=1.32, n_633=1.650, k_633=0.0,
         eps_real=3.20, eps_imag=None, freq_hz=1000.0,
         MW=288.30, material_class="polymer"),
    dict(name="PVA",     formula="C2H4O",      smiles="C=CO",
         density=1.27, n_633=1.500, k_633=0.0,
         eps_real=10.80, eps_imag=None, freq_hz=1000.0,
         MW=44.05, material_class="polymer"),
    dict(name="Nylon66", formula="C12H22N2O2",
         smiles="O=C1CCCCC(=O)NCCCCCCN1",
         density=1.14, n_633=1.530, k_633=0.0,
         eps_real=3.50, eps_imag=None, freq_hz=1000.0,
         MW=226.32, material_class="polymer"),
    dict(name="Al2O3",   formula="Al2O3",      smiles=None,
         density=3.99, n_633=1.765, k_633=0.0,
         eps_real=9.80, eps_imag=None, freq_hz=1000.0,
         MW=101.96, material_class="oxide"),
    dict(name="ZnO",     formula="ZnO",        smiles=None,
         density=5.61, n_633=2.004, k_633=0.0010,
         eps_real=8.50, eps_imag=None, freq_hz=1000.0,
         MW=81.38, material_class="oxide"),
]

# RDKit descriptors (only for organics)
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDKIT_OK = True
except ImportError:
    RDKIT_OK = False
    print("  WARNING: RDKit not available; skipping chemical descriptor computation")

ORGANIC_DESCS = [
    "MolWt", "ExactMolWt", "MolLogP", "TPSA",
    "NumHDonors", "NumHAcceptors", "NumRotatableBonds",
    "NumAromaticRings", "NumHeavyAtoms", "FractionCSP3", "BertzCT",
]
# Descriptors that are invalid / meaningless for inorganics
INORGANIC_SKIP = {"MolLogP", "TPSA", "BertzCT"}

def rdkit_descriptors(smi, fallback_mw, is_inorganic=False):
    """Return dict of descriptors, using fallback_mw for MolWt/ExactMolWt."""
    d = {}
    if RDKIT_OK and smi:
        mol = Chem.MolFromSmiles(smi)
        if mol:
            d["MolWt"]             = Descriptors.MolWt(mol)
            d["ExactMolWt"]        = Descriptors.ExactMolWt(mol)
            d["MolLogP"]           = Descriptors.MolLogP(mol)
            d["TPSA"]              = float(rdMolDescriptors.CalcTPSA(mol))
            d["NumHDonors"]        = float(rdMolDescriptors.CalcNumHBD(mol))
            d["NumHAcceptors"]     = float(rdMolDescriptors.CalcNumHBA(mol))
            d["NumRotatableBonds"] = float(rdMolDescriptors.CalcNumRotatableBonds(mol))
            d["NumAromaticRings"]  = float(rdMolDescriptors.CalcNumAromaticRings(mol))
            d["NumHeavyAtoms"]     = float(mol.GetNumHeavyAtoms())
            d["FractionCSP3"]      = float(rdMolDescriptors.CalcFractionCSP3(mol))
            d["BertzCT"]           = Descriptors.BertzCT(mol)
    # Override MW with user-provided fallback (exact for repeat unit)
    d["MolWt"]      = fallback_mw
    d["ExactMolWt"] = fallback_mw
    # Remove invalid descriptors for inorganics
    if is_inorganic:
        for k in INORGANIC_SKIP:
            d.pop(k, None)
    return d

def upsert_descriptor(mid, name, val, src="manual"):
    existing = cur.execute(
        "SELECT id FROM chemical_descriptors WHERE material_id=? AND descriptor_name=?",
        (mid, name),
    ).fetchone()
    if existing:
        cur.execute(
            "UPDATE chemical_descriptors SET value=?, source_library=? WHERE id=?",
            (val, src, existing[0]),
        )
    else:
        cur.execute(
            "INSERT INTO chemical_descriptors (material_id, descriptor_name, value, source_library)"
            " VALUES (?,?,?,?)",
            (mid, name, val, src),
        )


# ── Purge invalid organic descriptors from existing inorganics ────────────────
INORGANIC_MIDS = {
    name: get_mid(name) for name in ("TiO2", "ITO")
}
print("\n  Purging invalid organic descriptors from TiO2 / ITO:")
for mat_name, mid in INORGANIC_MIDS.items():
    if mid is None:
        continue
    for desc in INORGANIC_SKIP:
        n_del = cur.execute(
            "DELETE FROM chemical_descriptors WHERE material_id=? AND descriptor_name=?",
            (mid, desc),
        ).rowcount
        if n_del:
            print(f"  DELETE {mat_name} [{desc}]")
conn.commit()

# ── Add measurement_regime to dielectrics if missing ─────────────────────────
cur.execute("PRAGMA table_info(dielectrics)")
dielectrics_cols = {r[1] for r in cur.fetchall()}
if "measurement_regime" not in dielectrics_cols:
    cur.execute("ALTER TABLE dielectrics ADD COLUMN measurement_regime TEXT")
    cur.execute("UPDATE dielectrics SET measurement_regime = 'low_frequency'")
    conn.commit()
    print("\n  Added measurement_regime to dielectrics table")

# ── Insert each material ──────────────────────────────────────────────────────
for m in NEW_MATS:
    name = m["name"]
    print(f"\n  ── {name} ──────────────────────────────────────────")

    # 1. materials table
    mid = get_mid(name)
    if mid is not None:
        skip(f"materials: {name} already exists (id={mid})")
    else:
        cur.execute(
            "INSERT INTO materials (name, formula, molecular_weight, density_g_cm3, material_class)"
            " VALUES (?,?,?,?,?)",
            (name, m["formula"], m["MW"], m["density"], m["material_class"]),
        )
        mid = cur.lastrowid
        inserted(f"materials: {name} → id={mid}")
    conn.commit()

    # 2. optical_nk at 633 nm
    exists_nk = cur.execute(
        "SELECT 1 FROM optical_nk WHERE material_id=? AND wavelength_nm=633.0",
        (mid,),
    ).fetchone()
    if exists_nk:
        skip(f"optical_nk: {name} @ 633nm")
    else:
        cur.execute(
            "INSERT INTO optical_nk (material_id, wavelength_nm, n, k)"
            " VALUES (?,633.0,?,?)",
            (mid, m["n_633"], m["k_633"] if m["k_633"] else None),
        )
        inserted(f"optical_nk: {name}  n={m['n_633']}  k={m['k_633']}")
    conn.commit()

    # 3. calculated_slds (two wavelengths)
    counts = parse_formula(m["formula"])
    for wl_nm, energy_ev in SLD_WL:
        exists_sld = cur.execute(
            "SELECT 1 FROM calculated_slds WHERE material_id=? AND wavelength_nm=?",
            (mid, wl_nm),
        ).fetchone()
        if exists_sld:
            skip(f"calculated_slds: {name} @ {wl_nm} nm")
        else:
            xsld  = compute_xray_sld(counts, m["density"], m["MW"])
            nsld  = compute_neutron_sld(counts, m["density"], m["MW"])
            cur.execute(
                "INSERT INTO calculated_slds"
                " (material_id, energy_ev, wavelength_nm, xray_sld_real,"
                "  neutron_sld_real)"
                " VALUES (?,?,?,?,?)",
                (mid, energy_ev, wl_nm, float(xsld.real), float(nsld)),
            )
            inserted(
                f"calculated_slds: {name} @ {wl_nm}nm  "
                f"xray={xsld.real:.5e}  neutron={nsld:.5e}"
            )
    conn.commit()

    # 4a. dielectric table (primary for analysis)
    exists_diel = cur.execute(
        "SELECT 1 FROM dielectric WHERE material_id=? AND frequency_hz=?",
        (mid, m["freq_hz"]),
    ).fetchone()
    if exists_diel:
        skip(f"dielectric: {name} @ {m['freq_hz']} Hz")
    else:
        cur.execute(
            "INSERT INTO dielectric"
            " (material_id, frequency_hz, dielectric_real, dielectric_imag,"
            "  temperature_C, measurement_regime, notes)"
            " VALUES (?,?,?,?,25.0,'low_frequency',?)",
            (mid, m["freq_hz"], m["eps_real"], m["eps_imag"],
             f"literature {int(m['freq_hz'])} Hz"),
        )
        inserted(
            f"dielectric: {name}  ε={m['eps_real']}  regime=low_frequency"
        )
    conn.commit()

    # 4b. dielectrics table (as specified)
    exists_diels = cur.execute(
        "SELECT 1 FROM dielectrics WHERE material_id=?", (mid,)
    ).fetchone()
    if exists_diels:
        skip(f"dielectrics: {name}")
    else:
        cur.execute(
            "INSERT INTO dielectrics"
            " (material_id, frequency_hz, real_permittivity,"
            "  imag_permittivity, temperature_C, measurement_regime)"
            " VALUES (?,?,?,?,25.0,'low_frequency')",
            (mid, m["freq_hz"], m["eps_real"], m["eps_imag"]),
        )
        inserted(f"dielectrics: {name}  ε={m['eps_real']}")
    conn.commit()

    # 5. chemical_descriptors
    is_inorg = m["material_class"] == "oxide" and name in ("Al2O3", "ZnO")
    src = "RDKit+manual" if (RDKIT_OK and m["smiles"]) else "manual_formula"
    desc_d = rdkit_descriptors(m["smiles"], m["MW"], is_inorganic=is_inorg)
    for desc_name, val in desc_d.items():
        upsert_descriptor(mid, desc_name, float(val), src)
    inserted(f"chemical_descriptors: {name}  {len(desc_d)} descriptors")
    conn.commit()

# ── Update material_class for existing materials per user spec ─────────────────
CLASS_UPDATES = {
    "Water": "biological", "DPPC": "biological", "BSA": "biological",
}
print("\n  Updating material_class in materials table:")
for name, cls in CLASS_UPDATES.items():
    mid = get_mid(name)
    if mid:
        old = cur.execute("SELECT material_class FROM materials WHERE id=?", (mid,)).fetchone()[0]
        if old != cls:
            cur.execute("UPDATE materials SET material_class=? WHERE id=?", (cls, mid))
            print(f"  UPDATE {name}: {old!r} → {cls!r}")
        else:
            skip(f"{name} material_class already '{cls}'")
conn.commit()

print(f"\n  dielectric table rows: {cur.execute('SELECT COUNT(*) FROM dielectric').fetchone()[0]}")
print(f"  dielectrics table rows: {cur.execute('SELECT COUNT(*) FROM dielectrics').fetchone()[0]}")
print(f"  materials table rows:  {cur.execute('SELECT COUNT(*) FROM materials').fetchone()[0]}")
print("✓ Step 1 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — REBUILD FLAT DATASET + PHYSICS FEATURES
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 2 — REBUILD FLAT DATASET + PHYSICS FEATURES")
print("=" * 65)

# Load previous null counts for delta
try:
    prev_df = pd.read_csv("analysis_dataset.csv")
    prev_nulls = prev_df.isnull().sum()
    prev_shape = prev_df.shape
except FileNotFoundError:
    prev_nulls = pd.Series(dtype=float)
    prev_shape = (0, 0)

# ── Build flat DataFrame ──────────────────────────────────────────────────────
mat_df = pd.read_sql(
    "SELECT id AS material_id, name, formula, molecular_weight AS MW_db,"
    "       density_g_cm3, material_class FROM materials",
    conn,
)

# Dielectric (from dielectric table — has measurement_regime)
diel_df = pd.read_sql(
    "SELECT material_id, dielectric_real, dielectric_imag,"
    "       frequency_hz AS diel_freq_hz, measurement_regime"
    " FROM dielectric"
    " ORDER BY material_id, frequency_hz",  # DC first → prefer lowest freq
    conn,
)
# One row per material: prefer DC (lowest freq)
diel_df = diel_df.sort_values("diel_freq_hz").groupby("material_id", as_index=False).first()

# Optical n,k at 633 nm
nk633 = pd.read_sql(
    "SELECT material_id, n AS n_633nm, k AS k_633nm FROM optical_nk"
    " WHERE wavelength_nm BETWEEN 630 AND 636"
    " ORDER BY material_id, ABS(wavelength_nm - 633.0)",
    conn,
)
nk633 = nk633.groupby("material_id", as_index=False).first()

# Optical at 785 nm
nk785 = pd.read_sql(
    "SELECT material_id, n AS n_785nm, k AS k_785nm FROM optical_nk"
    " WHERE wavelength_nm BETWEEN 780 AND 790"
    " ORDER BY material_id, ABS(wavelength_nm - 785.0)",
    conn,
)
nk785 = nk785.groupby("material_id", as_index=False).first()

# SLDs
sld_df = pd.read_sql(
    "SELECT material_id,"
    "  AVG(xray_sld_real)    AS xray_sld_real,"
    "  AVG(neutron_sld_real) AS neutron_sld_real"
    " FROM calculated_slds GROUP BY material_id",
    conn,
)

# Viscoelasticity
vis_df = pd.read_sql(
    "SELECT material_id,"
    "  AVG(storage_modulus_pa) AS storage_modulus_pa,"
    "  AVG(loss_modulus_pa)    AS loss_modulus_pa,"
    "  AVG(viscosity_mpa_s)    AS viscosity_mpa_s"
    " FROM viscoelasticity GROUP BY material_id",
    conn,
)

# Chemical descriptors (wide pivot, keep first when duplicated)
cd = pd.read_sql(
    "SELECT material_id, descriptor_name, value FROM chemical_descriptors", conn
)
cd_wide = (
    cd.pivot_table(index="material_id", columns="descriptor_name",
                   values="value", aggfunc="first")
    .reset_index()
)
cd_wide.columns.name = None
# Normalise MW/LogP column name variants
rename_cd = {}
for col in cd_wide.columns:
    if col in ("MolWt", "ExactMolWt", "exact_mass") and "MW" not in cd_wide.columns:
        rename_cd[col] = "MW"
    elif col in ("MolLogP", "logP") and "LogP" not in cd_wide.columns:
        rename_cd[col] = "LogP"
if rename_cd:
    cd_wide.rename(columns=rename_cd, inplace=True)
cd_wide = cd_wide.loc[:, ~cd_wide.columns.duplicated(keep="first")]

# Assemble
flat = mat_df.copy()
for part in [diel_df, nk633, nk785, sld_df, vis_df, cd_wide]:
    flat = flat.merge(part, on="material_id", how="left")

# Canonical MW: prefer MolWt (from chemical_descriptors/fallback) else MW_db
if "MW" not in flat.columns:
    flat["MW"] = flat["MW_db"]
else:
    flat["MW"] = flat["MW"].fillna(flat["MW_db"])

# ── Material class column for analysis ───────────────────────────────────────
CLASS_MAP = {
    "PTFE": "polymer", "PEEK": "polymer", "PVA": "polymer", "Nylon66": "polymer",
    "PMMA": "polymer", "Polystyrene": "polymer", "PDMS": "polymer", "PEI": "polymer",
    "SiO2": "oxide",  "TiO2": "oxide",   "Al2O3": "oxide",  "ZnO": "oxide",
    "ITO":  "oxide",
    "Gold": "metal",  "Silver": "metal", "Chromium": "metal",
    "BSA":  "biological", "DPPC": "biological", "Water": "biological",
}
flat["material_class"] = flat["name"].map(CLASS_MAP).fillna(flat["material_class"])

# ── Physics features ──────────────────────────────────────────────────────────
flat["n2"]        = flat["n_633nm"] ** 2
flat["f_LL"]      = (flat["n2"] - 1) / (flat["n2"] + 2)
flat["f_CM"]      = (flat["dielectric_real"] - 1) / (flat["dielectric_real"] + 2)
flat["molar_vol"] = flat["MW"] / flat["density_g_cm3"]
flat["f_LL_norm"] = flat["f_LL"] / flat["molar_vol"]
flat["f_CM_norm"] = flat["f_CM"] / flat["molar_vol"]

# Drop degenerate measurement_regime column from merge (keep in separate var)
flat_measurement = flat["measurement_regime"].copy() if "measurement_regime" in flat.columns else None

# Save
flat.to_csv("analysis_dataset.csv", index=False)
print(f"  Saved analysis_dataset.csv: {flat.shape[0]} rows × {flat.shape[1]} cols")

# Null count delta
new_nulls = flat.isnull().sum()
all_cols = sorted(set(list(prev_nulls.index) + list(new_nulls.index)))
print(f"\n  Null count delta (prev {prev_shape[0]} rows → now {flat.shape[0]} rows):")
print(f"  {'Column':<28} {'Prev':>6}  {'Now':>6}  {'Δ':>6}")
print("  " + "-" * 50)
for col in all_cols:
    pv = prev_nulls.get(col, "N/A")
    nv = new_nulls.get(col, "N/A")
    if pv == "N/A" and nv == "N/A":
        continue
    if isinstance(pv, float) and isinstance(nv, float):
        delta = int(nv - pv)
        flag = "  ↑ improved" if delta < 0 else ("  ↓ more nulls" if delta > 0 else "")
        print(f"  {col:<28} {int(pv):>6}  {int(nv):>6}  {delta:>+6}{flag}")
    else:
        print(f"  {col:<28} {str(pv):>6}  {str(nv):>6}  {'—':>6}")

diel_nonnull = flat["dielectric_real"].notna().sum()
print(f"\n  dielectric_real non-null: {diel_nonnull}/23  {'✓ ≥ 16' if diel_nonnull >= 16 else '✗ < 16 — CHECK'}")
print("✓ Step 2 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — FULL LOW-FREQUENCY CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 3 — FULL LOW-FREQUENCY CORRELATION MATRIX")
print("=" * 65)

lf = flat[flat["measurement_regime"] == "low_frequency"].copy()
print(f"  Low-frequency materials (N={len(lf)}): {lf['name'].tolist()}")

FEATURES_3 = [
    "dielectric_real", "n_633nm", "f_LL", "f_CM",
    "f_LL_norm", "f_CM_norm", "density_g_cm3", "xray_sld_real", "MW", "molar_vol",
]
available_3 = [f for f in FEATURES_3 if f in lf.columns]
min8 = {f: lf[f].notna().sum() for f in available_3}
print(f"\n  Feature coverage in low-freq subset:")
for f, n in min8.items():
    print(f"    {f:<22} {n}/{len(lf)}  {'OK' if n >= 8 else 'SKIP (< 8)'}")

use_3 = [f for f in available_3 if min8[f] >= 8]
print(f"\n  Features used in heatmap: {use_3}")

make_heatmap(
    lf[use_3].astype(float),
    "Low-Frequency Dielectric Correlation Matrix\n"
    f"(N={len(lf)} low-freq materials, all features ≥ 8 non-null)",
    f"{FIG_DIR}/corr_dielectric_final.png",
    min_pairs=4,
)

# Print r vs dielectric_real
print(f"\n  {'Feature':<22} {'r':>8}  {'p':>8}  {'N':>4}")
for feat in [f for f in use_3 if f != "dielectric_real"]:
    r, p, n = pearson_safe(lf[feat], lf["dielectric_real"])
    sig = "  ***" if p < 0.05 else ""
    print(f"  {feat:<22} {r:>+8.4f}  {p:>8.4f}  {n:>4}{sig}")
print("✓ Step 3 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — POLYMER-ONLY CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 4 — POLYMER-ONLY CORRELATION MATRIX")
print("=" * 65)

poly = flat[flat["material_class"] == "polymer"].copy()
print(f"  Polymer subset (N={len(poly)}): {poly['name'].tolist()}")

FEATURES_4 = [
    "dielectric_real", "n_633nm", "f_LL", "f_CM",
    "density_g_cm3", "MW", "LogP", "TPSA", "BertzCT", "molar_vol",
]
avail_4  = [f for f in FEATURES_4 if f in poly.columns]
cov_4    = {f: poly[f].notna().sum() for f in avail_4}
print(f"\n  Feature coverage in polymer subset:")
for f, n in cov_4.items():
    print(f"    {f:<22} {n}/{len(poly)}")

make_heatmap(
    poly[avail_4].astype(float),
    "Polymer-Only Dielectric Correlation Matrix\n"
    f"(N={len(poly)} polymers)",
    f"{FIG_DIR}/corr_dielectric_polymers.png",
    min_pairs=3,
)

# Identify strongest RDKit descriptor
rdkit_feats = [f for f in ["LogP", "TPSA", "BertzCT"] if f in poly.columns]
rdkit_corrs = {}
print(f"\n  RDKit descriptor correlations with dielectric_real:")
for feat in rdkit_feats:
    r, p, n = pearson_safe(poly[feat], poly["dielectric_real"])
    sig = "  ***" if p < 0.05 else ""
    print(f"    {feat:<12} r={r:>+7.4f}  p={p:.4f}  N={n}{sig}")
    if not np.isnan(r):
        rdkit_corrs[feat] = abs(r)
if rdkit_corrs:
    best_rdkit = max(rdkit_corrs, key=rdkit_corrs.get)
    print(f"\n  Strongest RDKit descriptor: {best_rdkit} (|r|={rdkit_corrs[best_rdkit]:.4f})")
print("✓ Step 4 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — MAXWELL / CLAUSIUS-MOSSOTTI VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 5 — MAXWELL / CLAUSIUS-MOSSOTTI VALIDATION")
print("=" * 65)

CLASS_COLORS = {
    "polymer":    "#1D9E75",
    "oxide":      "#378ADD",
    "biological": "#D85A30",
    "metal":      "#888780",
    "solvent":    "#9E559E",
    "semiconductor": "#C4A900",
}

def scatter_points(ax, df, x_col, y_col, label_col="name"):
    handles = {}
    for _, row in df.dropna(subset=[x_col, y_col]).iterrows():
        cls   = row.get("material_class", "other") or "other"
        color = CLASS_COLORS.get(cls, "#555555")
        m     = ax.scatter(row[x_col], row[y_col], color=color, s=70, zorder=3,
                           label=cls if cls not in handles else "")
        if cls not in handles:
            handles[cls] = m
        ax.annotate(
            row[label_col],
            (row[x_col], row[y_col]),
            xytext=(5, 3), textcoords="offset points", fontsize=9,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")],
        )
    return handles

# ── Plot 1: Maxwell relation ε vs n² ─────────────────────────────────────────
mx = flat[["name", "material_class", "n2", "dielectric_real"]].dropna()
print(f"\n  Maxwell plot: {len(mx)} materials with both n_633nm and dielectric_real")

fig, ax = plt.subplots(figsize=(10, 8))
handles = scatter_points(ax, mx, "n2", "dielectric_real")

# Regression forced through origin: slope = Σ(n²·ε) / Σ(n²·n²)
x_arr = mx["n2"].values.astype(float)
y_arr = mx["dielectric_real"].values.astype(float)
slope_forced = np.sum(x_arr * y_arr) / np.sum(x_arr ** 2)
x_plot = np.linspace(0, x_arr.max() * 1.05, 300)
ax.plot(x_plot, slope_forced * x_plot, "k-", lw=2, alpha=0.75,
        label=f"Fit: ε = {slope_forced:.3f}·n²")

# R² and p for the forced-origin fit
y_pred   = slope_forced * x_arr
ss_res   = np.sum((y_arr - y_pred) ** 2)
ss_tot   = np.sum((y_arr - y_arr.mean()) ** 2)
r2_forced = 1 - ss_res / ss_tot
# p-value via t-stat on slope
se_slope  = np.sqrt(ss_res / (len(x_arr) - 1)) / np.sqrt(np.sum(x_arr ** 2))
t_stat    = slope_forced / se_slope
p_forced  = 2 * (1 - stats.t.cdf(abs(t_stat), df=len(x_arr) - 1))
print(f"  Maxwell forced-origin fit:  a = {slope_forced:.4f}"
      f"  R² = {r2_forced:.4f}  p = {p_forced:.4e}"
      f"  deviation from 1: {slope_forced - 1:+.4f}")

# Ideal Maxwell line
ax.plot(x_plot, x_plot, "--", color="#aaaaaa", lw=1.5, label="ε = n² (ideal)")

ax.set_xlabel("n² at 633 nm", fontsize=12)
ax.set_ylabel("ε (dielectric_real)", fontsize=12)
ax.set_title("Maxwell Relation: ε vs n²\n"
             "(slope forced through origin; dashed = ideal ε = n²)",
             fontsize=12)
legend_handles = [plt.Line2D([0],[0], marker='o', color='w',
                              markerfacecolor=v, markersize=9, label=k)
                  for k, v in CLASS_COLORS.items()
                  if k in mx["material_class"].values]
legend_handles += [
    plt.Line2D([0],[0], color='k', lw=2, label=f"Fit: ε={slope_forced:.3f}·n²"),
    plt.Line2D([0],[0], color='#aaaaaa', lw=1.5, ls='--', label="Ideal ε=n²"),
]
ax.legend(handles=legend_handles, fontsize=8.5, framealpha=0.9)
ax.grid(True, lw=0.4, alpha=0.4)
plt.tight_layout()
plt.savefig(f"{FIG_DIR}/maxwell_final.png", dpi=300, bbox_inches="tight")
plt.close()
print(f"  Saved: {FIG_DIR}/maxwell_final.png")

# ── Plot 2: Clausius-Mossotti f_CM vs f_LL ───────────────────────────────────
cm_df = flat[["name", "material_class", "f_LL", "f_CM"]].dropna()
print(f"\n  CM plot: {len(cm_df)} materials with both f_LL and f_CM")

fig, ax = plt.subplots(figsize=(10, 8))
handles = scatter_points(ax, cm_df, "f_LL", "f_CM")

fll_arr = cm_df["f_LL"].values.astype(float)
fcm_arr = cm_df["f_CM"].values.astype(float)
slope_cm, intercept_cm, r_cm, p_cm, se_cm = stats.linregress(fll_arr, fcm_arr)
r2_cm = r_cm ** 2
x_cm  = np.linspace(fll_arr.min() * 0.9, fll_arr.max() * 1.05, 300)
ax.plot(x_cm, slope_cm * x_cm + intercept_cm, "k-", lw=2, alpha=0.75,
        label=f"Fit: f_CM = {slope_cm:.3f}·f_LL {intercept_cm:+.3f}")
ax.plot(x_cm, x_cm, "--", color="#aaaaaa", lw=1.5, label="f_CM = f_LL (ideal)")

print(f"  CM regression: slope={slope_cm:.4f}  intercept={intercept_cm:.4f}"
      f"  R²={r2_cm:.4f}  p={p_cm:.4e}")

ax.set_xlabel("f_LL = (n²−1)/(n²+2)  [Lorentz-Lorenz]", fontsize=12)
ax.set_ylabel("f_CM = (ε−1)/(ε+2)  [Clausius-Mossotti]", fontsize=12)
ax.set_title("Clausius-Mossotti Validation: f_CM vs f_LL\n"
             "(slope ≈ 1 for non-polar materials; polar → f_CM >> f_LL)",
             fontsize=12)
legend_handles2 = [plt.Line2D([0],[0], marker='o', color='w',
                               markerfacecolor=v, markersize=9, label=k)
                   for k, v in CLASS_COLORS.items()
                   if k in cm_df["material_class"].values]
legend_handles2 += [
    plt.Line2D([0],[0], color='k', lw=2,
               label=f"Fit: {slope_cm:.3f}·f_LL{intercept_cm:+.3f}"),
    plt.Line2D([0],[0], color='#aaaaaa', lw=1.5, ls='--', label="Ideal f_CM=f_LL"),
]
ax.legend(handles=legend_handles2, fontsize=8.5, framealpha=0.9)
ax.grid(True, lw=0.4, alpha=0.4)
plt.tight_layout()
plt.savefig(f"{FIG_DIR}/clausius_mossotti.png", dpi=300, bbox_inches="tight")
plt.close()
print(f"  Saved: {FIG_DIR}/clausius_mossotti.png")
print("✓ Step 5 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — SIGNIFICANCE REPORT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 6 — SIGNIFICANCE REPORT")
print("=" * 65)

# Load previous correlation summary to flag NEWLY_SIGNIFICANT
prev_sig = set()
try:
    prev_csv = pd.read_csv("correlation_summary_dielectric.csv")
    prev_sig = set(
        prev_csv[prev_csv["Significant"] == "YES"]["Feature_A"].tolist()
    )
except FileNotFoundError:
    pass
print(f"  Previously significant features: {sorted(prev_sig)}")

rpt_buf  = io.StringIO()
all_rows = []

def report(msg):
    rpt_buf.write(msg + "\n")

report("DIELECTRIC SIGNIFICANCE FINAL REPORT")
report("=" * 70)
report(f"  Flat dataset: {flat.shape[0]} materials × {flat.shape[1]} columns")
report(f"  Low-freq subset: {len(lf)} materials")
report("")

# All numeric features vs dielectric_real
num_feats = flat.select_dtypes(include=[np.number]).columns.tolist()
num_feats = [c for c in num_feats if c not in
             ("material_id", "dielectric_real", "n2", "diel_freq_hz")]

report(f"{'Feature':<22} {'r':>8}  {'p':>8}  {'N':>4}  {'Sig':>4}  "
       f"{'NEW':>4}  {'Class_filter':<20}  Notes")
report("-" * 90)

for subset_label, subset_df in [("low_frequency", lf), ("all", flat)]:
    for feat in num_feats:
        if feat not in subset_df.columns:
            continue
        r, p, n = pearson_safe(subset_df[feat], subset_df["dielectric_real"])
        if np.isnan(r) or n < 2:
            continue
        sig  = p < 0.05
        new  = sig and feat not in prev_sig
        unrel = n < 6
        inorg_excl = feat in ("LogP", "TPSA", "BertzCT") and subset_label == "all"
        notes = []
        if unrel:
            notes.append("UNRELIABLE")
        if inorg_excl:
            notes.append("INORGANIC_EXCLUDED")
        row = dict(
            Feature=feat,
            r=round(r, 6),
            p=round(p, 6),
            N_pairs=n,
            Significant="YES" if sig else "no",
            NEWLY_SIGNIFICANT="YES" if new else "no",
            UNRELIABLE=unrel,
            INORGANIC_EXCLUDED=inorg_excl,
            Class_filter=subset_label,
        )
        all_rows.append(row)

        sig_str  = "YES" if sig else "no "
        new_str  = "***" if new else "   "
        note_str = " | ".join(notes) if notes else ""
        line = (f"  {feat:<22} {r:>+8.4f}  {p:>8.4f}  {n:>4}  {sig_str:>4}  "
                f"{new_str:>4}  {subset_label:<20}  {note_str}")
        report(line)

report("")
report("SUMMARY")
report("-" * 40)
df_rpt = pd.DataFrame(all_rows)
sig_df = df_rpt[df_rpt["Significant"] == "YES"]
report(f"  Total correlations computed: {len(df_rpt)}")
report(f"  Significant (p < 0.05): {len(sig_df)}")
report(f"  Newly significant: {df_rpt['NEWLY_SIGNIFICANT'].eq('YES').sum()}")
report(f"  UNRELIABLE (N<6): {df_rpt['UNRELIABLE'].sum()}")
report(f"  INORGANIC_EXCLUDED: {df_rpt['INORGANIC_EXCLUDED'].sum()}")
if len(sig_df):
    report("\n  Significant correlations:")
    for _, row in sig_df.drop_duplicates("Feature").iterrows():
        report(f"    {row['Feature']:<22}  r={row['r']:>+8.4f}  p={row['p']:.5f}  "
               f"N={row['N_pairs']}  NEW={row['NEWLY_SIGNIFICANT']}")

rpt_path = f"{RPT_DIR}/dielectric_significance_final.txt"
with open(rpt_path, "w") as f:
    f.write(rpt_buf.getvalue())
print(f"  Saved: {rpt_path}")

# Save updated CSV
df_rpt.to_csv("correlation_summary_dielectric.csv", index=False)
print(f"  Saved: correlation_summary_dielectric.csv  ({len(df_rpt)} rows)")

# Console summary table (top 20 by |r| in low_freq subset)
lf_rows = df_rpt[df_rpt["Class_filter"] == "low_frequency"].copy()
lf_rows = lf_rows.sort_values("r", key=abs, ascending=False)
print(f"\n  Top correlations with dielectric_real (low_freq, by |r|):")
print(f"  {'Feature':<22} {'r':>8}  {'p':>8}  {'N':>4}  Sig  New")
print("  " + "-" * 60)
for _, row in lf_rows.head(15).iterrows():
    new_mark = " ***NEW***" if row["NEWLY_SIGNIFICANT"] == "YES" else ""
    print(f"  {row['Feature']:<22} {row['r']:>+8.4f}  {row['p']:>8.5f}  "
          f"{row['N_pairs']:>4}  {row['Significant']:<3}  {new_mark}")

print("✓ Step 6 complete")

conn.close()
print("\n" + "=" * 65)
print("ALL 6 STEPS COMPLETE")
print("=" * 65)
