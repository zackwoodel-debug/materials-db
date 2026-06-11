#!/usr/bin/env python3
"""
scripts/enrich_and_reanalyze.py
Steps 1-5: RDKit descriptors, viscoelasticity, optical data, full reanalysis, report.
Run from project root: python3 scripts/enrich_and_reanalyze.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats
from pathlib import Path

from materials_db.calculators.sld_calculator import (
    parse_formula, compute_xray_sld, compute_neutron_sld,
)

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "materials.db"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

SLDS_ENERGIES = [(8040.0, 0.15406), (17400.0, 0.07093)]
SLD_ENERGIES  = [(8047.8, 0.154060), (17479.3, 0.070932),
                 (10000.0, 0.123984), (12000.0, 0.103320)]

sns.set_theme(style="whitegrid", font_scale=0.9)

# ── Snapshot previous analysis_dataset.csv null counts for delta ──────────────
prev_csv = ROOT / "analysis_dataset.csv"
prev_null_counts = {}
if prev_csv.exists():
    prev_df = pd.read_csv(prev_csv)
    prev_null_counts = prev_df.isnull().sum().to_dict()
    print(f"Snapshot: previous analysis_dataset.csv  shape={prev_df.shape}")

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

def stop(msg):
    print(f"\n!!! STOP: {msg}")
    conn.close()
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════════
# STEP 1 — RDKit DESCRIPTORS FOR NEW MATERIALS
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 1 — RDKit DESCRIPTORS")
print("="*70)

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    from rdkit.Chem.GraphDescriptors import BertzCT
    print("  rdkit already installed ✓")
except ImportError:
    print("  Installing rdkit...")
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "rdkit", "--break-system-packages", "-q"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        stop(f"rdkit install failed: {r.stderr[:200]}")
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    from rdkit.Chem.GraphDescriptors import BertzCT
    print("  rdkit installed ✓")

# Map: (user descriptor name) → function or None
DESCRIPTOR_FUNCS = {
    "MolWt":            lambda mol: Descriptors.MolWt(mol),
    "MolLogP":          lambda mol: Descriptors.MolLogP(mol),
    "NumHDonors":       lambda mol: Descriptors.NumHDonors(mol),
    "NumHAcceptors":    lambda mol: Descriptors.NumHAcceptors(mol),
    "TPSA":             lambda mol: Descriptors.TPSA(mol),
    "NumRotatableBonds":lambda mol: Descriptors.NumRotatableBonds(mol),
    "NumAromaticRings": lambda mol: Descriptors.NumAromaticRings(mol),
    "NumHeavyAtoms":    lambda mol: mol.GetNumHeavyAtoms(),
    "FractionCSP3":     lambda mol: Descriptors.FractionCSP3(mol),
    "BertzCT":          lambda mol: BertzCT(mol),
}

# SMILES to use: read from pubchem_data where available, else use fallback
SMILES_FALLBACK = {
    "TiO2":     "O=[Ti]=O",
    "PDMS":     "C[Si](C)(O)O",          # monomer unit
    "PEI":      "NCCN",                   # ethylenediamine repeat
    "ITO":      "[In+3].[Sn+4].[O-2]",
    "Chromium": "[Cr]",
    "BSA":      None,                     # skip — protein
}

# Get material id map
cur.execute("SELECT id, name FROM materials")
mat_id = {r[1]: r[0] for r in cur.fetchall()}

# Get SMILES from pubchem_data
cur.execute("SELECT material_name, SMILES FROM pubchem_data")
pc_smiles = {r[0]: r[1] for r in cur.fetchall() if r[1] is not None}

def safe_compute(mol, fname, func):
    try:
        val = func(mol)
        return float(val) if val is not None else None
    except Exception as e:
        return None

step1_results = {}
for mat_name in SMILES_FALLBACK:
    # Priority: pubchem_data SMILES → fallback SMILES
    smiles = pc_smiles.get(mat_name) or SMILES_FALLBACK[mat_name]

    if smiles is None:
        print(f"  {mat_name:<12} SKIPPED — protein, no valid SMILES")
        step1_results[mat_name] = "skipped"
        continue

    mid = mat_id.get(mat_name)
    if mid is None:
        print(f"  {mat_name:<12} SKIPPED — not in materials table")
        step1_results[mat_name] = "skipped_no_id"
        continue

    # Try parsing SMILES
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        # Retry without full sanitization (useful for inorganics)
        mol = Chem.MolFromSmiles(smiles, sanitize=False)
        if mol is not None:
            try:
                Chem.SanitizeMol(
                    mol,
                    Chem.SanitizeFlags.SANITIZE_ALL ^
                    Chem.SanitizeFlags.SANITIZE_PROPERTIES
                )
            except Exception:
                pass

    if mol is None:
        print(f"  {mat_name:<12} FAILED  — RDKit cannot parse SMILES: {smiles}")
        step1_results[mat_name] = "failed_parse"
        continue

    computed = {}
    failed   = []
    for desc_name, func in DESCRIPTOR_FUNCS.items():
        val = safe_compute(mol, desc_name, func)
        if val is not None:
            computed[desc_name] = val
        else:
            failed.append(desc_name)

    # Upsert into chemical_descriptors
    inserted = updated = skipped = 0
    for desc_name, value in computed.items():
        cur.execute(
            "SELECT id FROM chemical_descriptors WHERE material_id=? AND descriptor_name=?",
            (mid, desc_name)
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE chemical_descriptors SET value=?, source_library='RDKit' WHERE id=?",
                (value, existing[0])
            )
            updated += 1
        else:
            cur.execute(
                """INSERT INTO chemical_descriptors
                   (material_id, descriptor_name, value, source_library)
                   VALUES (?,?,?,'RDKit')""",
                (mid, desc_name, value)
            )
            inserted += 1

    conn.commit()
    fail_str = f"  failed=[{','.join(failed)}]" if failed else ""
    print(f"  {mat_name:<12} OK — {inserted} inserted, {updated} updated{fail_str}")
    step1_results[mat_name] = "ok"

# Verify
cur.execute("SELECT COUNT(*) FROM chemical_descriptors")
print(f"\n  chemical_descriptors total rows: {cur.fetchone()[0]}")
print("\n✓ STEP 1 COMPLETE")

# ════════════════════════════════════════════════════════════════════════════════
# STEP 2 — VISCOELASTICITY FOR PDMS AND ITO
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 2 — VISCOELASTICITY")
print("="*70)
print("  Schema: viscoelasticity(id, material_id, reference_id, frequency_hz,")
print("          temperature_C, storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s)")
print("  Note: viscosity_mpa_s stores mPa·s (water=1.0016 mPa·s at 20°C)")

# (name, storage_pa, loss_pa, viscosity_mpa_s, temp_C, freq_hz, source)
VISCO_DATA = [
    ("PDMS", 1.0e6, 1.0e5,  5.0,  25.0, 1.0,  "Literature avg: Sylgard 184 crosslinked film (Voigt model, 1 Hz, 25°C)"),
    ("ITO",  1.16e11, None, None, 25.0, 0.0,  "Bulk ceramic Young modulus (quasi-static); Hjortsberg 1982 / literature"),
]

for mat_name, E_stor, E_loss, visc, temp, freq, src in VISCO_DATA:
    mid = mat_id.get(mat_name)
    if mid is None:
        print(f"  {mat_name}: not in materials — SKIP")
        continue

    # Duplicate check: uses the UNIQUE(material_id, frequency_hz, temperature_C) constraint
    cur.execute(
        "SELECT id FROM viscoelasticity WHERE material_id=? AND frequency_hz=? AND temperature_C=?",
        (mid, freq, temp)
    )
    if cur.fetchone():
        print(f"  {mat_name:<10} SKIPPED — (material_id={mid}, freq={freq}, temp={temp}) already exists")
        continue

    try:
        cur.execute(
            """INSERT INTO viscoelasticity
               (material_id, reference_id, frequency_hz, temperature_C,
                storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s)
               VALUES (?,NULL,?,?,?,?,?)""",
            (mid, freq, temp, E_stor, E_loss, visc)
        )
        conn.commit()
        print(f"  {mat_name:<10} INSERTED — E'={E_stor:.2e}  E''={E_loss}  η={visc}  src={src[:50]}")
    except Exception as e:
        stop(f"viscoelasticity insert failed for {mat_name}: {e}")

cur.execute("SELECT COUNT(*) FROM viscoelasticity")
print(f"\n  viscoelasticity total rows: {cur.fetchone()[0]}")
print("\n✓ STEP 2 COMPLETE")

# ════════════════════════════════════════════════════════════════════════════════
# STEP 3 — k@633nm OPTICAL DATA + SILVER
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 3 — k@633nm OPTICAL DATA")
print("="*70)

# Add reference
REF = "Johnson P.B. & Christy R.W. Phys.Rev.B 6,4370 (1972); Palik Handbook Vol.1 (1985)"
cur.execute("INSERT OR IGNORE INTO references_db (citation_text) VALUES (?)", (REF,))
conn.commit()
cur.execute("SELECT id FROM references_db WHERE citation_text=?", (REF,))
ref_id = cur.fetchone()[0]

# ── Add Silver material ───────────────────────────────────────────────────────
cur.execute("INSERT OR IGNORE INTO materials (name,formula,smiles,molecular_weight,material_class,notes,density_g_cm3,pubchem_cid) VALUES (?,?,?,?,?,?,?,?)",
    ("Silver","Ag","[Ag]",107.868,"metal",
     "Silver thin film; n@633nm from Johnson & Christy 1972.",10.49,23954))
conn.commit()
# refresh mat_id after possible insert
cur.execute("SELECT id, name FROM materials")
mat_id = {r[1]: r[0] for r in cur.fetchall()}
print(f"  Silver id={mat_id['Silver']}  {'(freshly inserted)' if cur.rowcount else '(already existed)'}")

# Compute Silver SLD
ag_mid = mat_id["Silver"]
cur.execute("SELECT COUNT(*) FROM calculated_slds WHERE material_id=?", (ag_mid,))
if cur.fetchone()[0] == 0:
    try:
        counts = parse_formula("Ag")
        xsld = float(compute_xray_sld(counts, 10.49, 107.868).real)
        nsld = float(compute_neutron_sld(counts, 10.49, 107.868))
        for ev, wl in SLDS_ENERGIES:
            cur.execute("""INSERT INTO calculated_slds
                (material_id,reference_id,energy_ev,wavelength_nm,
                 xray_sld_real,xray_sld_imag,neutron_sld_real,neutron_sld_imag)
                VALUES (?,NULL,?,?,?,NULL,?,NULL)""", (ag_mid,ev,wl,xsld,nsld))
        for ev, wl in SLD_ENERGIES:
            cur.execute("""INSERT INTO calculated_sld
                (material_id,reference_id,energy_ev,wavelength_nm,
                 sld_xray_real,sld_xray_imag,sld_neutron_real,
                 calculation_method,notes)
                VALUES (?,NULL,?,?,?,0.0,?,'sld_calculator.py',NULL)""",
                (ag_mid,ev,wl,xsld,nsld))
        conn.commit()
        print(f"  Silver SLD: xray={xsld:.6f}  neutron={nsld:.4e}")
    except Exception as e:
        print(f"  Silver SLD FAILED: {e}")

# Add Silver to pubchem_data
cur.execute("INSERT OR IGNORE INTO pubchem_data (material_name,SMILES,molecular_formula,MW) VALUES (?,?,?,?)",
    ("Silver","[Ag]","Ag",107.868))
conn.commit()

# ── Optical NK inserts / updates at 633nm ────────────────────────────────────
# (name, n, k, update_if_different)  — k=None means transparent (store NULL)
NK_633 = [
    ("TiO2",     2.490, 0.0001,  True,  "Devore 1951 J.Opt.Soc.Am; k from thin-film absorption"),
    ("ITO",      1.800, 0.0550,  True,  "Standard sputtered ITO film; n corrected to 1.800"),
    ("Chromium", 3.180, 3.330,   False, "Palik Handbook Vol.1 1985"),
    ("PDMS",     1.410, 0.0000,  True,  "Transparent polymer; k~0"),
    ("Gold",     0.180, 3.450,   False, "Johnson & Christy 1972; 633nm interpolated"),
    ("Silver",   0.135, 3.990,   False, "Johnson & Christy 1972"),
    ("BSA",      1.450, 0.0000,  True,  "Protein film approximation"),
    ("PEI",      1.520, 0.0000,  True,  "Transparent polymer"),
]

for mat_name, n_val, k_val, may_update, src in NK_633:
    mid = mat_id.get(mat_name)
    if mid is None:
        print(f"  {mat_name:<10} not in materials — SKIP")
        continue

    cur.execute(
        "SELECT id, n, k FROM optical_nk WHERE material_id=? AND wavelength_nm BETWEEN 628 AND 638",
        (mid,)
    )
    existing = cur.fetchall()

    if existing and not may_update:
        print(f"  {mat_name:<10} 633nm exists — SKIP (no update needed)")
        continue

    if existing and may_update:
        # Only update if values differ meaningfully
        row_id, ex_n, ex_k = existing[0]
        n_diff = abs((ex_n or 0) - n_val) > 0.001
        k_diff = abs((ex_k or 0) - k_val) > 1e-6
        if n_diff or k_diff:
            cur.execute(
                "UPDATE optical_nk SET n=?, k=?, source_ref=?, reference_id=? WHERE id=?",
                (n_val, k_val, src, ref_id, row_id)
            )
            conn.commit()
            print(f"  {mat_name:<10} 633nm UPDATED  n={n_val} k={k_val}")
        else:
            print(f"  {mat_name:<10} 633nm values unchanged — SKIP")
        continue

    # No existing row — INSERT
    try:
        cur.execute(
            """INSERT INTO optical_nk
               (material_id,reference_id,wavelength_nm,n,k,source_ref,temperature_C)
               VALUES (?,?,633.0,?,?,?,25.0)""",
            (mid, ref_id, n_val, k_val, src)
        )
        conn.commit()
        print(f"  {mat_name:<10} 633nm INSERTED  n={n_val} k={k_val}")
    except Exception as e:
        stop(f"optical_nk insert failed for {mat_name}: {e}")

cur.execute("SELECT COUNT(*) FROM optical_nk")
print(f"\n  optical_nk total rows: {cur.fetchone()[0]}")

# Also add Silver to chemical_descriptors using RDKit [Ag]
ag_mol = Chem.MolFromSmiles("[Ag]", sanitize=False)
if ag_mol is not None:
    try:
        Chem.SanitizeMol(ag_mol,
            Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    except Exception:
        pass
    for desc_name, func in DESCRIPTOR_FUNCS.items():
        val = safe_compute(ag_mol, desc_name, func)
        if val is not None:
            cur.execute("SELECT id FROM chemical_descriptors WHERE material_id=? AND descriptor_name=?",
                        (ag_mid, desc_name))
            ex = cur.fetchone()
            if ex:
                cur.execute("UPDATE chemical_descriptors SET value=? WHERE id=?", (val, ex[0]))
            else:
                cur.execute("INSERT INTO chemical_descriptors (material_id,descriptor_name,value,source_library) VALUES (?,?,?,'RDKit')",
                            (ag_mid, desc_name, val))
    conn.commit()
    print(f"  Silver RDKit descriptors added")

print("\n✓ STEP 3 COMPLETE")

# ════════════════════════════════════════════════════════════════════════════════
# STEP 4 — REBUILD AND RERUN
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 4 — REBUILD + RERUN CORRELATION PIPELINE")
print("="*70)

# refresh mat_id with Silver included
cur.execute("SELECT id, name FROM materials")
mat_id = {r[1]: r[0] for r in cur.fetchall()}

# ── Build flat DataFrame ──────────────────────────────────────────────────────
base = pd.read_sql("SELECT * FROM materials", conn).rename(columns={"id": "material_id"})

nk_633 = pd.read_sql("""SELECT material_id, AVG(n) AS n_633nm, AVG(k) AS k_633nm
  FROM optical_nk WHERE wavelength_nm BETWEEN 628 AND 638 GROUP BY material_id""", conn)

nk_785 = pd.read_sql("""SELECT material_id, AVG(n) AS n_785nm, AVG(k) AS k_785nm
  FROM optical_nk WHERE wavelength_nm BETWEEN 780 AND 790 GROUP BY material_id""", conn)

nk_980 = pd.read_sql("""SELECT material_id, AVG(n) AS n_980nm, AVG(k) AS k_980nm
  FROM optical_nk WHERE wavelength_nm BETWEEN 975 AND 985 GROUP BY material_id""", conn)

sld_df = pd.read_sql("""SELECT material_id,
  AVG(xray_sld_real) AS xray_sld_real, AVG(neutron_sld_real) AS neutron_sld_real
  FROM calculated_slds GROUP BY material_id""", conn)

visco_df = pd.read_sql("""SELECT material_id,
  AVG(storage_modulus_pa) AS storage_modulus_pa,
  AVG(loss_modulus_pa)    AS loss_modulus_pa,
  AVG(viscosity_mpa_s)    AS viscosity_mpa_s
  FROM viscoelasticity GROUP BY material_id""", conn)

diel_df = pd.read_sql("""SELECT material_id,
  AVG(dielectric_real) AS dielectric_real_static
  FROM dielectric GROUP BY material_id""", conn)

# chemical_descriptors: pivot long → wide
cd_long = pd.read_sql(
    "SELECT material_id, descriptor_name, value FROM chemical_descriptors", conn)
cd_wide = cd_long.pivot_table(
    index="material_id", columns="descriptor_name",
    values="value", aggfunc="first"
).reset_index()
cd_wide.columns.name = None

# pubchem_data
pc_df = pd.read_sql("SELECT * FROM pubchem_data", conn)

flat = base.copy()
for right in [nk_633, nk_785, nk_980, sld_df, visco_df, diel_df, cd_wide]:
    dup = [c for c in right.columns if c != "material_id" and c in flat.columns]
    flat = flat.merge(right.drop(columns=dup), on="material_id", how="left")

# pubchem by name
pc_r = pc_df.rename(columns={"material_name": "name"})
dup_pc = [c for c in pc_r.columns if c != "name" and c in flat.columns]
flat = flat.merge(pc_r.drop(columns=dup_pc, errors="ignore"), on="name", how="left")
flat = flat.loc[:, ~flat.columns.duplicated()]

flat.to_csv(ROOT / "analysis_dataset.csv", index=False)
print(f"\n  Saved analysis_dataset.csv  shape={flat.shape}")

# ── Coverage delta ────────────────────────────────────────────────────────────
print("\n  Coverage delta (null count before → after):")
print(f"  {'Column':<38} {'Before':>7}  {'After':>7}  {'Delta':>7}")
print(f"  {'-'*62}")
new_null_counts = flat.isnull().sum().to_dict()
improved = []
for col in sorted(set(list(prev_null_counts.keys()) + list(new_null_counts.keys()))):
    before = prev_null_counts.get(col, "N/A")
    after  = new_null_counts.get(col, "N/A")
    if before == "N/A" or after == "N/A":
        continue
    delta  = after - before
    if delta != 0:
        sign = "▼" if delta < 0 else "▲"
        print(f"  {col:<38} {before:>7}  {after:>7}  {sign}{abs(delta):>5}")
        if delta < 0:
            improved.append(col)
print(f"\n  Total nulls: {sum(prev_null_counts.values())} → {flat.isnull().sum().sum()}")

# ── Correlation pipeline ──────────────────────────────────────────────────────
TARGETS = [
    ("n_633nm",          "n (633 nm)"),
    ("k_633nm",          "k (633 nm)"),
    ("xray_sld_real",    "X-ray SLD"),
    ("neutron_sld_real", "Neutron SLD"),
    ("density_g_cm3",    "Density g/cm³"),
]

ID_COLS = {
    "material_id","name","formula","smiles","molecular_weight",
    "material_class","notes","pubchem_cid",
    "SMILES","molecular_formula","MW","material_name",
}

RDKIT_DESCS = {"MolWt","MolLogP","NumHDonors","NumHAcceptors","TPSA",
               "NumRotatableBonds","NumAromaticRings","NumHeavyAtoms",
               "FractionCSP3","BertzCT",
               "ExactMolWt","logP","h_bond_donors","h_bond_acceptors",
               "rotatable_bonds","exact_mass","NumRings"}

summary_rows = []
best_per_target = {}
all_feature_abs_r = {}


def style_hm(ax, title):
    ax.set_title(title, fontsize=11, fontweight="bold", pad=11)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.tick_params(axis="y", rotation=0,  labelsize=7)


for target_col, target_label in TARGETS:
    print(f"\n  ── Target: {target_label} ({target_col}) ──")

    if target_col not in flat.columns:
        print(f"     NOT FOUND — skipping")
        continue

    num_df = flat.select_dtypes(include=[np.number]).copy()
    drop = [c for c in num_df.columns if c.lower() in {s.lower() for s in ID_COLS}]
    num_df.drop(columns=drop, errors="ignore", inplace=True)
    for col in list(num_df.columns):
        if num_df[col].dropna().nunique() <= 1:
            num_df.drop(columns=[col], inplace=True)

    if target_col not in num_df.columns:
        continue

    num_df = num_df.dropna(subset=[target_col])
    num_df = num_df.dropna(axis=1, thresh=3)
    feature_cols = [c for c in num_df.columns if c != target_col]
    if not feature_cols:
        print(f"     No features with ≥3 values")
        continue

    analysis = num_df[[target_col] + feature_cols]

    # Figure A: full heatmap
    corr_full = analysis.corr(method="pearson")
    n_c = len(corr_full)
    fig, ax = plt.subplots(figsize=(14, 12))
    sns.heatmap(corr_full, ax=ax, cmap="RdBu_r", vmin=-1, vmax=1,
                annot=True, fmt=".1f",
                linewidths=0.4, linecolor="#e0e0e0",
                cbar_kws={"shrink":0.8,"label":"Pearson r"},
                annot_kws={"size": max(5, 8 - n_c//8)})
    style_hm(ax, f"Full Correlation Matrix — {target_label}")
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"corr_full_{target_col}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Drop high-correlation pairs
    target_r_abs = corr_full[target_col].drop(target_col).abs()
    to_drop = set()
    for i, fi in enumerate(feature_cols):
        for fj in feature_cols[i+1:]:
            if fi in to_drop or fj in to_drop:
                continue
            if fi not in corr_full.index or fj not in corr_full.columns:
                continue
            rp = abs(corr_full.loc[fi, fj])
            if rp > 0.85:
                ri = target_r_abs.get(fi, 0)
                rj = target_r_abs.get(fj, 0)
                to_drop.add(fj if ri >= rj else fi)

    kept = [c for c in feature_cols if c not in to_drop]

    # Figure B: cleaned heatmap
    sz = max(7, len(kept)+1)
    corr_clean = analysis[[target_col]+kept].corr(method="pearson")
    fig, ax = plt.subplots(figsize=(sz, sz-1))
    sns.heatmap(corr_clean, ax=ax, cmap="RdBu_r", vmin=-1, vmax=1,
                annot=True, fmt=".2f",
                linewidths=0.4, linecolor="#e0e0e0",
                cbar_kws={"shrink":0.8,"label":"Pearson r"},
                annot_kws={"size":9})
    style_hm(ax, f"Cleaned Correlation Matrix — {target_label}")
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"corr_cleaned_{target_col}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # p-values + Figure C: ranked bar chart
    bar_data = []
    for feat in kept:
        pair = analysis[[feat, target_col]].dropna()
        if len(pair) < 3:
            r_val, p_val = np.nan, np.nan
        else:
            r_val, p_val = stats.pearsonr(pair[feat], pair[target_col])
        sig = (p_val < 0.05) if not np.isnan(p_val) else False
        is_rdkit = feat in RDKIT_DESCS
        bar_data.append({"feature": feat, "r": r_val,
                         "abs_r": abs(r_val) if not np.isnan(r_val) else 0,
                         "p": p_val, "sig": sig, "rdkit": is_rdkit})
        summary_rows.append({
            "Feature": feat, "Target": target_col,
            "Pearson_r": round(r_val,4) if not np.isnan(r_val) else np.nan,
            "P_value":   round(p_val,4) if not np.isnan(p_val) else np.nan,
            "Significant": "yes" if sig else "no",
            "Decision": "kept",
            "RDKit_descriptor": "yes" if is_rdkit else "no",
        })
        # track for pairplot feature selection
        if not np.isnan(r_val):
            all_feature_abs_r.setdefault(feat, []).append(abs(r_val))

    for feat in to_drop:
        pair = analysis[[feat, target_col]].dropna() if feat in analysis.columns else pd.DataFrame()
        r_val = p_val = np.nan
        if len(pair) >= 3:
            r_val, p_val = stats.pearsonr(pair[feat], pair[target_col])
        sig = (p_val < 0.05) if not np.isnan(p_val) else False
        summary_rows.append({
            "Feature": feat, "Target": target_col,
            "Pearson_r": round(r_val,4) if not np.isnan(r_val) else np.nan,
            "P_value":   round(p_val,4) if not np.isnan(p_val) else np.nan,
            "Significant": "yes" if sig else "no",
            "Decision": "dropped",
            "RDKit_descriptor": "yes" if feat in RDKIT_DESCS else "no",
        })

    # best predictor for report
    if bar_data:
        bd_valid = [b for b in bar_data if not np.isnan(b["abs_r"])]
        if bd_valid:
            best = max(bd_valid, key=lambda x: x["abs_r"])
            best_per_target[target_col] = {**best, "label": target_label}

    bar_df = pd.DataFrame(bar_data).sort_values("abs_r", ascending=True)
    fig_h  = max(5, len(bar_df)*0.42 + 2)
    fig, ax = plt.subplots(figsize=(11, fig_h))
    colors = ["#2ca02c" if s else "#d62728" for s in bar_df["sig"]]
    bars   = ax.barh(bar_df["feature"], bar_df["abs_r"], color=colors,
                     edgecolor="white", height=0.65)
    ax.axvline(0.30, color="#999", linestyle="--", linewidth=1.0)
    ax.axvline(0.70, color="#444", linestyle="--", linewidth=1.5)
    for bar, row in zip(bars, bar_df.itertuples()):
        r_s = f"{row.r:+.3f}" if not np.isnan(row.r) else "NaN"
        p_s = f"p={row.p:.3f}" if not np.isnan(row.p) else "p=NaN"
        rdkit_tag = " [R]" if row.rdkit else ""
        ax.text(bar.get_width()+0.01, bar.get_y()+bar.get_height()/2,
                f"{r_s}  {p_s}{rdkit_tag}", va="center", ha="left", fontsize=7)
    gp = mpatches.Patch(color="#2ca02c", label="p<0.05")
    rp = mpatches.Patch(color="#d62728", label="p≥0.05")
    ax.legend(handles=[gp,rp], loc="lower right", fontsize=8)
    ax.set_xlim(0, 1.35)
    ax.set_xlabel("|Pearson r|", fontsize=10)
    ax.set_title(f"Feature Importance — {target_label}", fontsize=11, fontweight="bold", pad=11)
    sns.despine(left=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"corr_ranked_{target_col}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"     k_633nm rows: {analysis['k_633nm'].notna().sum() if 'k_633nm' in analysis.columns else 'N/A'}")
    print(f"     Kept {len(kept)} features | Dropped {len(to_drop)} | Figures saved ✓")

# ── Save correlation_summary.csv ──────────────────────────────────────────────
summ_df = pd.DataFrame(summary_rows)
if not summ_df.empty:
    summ_df["Abs_r"] = summ_df["Pearson_r"].abs()
    summ_df.sort_values(["Target","Abs_r"], ascending=[True,False], inplace=True)
summ_df.to_csv(ROOT / "correlation_summary.csv", index=False)
print(f"\n  correlation_summary.csv: {len(summ_df)} rows")

# ── Coverage map ──────────────────────────────────────────────────────────────
ID_SET_COV = {"material_id","name","formula","smiles","molecular_weight",
              "material_class","notes","pubchem_cid","SMILES","molecular_formula",
              "MW","material_name"}
feat_cols_cov = [c for c in flat.columns if c not in ID_SET_COV]
cov_df = flat.set_index("name")[feat_cols_cov].dropna(axis=1, how="all")
presence = cov_df.notna().astype(float)
flat_s = flat.sort_values(["material_class","name"])
presence = presence.loc[flat_s["name"].values]

fig, ax = plt.subplots(figsize=(max(18, len(presence.columns)*0.55),
                                 max(7, len(presence)*0.45+2)))
cmap2 = matplotlib.colors.ListedColormap(["#d62728","#2ca02c"])
sns.heatmap(presence, ax=ax, cmap=cmap2, vmin=0, vmax=1,
            linewidths=0.5, linecolor="#e0e0e0", cbar=False,
            xticklabels=True)
ax.set_title("Data Coverage Map — materials × features\nGreen=present  Red=null",
             fontsize=12, fontweight="bold", pad=11)
ax.tick_params(axis="x", rotation=45, labelsize=7)
ax.tick_params(axis="y", rotation=0,  labelsize=8)
gp2 = mpatches.Patch(color="#2ca02c", label="Present")
rp2 = mpatches.Patch(color="#d62728", label="Null")
ax.legend(handles=[gp2,rp2], loc="upper right",
          bbox_to_anchor=(1.0,-0.18), ncol=2, fontsize=8)
fig.tight_layout()
fig.savefig(FIG_DIR/"coverage_map.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"  coverage_map.png saved")

# ── Pairplot ──────────────────────────────────────────────────────────────────
# Select top 6 well-covered features by mean |r| across all 5 targets
mean_abs_r = {f: np.mean(v) for f, v in all_feature_abs_r.items()}
for t, _ in TARGETS:
    mean_abs_r.pop(t, None)
# Filter to features with ≥10 non-null values (well-covered)
coverage_min = 10
well_covered = {f for f in mean_abs_r if flat[f].notna().sum() >= coverage_min}
mean_abs_r_cov = {f: v for f, v in mean_abs_r.items() if f in well_covered}
top6 = sorted(mean_abs_r_cov, key=lambda x: mean_abs_r_cov[x], reverse=True)[:6]
# Ensure density is always in pairplot
if "density_g_cm3" not in top6:
    top6 = (top6[:5] + ["density_g_cm3"])
print(f"\n  Top-6 well-covered features for pairplot: {top6}")
print(f"    Coverage counts: {[(f, int(flat[f].notna().sum())) for f in top6]}")

pairplot_cols = top6 + ["material_class"]
# Require each row to have at least 4 of the 6 features
pp_df = flat[pairplot_cols].copy()
pp_df = pp_df[pp_df[top6].notna().sum(axis=1) >= 4]

# Simplify material_class labels for colour map
cls_map = {
    "metal": "Metal", "oxide": "Oxide", "polymer": "Polymer",
    "protein": "Biological", "lipid": "Biological",
    "solvent": "Solvent", "semiconductor": "Semiconductor",
}
pp_df = pp_df.copy()
pp_df["Class"] = pp_df["material_class"].map(cls_map).fillna(pp_df["material_class"])

palette = {
    "Metal": "#e6194b", "Oxide": "#f58231",
    "Polymer": "#3cb44b", "Biological": "#4363d8",
    "Solvent": "#911eb4", "Semiconductor": "#42d4f4",
}

plot_cols = [c for c in pairplot_cols if c not in ("material_class","Class")]
try:
    g = sns.pairplot(
        pp_df.dropna(subset=plot_cols, how="all"),
        vars=plot_cols,
        hue="Class",
        palette=palette,
        diag_kind="kde",
        plot_kws={"alpha": 0.7, "s": 60},
        diag_kws={"fill": True, "alpha": 0.5},
        corner=False,
    )
    g.figure.suptitle(
        "Pairplot: Top 6 Features + Density (coloured by material class)",
        y=1.01, fontsize=12, fontweight="bold"
    )
    g.figure.savefig(FIG_DIR/"pairplot.png", dpi=300, bbox_inches="tight")
    plt.close(g.figure)
    print(f"  pairplot.png saved (n={len(pp_df.dropna(subset=plot_cols, how='all'))} materials)")
except Exception as e:
    print(f"  pairplot FAILED: {e}")

print("\n✓ STEP 4 COMPLETE")

# ════════════════════════════════════════════════════════════════════════════════
# STEP 5 — FINAL REPORT
# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 5 — FINAL REPORT")
print("="*70)

# Build "new this run?" set: features that had 0 non-null in prev run
prev_non_null = {k: (len(prev_df) - v) for k, v in prev_null_counts.items()} if prev_null_counts else {}
new_this_run  = {c for c, v in prev_non_null.items() if v == 0}
new_this_run |= set(RDKIT_DESCS)   # all RDKit descriptors are enriched this run
new_this_run.add("k_633nm")        # k_633nm gained more rows this run

print("\n┌─────────────────────────────────────────────────────────────────────────┐")
print("│  Target          │ Best predictor          │    r   │      p  │ Sig │ New │")
print("├─────────────────────────────────────────────────────────────────────────┤")
for target_col, target_label in TARGETS:
    bp = best_per_target.get(target_col)
    if bp is None:
        print(f"│  {target_label:<16} │ {'N/A':<24} │  N/A   │  N/A    │  -  │  -  │")
        continue
    sig_str = "✓" if bp["sig"] else "✗"
    new_str = "✓" if bp["feature"] in new_this_run else "  "
    r_str   = f"{bp['r']:+.4f}"
    p_str   = f"{bp['p']:.4f}" if not np.isnan(bp["p"]) else "NaN"
    feat    = bp["feature"][:24]
    print(f"│  {target_label:<16} │ {feat:<24} │ {r_str} │ {p_str:>8} │  {sig_str}  │  {new_str} │")
print("└─────────────────────────────────────────────────────────────────────────┘")

# Q1: RDKit descriptors predicting n or SLD at p<0.05?
print("\n  Q1: RDKit descriptors (MolLogP/logP, TPSA, BertzCT) at p<0.05?")
rdkit_sig = summ_df[
    (summ_df["RDKit_descriptor"]=="yes") &
    (summ_df["Significant"]=="yes") &
    (summ_df["Target"].isin(["n_633nm","xray_sld_real","neutron_sld_real"]))
][["Feature","Target","Pearson_r","P_value"]].drop_duplicates().sort_values("P_value")
if not rdkit_sig.empty:
    print(rdkit_sig.to_string(index=False))
else:
    print("  None at p<0.05 — RDKit descriptors have weak/insignificant correlations")
    rdkit_best = summ_df[
        (summ_df["RDKit_descriptor"]=="yes") &
        (summ_df["Target"].isin(["n_633nm","xray_sld_real"]))
    ].dropna(subset=["Abs_r"]).sort_values("Abs_r", ascending=False).head(5)
    print("  Best RDKit predictors (closest to significance):")
    print(rdkit_best[["Feature","Target","Pearson_r","P_value"]].to_string(index=False))

# Q2: k_633nm rows
k_rows = flat["k_633nm"].notna().sum()
print(f"\n  Q2: k_633nm non-null rows = {k_rows} "
      f"({'≥6 ✓ — sufficient for correlation' if k_rows>=6 else '< 6 ✗ — still sparse'})")

# Q3: most predictable material class
print("\n  Q3: Most predictable material class")
# count significant predictors per target, weighted by material class membership
class_counts = flat.groupby("material_class").size().reset_index(name="n_materials")
# for each class, show average n_633nm std (lower = more predictable within class)
for cls in sorted(flat["material_class"].dropna().unique()):
    sub = flat[flat["material_class"]==cls][["n_633nm","xray_sld_real","density_g_cm3"]].dropna()
    if len(sub) >= 2:
        cv = sub.std() / sub.mean().abs()
        print(f"    {cls:<14} n={len(sub)}  CoV(n)={cv.get('n_633nm',np.nan):.3f}  "
              f"CoV(xray_SLD)={cv.get('xray_sld_real',np.nan):.3f}  "
              f"CoV(ρ)={cv.get('density_g_cm3',np.nan):.3f}")

# Row count summary
print("\n── Final row counts ───────────────────────────────────────────────────────")
for tbl in ["materials","optical_nk","calculated_slds","calculated_sld",
            "pubchem_data","chemical_descriptors","viscoelasticity"]:
    cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
    print(f"  {tbl:<28} {cur.fetchone()[0]:>5} rows")

# Figure inventory
figs = sorted(FIG_DIR.glob("*.png"))
print(f"\n  Figures generated: {len(figs)}")
for f in figs:
    print(f"    {f.name}")

conn.close()
print("\n" + "="*70)
print("ALL STEPS COMPLETE")
print("="*70)
