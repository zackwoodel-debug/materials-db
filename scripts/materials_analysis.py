#!/usr/bin/env python3
"""
scripts/materials_analysis.py
Steps 2-6: PubChem patch, 8-material insert, coverage map, correlation matrices, summary.
Run from project root: python3 scripts/materials_analysis.py
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

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "materials.db"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

# ── SLD energy/wavelength levels matching existing DB rows ────────────────────
# calculated_slds table uses these two points:
SLDS_ENERGIES = [
    (8040.0,  0.15406),
    (17400.0, 0.07093),
]
# calculated_sld table uses these four points:
SLD_ENERGIES = [
    (8047.8,  0.154060),
    (17479.3, 0.070932),
    (10000.0, 0.123984),
    (12000.0, 0.103320),
]

sns.set_theme(style="whitegrid", font_scale=0.9)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PATCH PUBCHEM FAILURES
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 2 — PATCH PUBCHEM FAILURES")
print("="*70)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

# The pubchem_data table was created with SMILES typed as REAL (SQLite schema bug),
# which silently NULLs any text stored there. Recreate with correct types.
cur.execute("SELECT sql FROM sqlite_master WHERE name='pubchem_data'")
row = cur.fetchone()
print(f"  Current pubchem_data schema: {row[0][:120] if row else 'NOT FOUND'}")

# Back up existing data, recreate table with TEXT SMILES and REAL MW
cur.execute("""
    CREATE TABLE IF NOT EXISTS pubchem_data_backup AS
    SELECT * FROM pubchem_data
""")

cur.execute("""
    CREATE TABLE pubchem_data_new (
        material_name     TEXT PRIMARY KEY,
        SMILES            TEXT,
        molecular_formula TEXT,
        MW                REAL,
        XLogP             REAL,
        HBondDonors       REAL,
        HBondAcceptors    REAL,
        RotatableBonds    REAL,
        TPSA              REAL
    )
""")

# Migrate existing rows (MW column in old table is TEXT, cast to REAL)
cur.execute("""
    INSERT OR IGNORE INTO pubchem_data_new
        (material_name, molecular_formula, MW,
         XLogP, HBondDonors, HBondAcceptors, RotatableBonds, TPSA)
    SELECT
        material_name, molecular_formula,
        CAST(MW AS REAL),
        XLogP, HBondDonors, HBondAcceptors, RotatableBonds, TPSA
    FROM pubchem_data
""")

cur.execute("DROP TABLE pubchem_data")
cur.execute("ALTER TABLE pubchem_data_new RENAME TO pubchem_data")
cur.execute("DROP TABLE IF EXISTS pubchem_data_backup")
conn.commit()
print("  Schema fixed: SMILES→TEXT, MW→REAL")

# Patch Polystyrene and PMMA
patches = [
    ("Polystyrene", "C(c1ccccc1)CC(c1ccccc1)", "(C8H8)n",  104.15),
    ("PMMA",        "COC(=O)C(C)(C)CC(C)(C(=O)OC)", "(C5H8O2)n", 100.12),
]
for name, smiles, formula, mw in patches:
    cur.execute("""
        UPDATE pubchem_data
        SET SMILES=?, molecular_formula=?, MW=?
        WHERE material_name=?
    """, (smiles, formula, mw, name))
    updated = cur.rowcount
    print(f"  Patched {name}: {updated} row(s) updated  SMILES='{smiles[:40]}...'")

conn.commit()

# Verify
df_pc = pd.read_sql(
    "SELECT material_name, SMILES, molecular_formula, MW FROM pubchem_data", conn
)
print("\n  pubchem_data after patch:")
print(df_pc.to_string())
print("\n✓ STEP 2 COMPLETE")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — ADD 8 MATERIALS (INSERT OR IGNORE; SiO2+DPPC already exist)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 3 — ADD 8 MATERIALS")
print("="*70)

# Add a generic reference for the new material optical data
REF_CITATION = (
    "Literature best estimates for thin-film applications: "
    "TiO2 (Sarkar 2019 / De Vore 1951), PDMS (Mark 1999), "
    "PEI (Sigma-Aldrich), BSA (Zhao 2006), "
    "ITO (Kim 1999 Thin Solid Films), "
    "Cr (Palik Handbook Vol.1 1985)"
)
cur.execute(
    "INSERT OR IGNORE INTO references_db (citation_text) VALUES (?)", (REF_CITATION,)
)
conn.commit()
cur.execute(
    "SELECT id FROM references_db WHERE citation_text=?", (REF_CITATION,)
)
NEW_REF_ID = cur.fetchone()[0]
print(f"  Reference id={NEW_REF_ID} added/found")

# ── Material definitions ──────────────────────────────────────────────────────
# Columns: name, formula, smiles, mw, material_class, notes, density, pubchem_cid
MATERIALS_TO_ADD = [
    # SiO2 (2.65 = crystalline quartz; existing DB has 2.20 = fused silica)
    # INSERT OR IGNORE will skip since name is UNIQUE — existing entry preserved
    ("SiO2",      "SiO2",                "O=[Si]=O",
     60.084,  "oxide",    "Silicon dioxide (crystalline quartz). n@633nm=1.46.",
     2.65, 24261),
    # TiO2
    ("TiO2",      "TiO2",                "O=[Ti]=O",
     79.866,  "oxide",    "Titanium dioxide (anatase thin film). n@633nm=2.49 (Sarkar 2019).",
     4.23, 26042),
    # PDMS
    ("PDMS",      "(C2H6OSi)n",          "C[Si](C)(O[Si](C)(C)O)C",
     74.148,  "polymer",  "Polydimethylsiloxane. n from Mark Polymer Data Handbook 4th ed (1999).",
     0.97, None),
    # PEI
    ("PEI",       "(C2H5N)n",            "NCCNCCN",
     43.068,  "polymer",  "Polyethylenimine (branched). Bulk n estimate ~1.52 at 633nm.",
     1.03, None),
    # BSA
    ("BSA",       "C2929H4624N786O892S39", None,
     66432.0, "protein",  "Bovine serum albumin. Formula C2929H4624N786O892S39 (Sigma-Aldrich P02769). n@633nm=1.45.",
     1.35, None),
    # DPPC already exists (id=5, density=1.01) — INSERT OR IGNORE will skip
    ("DPPC",      "C40H80NO8P",
     "CCCCCCCCCCCCCCCC(=O)OCC(COP(=O)([O-])OCC[N+](C)(C)C)OC(=O)CCCCCCCCCCCCCCC",
     734.05, "lipid", "Dipalmitoylphosphatidylcholine; lipid bilayer model.",
     1.02, None),
    # ITO
    ("ITO",       "In18SnO29",           None,
     2649.4,  "oxide",    "Indium tin oxide (90:10 mol In2O3:SnO2). Thin film electrode.",
     7.12, None),
    # Chromium
    ("Chromium",  "Cr",                  "[Cr]",
     51.996,  "metal",    "Chromium adhesion layer. k=3.33 at 633nm (Palik Handbook Vol.1 1985).",
     7.19, 23976),
]

for mat in MATERIALS_TO_ADD:
    name, formula, smiles, mw, cls_, notes, density, cid = mat
    cur.execute("""
        INSERT OR IGNORE INTO materials
            (name, formula, smiles, molecular_weight, material_class, notes,
             density_g_cm3, pubchem_cid)
        VALUES (?,?,?,?,?,?,?,?)
    """, (name, formula, smiles, mw, cls_, notes, density, cid))
    status = "INSERTED" if cur.rowcount else "SKIPPED (exists)"
    print(f"  materials: {name:<12} {status}")

conn.commit()

# Get current material id map
cur.execute("SELECT id, name, density_g_cm3, formula, molecular_weight FROM materials ORDER BY id")
mat_rows = cur.fetchall()
mat_id   = {r[1]: r[0] for r in mat_rows}
mat_data = {r[1]: {"id": r[0], "density": r[2], "formula": r[3], "mw": r[4]}
            for r in mat_rows}
print(f"\n  Current materials ({len(mat_rows)} total):")
for r in mat_rows:
    print(f"    id={r[0]:>3}  {r[1]:<14}  density={r[2]}  formula={r[3]}")

# ── optical_nk inserts ────────────────────────────────────────────────────────
# Only for truly new materials; skip SiO2/DPPC which already have full optical data
# Columns: material_id, reference_id, wavelength_nm, n, k, source_ref, temperature_C
# k=None → NULL (transparent), k=0.0 retained for weak absorbers

# (name, wl_nm, n, k, source_note)
NK_DATA = [
    # TiO2
    ("TiO2", 633.0, 2.490, 0.000, "Sarkar 2019 thin-film TiO2 / user-specified"),
    ("TiO2", 785.0, 2.440, 0.000, "Cauchy extrapolation from 633nm"),
    ("TiO2", 980.0, 2.395, 0.000, "Cauchy extrapolation from 633nm"),
    # PDMS
    ("PDMS", 633.0, 1.410, None,  "Mark J.E. Polymer Data Handbook 4th ed 1999"),
    ("PDMS", 785.0, 1.407, None,  "Cauchy extrapolation"),
    ("PDMS", 980.0, 1.404, None,  "Cauchy extrapolation"),
    # PEI — only well-known single point
    ("PEI",  633.0, 1.520, None,  "Literature estimate; branched PEI bulk n ~1.51-1.53"),
    # BSA
    ("BSA",  633.0, 1.450, None,  "Zhao X. et al. Langmuir 2006; protein film n"),
    ("BSA",  785.0, 1.447, None,  "Cauchy extrapolation"),
    ("BSA",  980.0, 1.444, None,  "Cauchy extrapolation"),
    # ITO
    ("ITO",  633.0, 1.900, 0.050, "Kim H.K. Thin Solid Films 1999; ITO thin film"),
    ("ITO",  785.0, 1.875, 0.035, "Kim H.K. Thin Solid Films 1999; ITO thin film"),
    ("ITO",  980.0, 1.855, 0.015, "Kim H.K. Thin Solid Films 1999; ITO thin film"),
    # Chromium — user-specified @ 633nm; Palik for 785/980
    ("Chromium", 633.0, 3.180, 3.330, "Palik E.D. Handbook of Optical Constants Vol.1 (1985); user-specified"),
    ("Chromium", 785.0, 3.470, 3.680, "Palik E.D. Handbook of Optical Constants Vol.1 (1985); extrapolated"),
    ("Chromium", 980.0, 3.740, 3.870, "Palik E.D. Handbook of Optical Constants Vol.1 (1985); extrapolated"),
]

# Check which (material_id, wavelength_nm) pairs already exist
cur.execute("SELECT material_id, wavelength_nm FROM optical_nk")
existing_nk = set(cur.fetchall())

nk_inserted = 0
for name, wl, n, k, src in NK_DATA:
    mid = mat_id.get(name)
    if mid is None:
        print(f"  optical_nk: {name} not in DB — skip")
        continue
    if (mid, wl) in existing_nk:
        print(f"  optical_nk: {name} @ {wl}nm already exists — skip")
        continue
    cur.execute("""
        INSERT INTO optical_nk (material_id, reference_id, wavelength_nm, n, k, source_ref, temperature_C)
        VALUES (?,?,?,?,?,?,?)
    """, (mid, NEW_REF_ID, wl, n, k, src, 25.0))
    nk_inserted += 1

conn.commit()
print(f"\n  optical_nk: {nk_inserted} rows inserted")

# ── SLD computation and insert ────────────────────────────────────────────────
# Materials to compute SLD for — only truly new ones that don't have SLD entries yet
cur.execute("SELECT DISTINCT material_id FROM calculated_slds")
existing_sld_ids = {r[0] for r in cur.fetchall()}
cur.execute("SELECT DISTINCT material_id FROM calculated_sld")
existing_sld_ids2 = {r[0] for r in cur.fetchall()}

slds_inserted = 0
sld_inserted  = 0

def compute_slds_for_material(name):
    """Return (xray_sld_real, neutron_sld_real) or (None, None) on error."""
    info = mat_data.get(name)
    if info is None:
        return None, None
    formula = info["formula"]
    density = info["density"]
    mw      = info["mw"]
    if not formula or not density or not mw:
        return None, None
    try:
        counts = parse_formula(formula)
        xsld = compute_xray_sld(counts, density, mw)
        nsld = compute_neutron_sld(counts, density, mw)
        return float(xsld.real), float(nsld)
    except Exception as e:
        print(f"    SLD error for {name}: {e}")
        return None, None

# Only compute for materials that don't already have entries
for name in [r[1] for r in mat_rows]:
    mid = mat_id[name]
    xsld, nsld = compute_slds_for_material(name)
    if xsld is None:
        print(f"  SLD: {name:<14} SKIPPED (cannot compute)")
        continue

    # calculated_slds (2 energies)
    if mid not in existing_sld_ids:
        for energy_ev, wavelength_nm in SLDS_ENERGIES:
            cur.execute("""
                INSERT INTO calculated_slds
                    (material_id, reference_id, energy_ev, wavelength_nm,
                     xray_sld_real, xray_sld_imag, neutron_sld_real, neutron_sld_imag)
                VALUES (?,NULL,?,?,?,NULL,?,NULL)
            """, (mid, energy_ev, wavelength_nm, xsld, nsld))
            slds_inserted += 1
        existing_sld_ids.add(mid)
        print(f"  SLD: {name:<14} xray={xsld:.6f}  neutron={nsld:.4e}  → calculated_slds +2")

    # calculated_sld (4 energies)
    if mid not in existing_sld_ids2:
        for energy_ev, wavelength_nm in SLD_ENERGIES:
            cur.execute("""
                INSERT INTO calculated_sld
                    (material_id, reference_id, energy_ev, wavelength_nm,
                     sld_xray_real, sld_xray_imag, sld_neutron_real, sld_neutron_imag,
                     calculation_method, notes)
                VALUES (?,NULL,?,?,?,0.0,?,NULL,'sld_calculator.py',NULL)
            """, (mid, energy_ev, wavelength_nm, xsld, nsld))
            sld_inserted += 1
        existing_sld_ids2.add(mid)

conn.commit()
print(f"\n  calculated_slds: +{slds_inserted} rows  |  calculated_sld: +{sld_inserted} rows")

# Also add new materials to pubchem_data (rows for ones not yet present)
cur.execute("SELECT material_name FROM pubchem_data")
existing_pc_names = {r[0] for r in cur.fetchall()}

PUBCHEM_NEW = {
    "TiO2":     ("O=[Ti]=O", "TiO2",         79.866),
    "PDMS":     ("C[Si](C)(O[Si](C)(C)O)C", "(C2H6OSi)n", 74.148),
    "PEI":      ("NCCNCCN",  "(C2H5N)n",     43.068),
    "BSA":      (None,       "C2929H4624N786O892S39", 66432.0),
    "ITO":      (None,       "In18SnO29",     2649.4),
    "Chromium": ("[Cr]",     "Cr",            51.996),
}
for mat_name, (smiles, formula, mw) in PUBCHEM_NEW.items():
    if mat_name not in existing_pc_names:
        cur.execute("""
            INSERT OR IGNORE INTO pubchem_data (material_name, SMILES, molecular_formula, MW)
            VALUES (?,?,?,?)
        """, (mat_name, smiles, formula, mw))
        print(f"  pubchem_data: {mat_name} added")

conn.commit()

# Final row counts
cur.execute("SELECT COUNT(*) FROM materials"); n_mat = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM optical_nk"); n_nk = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM calculated_slds"); n_slds = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM calculated_sld"); n_sld = cur.fetchone()[0]
print(f"\n  Final counts: materials={n_mat}  optical_nk={n_nk}  "
      f"calculated_slds={n_slds}  calculated_sld={n_sld}")
print("\n✓ STEP 3 COMPLETE")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — FLAT DATAFRAME + COVERAGE MAP
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 4 — FLAT DATAFRAME + COVERAGE MAP")
print("="*70)

# ── Base: materials ───────────────────────────────────────────────────────────
base = pd.read_sql("SELECT * FROM materials", conn)
base = base.rename(columns={"id": "material_id"})

# ── optical_nk at 633nm (±5nm window) ────────────────────────────────────────
nk_633 = pd.read_sql("""
    SELECT material_id, AVG(n) AS n_633nm, AVG(k) AS k_633nm
    FROM optical_nk
    WHERE wavelength_nm BETWEEN 628 AND 638
    GROUP BY material_id
""", conn)

# ── optical_nk at 785nm (±5nm window) ────────────────────────────────────────
nk_785 = pd.read_sql("""
    SELECT material_id, AVG(n) AS n_785nm, AVG(k) AS k_785nm
    FROM optical_nk
    WHERE wavelength_nm BETWEEN 780 AND 790
    GROUP BY material_id
""", conn)

# ── optical_nk at 980nm (±5nm window) ────────────────────────────────────────
nk_980 = pd.read_sql("""
    SELECT material_id, AVG(n) AS n_980nm, AVG(k) AS k_980nm
    FROM optical_nk
    WHERE wavelength_nm BETWEEN 975 AND 985
    GROUP BY material_id
""", conn)

# ── calculated_slds: mean per material ───────────────────────────────────────
sld_df = pd.read_sql("""
    SELECT material_id,
           AVG(xray_sld_real)    AS xray_sld_real,
           AVG(neutron_sld_real) AS neutron_sld_real
    FROM calculated_slds
    GROUP BY material_id
""", conn)

# ── viscoelasticity: mean per material ───────────────────────────────────────
visco_df = pd.read_sql("""
    SELECT material_id,
           AVG(storage_modulus_pa) AS storage_modulus_pa,
           AVG(loss_modulus_pa)    AS loss_modulus_pa,
           AVG(viscosity_mpa_s)    AS viscosity_mpa_s
    FROM viscoelasticity
    GROUP BY material_id
""", conn)

# ── dielectric (static): mean per material ───────────────────────────────────
diel_df = pd.read_sql("""
    SELECT material_id,
           AVG(dielectric_real) AS dielectric_real_static,
           AVG(dielectric_imag) AS dielectric_imag_static
    FROM dielectric
    GROUP BY material_id
""", conn)

# ── dielectrics (dynamic): mean per material ─────────────────────────────────
dielac_df = pd.read_sql("""
    SELECT material_id,
           AVG(real_permittivity) AS real_permittivity,
           AVG(imag_permittivity) AS imag_permittivity
    FROM dielectrics
    GROUP BY material_id
""", conn)

# ── chemical_descriptors: pivot long → wide ───────────────────────────────────
cd_long = pd.read_sql("SELECT material_id, descriptor_name, value FROM chemical_descriptors", conn)
cd_wide = cd_long.pivot_table(
    index="material_id", columns="descriptor_name", values="value", aggfunc="first"
).reset_index()
cd_wide.columns.name = None

# ── pubchem_data: join by material name ───────────────────────────────────────
pc_df = pd.read_sql("SELECT * FROM pubchem_data", conn)

# ── Build flat df ──────────────────────────────────────────────────────────────
flat = base.copy()
for right, key in [
    (nk_633,    "material_id"),
    (nk_785,    "material_id"),
    (nk_980,    "material_id"),
    (sld_df,    "material_id"),
    (visco_df,  "material_id"),
    (diel_df,   "material_id"),
    (dielac_df, "material_id"),
    (cd_wide,   "material_id"),
]:
    dup = [c for c in right.columns if c != key and c in flat.columns]
    flat = flat.merge(right.drop(columns=dup), on=key, how="left")

# Attach pubchem by name
name_col = "name"
pc_df_r = pc_df.rename(columns={"material_name": name_col})
dup_pc = [c for c in pc_df_r.columns if c != name_col and c in flat.columns]
flat = flat.merge(pc_df_r.drop(columns=dup_pc, errors="ignore"), on=name_col, how="left")

# Drop exact-duplicate columns
flat = flat.loc[:, ~flat.columns.duplicated()]

flat.to_csv(ROOT / "analysis_dataset.csv", index=False)
print(f"\n  Saved: analysis_dataset.csv  shape={flat.shape}")

# Null counts
print("\n  Column null counts (top 10 by nulls):")
null_counts = flat.isnull().sum().sort_values(ascending=False)
for col, cnt in null_counts.head(10).items():
    pct = 100 * cnt / len(flat)
    print(f"    {col:<40} {cnt:>3} nulls ({pct:.0f}%)")

# ── Coverage heatmap ──────────────────────────────────────────────────────────
ID_COLS = {"material_id", "name", "formula", "smiles", "molecular_weight",
           "material_class", "notes", "pubchem_cid",
           "SMILES", "molecular_formula", "material_name"}

# Only keep feature columns (not identifiers) that are numeric or have interesting coverage
feature_cols = [c for c in flat.columns if c not in ID_COLS]
cov_df = flat[["name"] + feature_cols].set_index("name")

# Drop columns that are all-null
cov_df = cov_df.dropna(axis=1, how="all")

# Build binary present/absent matrix
presence = cov_df.notna().astype(float)

# Sort rows by material class then name
flat_sorted = flat.sort_values(["material_class", "name"])
presence = presence.loc[flat_sorted["name"].values]

fig, ax = plt.subplots(figsize=(max(16, len(presence.columns) * 0.55),
                                 max(6,  len(presence) * 0.5 + 2)))
cmap = matplotlib.colors.ListedColormap(["#d62728", "#2ca02c"])
sns.heatmap(
    presence,
    ax=ax,
    cmap=cmap,
    vmin=0, vmax=1,
    linewidths=0.5,
    linecolor="#e0e0e0",
    cbar=False,
    xticklabels=True,
)
ax.set_title("Data Coverage Map — materials × features\n"
             "Green = present  |  Red = null", fontsize=13, fontweight="bold", pad=12)
ax.tick_params(axis="x", rotation=45, labelsize=7.5)
ax.tick_params(axis="y", rotation=0,  labelsize=8.5)
ax.set_ylabel("")

green_patch = mpatches.Patch(color="#2ca02c", label="Present")
red_patch   = mpatches.Patch(color="#d62728", label="Null")
ax.legend(handles=[green_patch, red_patch], loc="upper right",
          bbox_to_anchor=(1.0, -0.18), ncol=2, fontsize=9)

fig.tight_layout()
cov_path = FIG_DIR / "coverage_map.png"
fig.savefig(cov_path, dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"\n  Saved: {cov_path.name}")
print("\n✓ STEP 4 COMPLETE")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — CORRELATION MATRICES (5 targets × 3 figures each = 15 figures)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 5 — CORRELATION MATRICES")
print("="*70)

TARGETS = [
    ("n_633nm",          "n (633 nm refractive index)"),
    ("k_633nm",          "k (633 nm extinction coefficient)"),
    ("xray_sld_real",    "X-ray SLD"),
    ("neutron_sld_real", "Neutron SLD"),
    ("density_g_cm3",    "Density (g/cm³)"),
]

# Columns to always exclude from features
ALWAYS_DROP = {
    "material_id", "name", "formula", "smiles", "molecular_weight",
    "material_class", "notes", "pubchem_cid",
    "SMILES", "molecular_formula", "MW", "material_name",
}

summary_rows = []


def style_heatmap(ax, title):
    ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
    ax.tick_params(axis="x", rotation=45, labelsize=7.5)
    ax.tick_params(axis="y", rotation=0,  labelsize=7.5)


for target_col, target_label in TARGETS:
    print(f"\n  {'─'*60}")
    print(f"  Target: {target_label} ({target_col})")

    if target_col not in flat.columns:
        print(f"  *** '{target_col}' not found — skipping")
        continue

    # Numeric only, drop identifiers
    num_df = flat.select_dtypes(include=[np.number]).copy()
    drop_cols = [c for c in num_df.columns if c.lower() in {s.lower() for s in ALWAYS_DROP}]
    num_df.drop(columns=drop_cols, errors="ignore", inplace=True)

    # Drop zero-variance columns
    for col in list(num_df.columns):
        if num_df[col].dropna().nunique() <= 1:
            num_df.drop(columns=[col], inplace=True)

    if target_col not in num_df.columns:
        print(f"  *** '{target_col}' not numeric — skipping")
        continue

    # Need at least 3 non-null rows to compute correlation
    num_df = num_df.dropna(subset=[target_col])
    num_df = num_df.dropna(axis=1, thresh=3)

    feature_cols = [c for c in num_df.columns if c != target_col]
    if not feature_cols:
        print(f"  No features with ≥3 values — skipping")
        continue

    analysis = num_df[[target_col] + feature_cols]

    # ── Figure A: Full Pearson heatmap ───────────────────────────────────────
    corr_full = analysis.corr(method="pearson")
    n_cols = len(corr_full)

    fig, ax = plt.subplots(figsize=(14, 12))
    sns.heatmap(
        corr_full, ax=ax,
        cmap="RdBu_r", vmin=-1, vmax=1,
        annot=True, fmt=".1f",
        linewidths=0.4, linecolor="#e0e0e0",
        cbar_kws={"shrink": 0.8, "label": "Pearson r"},
        annot_kws={"size": max(5, 8 - n_cols // 8)},
    )
    style_heatmap(ax, f"Full Correlation Matrix — {target_label}")
    fig.tight_layout()
    path_a = FIG_DIR / f"corr_full_{target_col}.png"
    fig.savefig(path_a, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path_a.name}")

    # ── Drop high-correlation pairs (|r|>0.85) ───────────────────────────────
    target_r = corr_full[target_col].drop(target_col).abs()
    to_drop = set()

    for i, fi in enumerate(feature_cols):
        for fj in feature_cols[i+1:]:
            if fi in to_drop or fj in to_drop:
                continue
            if fi not in corr_full.index or fj not in corr_full.columns:
                continue
            r_pair = abs(corr_full.loc[fi, fj])
            if r_pair > 0.85:
                ri = target_r.get(fi, 0)
                rj = target_r.get(fj, 0)
                loser = fj if ri >= rj else fi
                to_drop.add(loser)
                print(f"    High-r pair: {fi} ↔ {fj}  r={r_pair:.3f}  → drop '{loser}'")

    kept = [c for c in feature_cols if c not in to_drop]
    print(f"  Kept ({len(kept)}): {kept}")
    print(f"  Dropped ({len(to_drop)}): {sorted(to_drop)}")

    # ── Figure B: Cleaned heatmap ─────────────────────────────────────────────
    clean_cols = [target_col] + kept
    corr_clean = analysis[clean_cols].corr(method="pearson")
    sz = max(7, len(clean_cols))

    fig, ax = plt.subplots(figsize=(sz, sz - 1))
    sns.heatmap(
        corr_clean, ax=ax,
        cmap="RdBu_r", vmin=-1, vmax=1,
        annot=True, fmt=".2f",
        linewidths=0.4, linecolor="#e0e0e0",
        cbar_kws={"shrink": 0.8, "label": "Pearson r"},
        annot_kws={"size": 9},
    )
    style_heatmap(ax, f"Cleaned Correlation Matrix — {target_label}")
    fig.tight_layout()
    path_b = FIG_DIR / f"corr_cleaned_{target_col}.png"
    fig.savefig(path_b, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path_b.name}")

    # ── p-values and Figure C: ranked bar chart ───────────────────────────────
    bar_data = []
    for feat in kept:
        pair = analysis[[feat, target_col]].dropna()
        if len(pair) < 3:
            r_val, p_val = np.nan, np.nan
        else:
            r_val, p_val = stats.pearsonr(pair[feat], pair[target_col])
        sig = (p_val < 0.05) if not np.isnan(p_val) else False
        bar_data.append({"feature": feat, "r": r_val, "abs_r": abs(r_val) if not np.isnan(r_val) else 0,
                         "p": p_val, "sig": sig})
        summary_rows.append({
            "Feature": feat, "Target": target_col,
            "Pearson_r": round(r_val, 4) if not np.isnan(r_val) else np.nan,
            "P_value":   round(p_val, 4) if not np.isnan(p_val) else np.nan,
            "Significant": "yes" if sig else "no",
            "Decision":    "kept",
        })

    # Also log dropped features to summary
    for feat in to_drop:
        pair = analysis[[feat, target_col]].dropna() if feat in analysis.columns else pd.DataFrame()
        if len(pair) >= 3:
            r_val, p_val = stats.pearsonr(pair[feat], pair[target_col])
            sig = p_val < 0.05
        else:
            r_val, p_val, sig = np.nan, np.nan, False
        summary_rows.append({
            "Feature": feat, "Target": target_col,
            "Pearson_r": round(r_val, 4) if not np.isnan(r_val) else np.nan,
            "P_value":   round(p_val, 4) if not np.isnan(p_val) else np.nan,
            "Significant": "yes" if sig else "no",
            "Decision":    "dropped",
        })

    bar_df = pd.DataFrame(bar_data).sort_values("abs_r", ascending=True)
    fig_h  = max(5, len(bar_df) * 0.42 + 2)

    fig, ax = plt.subplots(figsize=(11, fig_h))
    colors = ["#2ca02c" if s else "#d62728" for s in bar_df["sig"]]
    bars   = ax.barh(bar_df["feature"], bar_df["abs_r"], color=colors,
                     edgecolor="white", height=0.65)

    ax.axvline(0.30, color="#999999", linestyle="--", linewidth=1.0, label="|r|=0.3 weak")
    ax.axvline(0.70, color="#444444", linestyle="--", linewidth=1.5, label="|r|=0.7 strong")

    for bar, row in zip(bars, bar_df.itertuples()):
        r_str = f"{row.r:+.3f}" if not np.isnan(row.r) else "NaN"
        p_str = f"p={row.p:.3f}" if not np.isnan(row.p) else "p=NaN"
        not_sig = "" if row.sig else " ✗"
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{r_str}  {p_str}{not_sig}",
                va="center", ha="left", fontsize=7.5)

    green_p = mpatches.Patch(color="#2ca02c", label="p < 0.05 (significant)")
    red_p   = mpatches.Patch(color="#d62728", label="p ≥ 0.05 (not significant)")
    ax.legend(handles=[green_p, red_p, *ax.get_lines()[:2]],
              loc="lower right", fontsize=8)
    ax.set_xlim(0, 1.3)
    ax.set_xlabel("|Pearson r|", fontsize=10)
    ax.set_title(f"Feature Importance — {target_label}", fontsize=12, fontweight="bold", pad=12)
    sns.despine(left=True, bottom=False)
    fig.tight_layout()
    path_c = FIG_DIR / f"corr_ranked_{target_col}.png"
    fig.savefig(path_c, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path_c.name}")

print("\n✓ STEP 5 COMPLETE")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("STEP 6 — SUMMARY")
print("="*70)

summ_df = pd.DataFrame(summary_rows)
if not summ_df.empty:
    summ_df["Abs_r"] = summ_df["Pearson_r"].abs()
    summ_df = summ_df.sort_values(["Target", "Abs_r"], ascending=[True, False])
summ_df.to_csv(ROOT / "correlation_summary.csv", index=False)
print(f"\n  Saved: correlation_summary.csv ({len(summ_df)} rows)")

print("\n── Top 5 features per target ──────────────────────────────────────────")
for target_col, target_label in TARGETS:
    sub = summ_df[(summ_df["Target"] == target_col) & (summ_df["Decision"] == "kept")]
    sub = sub.dropna(subset=["Abs_r"]).sort_values("Abs_r", ascending=False).head(5)
    if sub.empty:
        continue
    print(f"\n  {target_label}:")
    for _, row in sub.iterrows():
        tag = "✓" if row["Significant"] == "yes" else "✗"
        print(f"    {tag}  {row['Feature']:<32}  r={row['Pearson_r']:+.4f}  p={row['P_value']:.4f}")

print("\n── Features significant (p<0.05) across ALL 5 targets ────────────────")
found_targets = summ_df["Target"].unique()
sig = (
    summ_df[summ_df["Significant"] == "yes"]
    .groupby("Feature")["Target"].nunique()
)
universal = sig[sig == len(found_targets)].index.tolist()
if universal:
    for f in sorted(universal):
        print(f"  {f}")
else:
    print("  None — coverage gaps prevent full cross-target significance.")
    print("  (Increase material count and fill null measurements to unlock.)")

# ── Row / null delta vs previous run ─────────────────────────────────────────
print("\n── Row counts ─────────────────────────────────────────────────────────")
for tbl in ["materials", "optical_nk", "calculated_slds", "calculated_sld",
            "pubchem_data", "chemical_descriptors", "viscoelasticity", "dielectric"]:
    cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
    print(f"  {tbl:<28} {cur.fetchone()[0]:>5} rows")

print(f"\n  analysis_dataset.csv shape: {flat.shape}")
print(f"  Total nulls in flat df:     {flat.isnull().sum().sum()}")

conn.close()
print("\n" + "="*70)
print("ALL STEPS COMPLETE")
print(f"  figures/              → {FIG_DIR}")
print(f"  analysis_dataset.csv  → {ROOT/'analysis_dataset.csv'}")
print(f"  correlation_summary.csv → {ROOT/'correlation_summary.csv'}")
print("="*70)
