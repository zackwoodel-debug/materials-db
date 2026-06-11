#!/usr/bin/env python3
"""
scripts/data_audit_dielectric.py
=================================
6-step data audit and dielectric correlation analysis.

Steps:
  1. Full data audit with physical validity checks → reports/data_audit.txt
  2. Unit consistency checks (wavelength, SLD ranges, modulus, MW cross-check)
  3. Cross-table consistency → reports/consistency_report.txt
  4. Dielectric correlation matrix heatmap → figures/corr_dielectric.png
  5. N-value correlation with dielectric_constant
  6. Export → correlation_summary_dielectric.csv
"""

import io
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

import sqlite3

DB_PATH = "data/materials.db"
FIG_DIR = "figures"
RPT_DIR = "reports"

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(RPT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: DATA AUDIT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: DATA AUDIT")
print("=" * 70)

cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall() if r[0] != "sqlite_sequence"]

audit_buf = io.StringIO()

# Physical validity rules per column name
# (check_fn returns True when a value is INVALID)
VALIDITY_RULES = {
    "density_g_cm3":      ("density < 0",                         lambda v: v < 0),
    "molecular_weight":   ("molecular_weight < 0",                lambda v: v < 0),
    "k":                  ("k < 0",                               lambda v: v < 0),
    # X-ray SLD: Gold reaches ~1.31e-4, so flag > 2e-4 as suspicious
    "sld_xray_real":      ("xray SLD > 2e-4 or < -1e-5",         lambda v: v > 2e-4 or v < -1e-5),
    "xray_sld_real":      ("xray SLD > 2e-4 or < -1e-5",         lambda v: v > 2e-4 or v < -1e-5),
    # Neutron SLD: H-rich materials legitimately reach ~-6e-7, Ti-based ~-2e-5
    "sld_neutron_real":   ("neutron SLD < -5e-5 or > 1e-4",      lambda v: v < -5e-5 or v > 1e-4),
    "neutron_sld_real":   ("neutron SLD < -5e-5 or > 1e-4",      lambda v: v < -5e-5 or v > 1e-4),
    "storage_modulus_pa": ("storage_modulus_pa < 0",              lambda v: v < 0),
    "loss_modulus_pa":    ("loss_modulus_pa < 0",                 lambda v: v < 0),
    "viscosity_mpa_s":    ("viscosity_mpa_s < 0",                 lambda v: v < 0),
    "wavelength_nm":      ("wavelength_nm <= 0",                  lambda v: v <= 0),
}

# For optical n: split into impossible (n<=0) and metal-physics note (0<n<1 or n>5)
N_IMPOSSIBLE_LIMIT = 0
N_SUSPICIOUS_HIGH  = 10

def audit_table(tbl, buf):
    df = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)
    sep = "─" * 60
    buf.write(f"\n{sep}\n")
    buf.write(f"TABLE: {tbl}  [{len(df)} rows × {len(df.columns)} cols]\n")
    buf.write(f"Columns: {list(df.columns)}\n")

    issues = []
    for col in df.columns:
        nulls = df[col].isna().sum()
        if nulls:
            buf.write(f"  NULL  {col}: {nulls}/{len(df)}\n")

        if not pd.api.types.is_numeric_dtype(df[col]):
            continue

        vals = df[col].dropna()
        if len(vals):
            buf.write(
                f"  STAT  {col}: min={vals.min():.6g}  "
                f"max={vals.max():.6g}  mean={vals.mean():.6g}  n={len(vals)}\n"
            )

        # Standard validity rules
        if col in VALIDITY_RULES:
            msg, check_fn = VALIDITY_RULES[col]
            bad = df[df[col].notna() & df[col].apply(check_fn)]
            if len(bad):
                id_col = "id" if "id" in df.columns else df.columns[0]
                ids = bad[id_col].tolist()[:10]
                buf.write(f"  FAIL  {col}: {msg}  →  {len(bad)} rows, ids: {ids}\n")
                issues.append(f"{msg} in {len(bad)} rows")

        # Special treatment for refractive index n
        if col == "n":
            impossible = df[(df[col].notna()) & (df[col] <= N_IMPOSSIBLE_LIMIT)]
            suspicious = df[(df[col].notna()) & (df[col] > N_SUSPICIOUS_HIGH)]
            metal_note = df[(df[col].notna()) & (df[col] > 0) & (df[col] < 1)]

            if len(impossible):
                ids = impossible["id"].tolist()[:10]
                buf.write(f"  FAIL  n <= 0 (physically impossible): {len(impossible)} rows, ids: {ids}\n")
                issues.append(f"n <= 0 in {len(impossible)} rows — impossible")
            if len(suspicious):
                ids = suspicious["id"].tolist()[:10]
                buf.write(
                    f"  WARN  n > {N_SUSPICIOUS_HIGH} (unusually high): {len(suspicious)} rows, ids: {ids}\n"
                )
                issues.append(f"n > {N_SUSPICIOUS_HIGH} in {len(suspicious)} rows — suspicious")
            if len(metal_note):
                mat_ids = df[(df[col].notna()) & (df[col] > 0) & (df[col] < 1)]["material_id"].unique().tolist() if "material_id" in df.columns else []
                buf.write(
                    f"  NOTE  n in (0,1): {len(metal_note)} rows (metallic regime — "
                    f"physically valid for metals below plasma frequency), "
                    f"material_ids: {mat_ids}\n"
                )

    if issues:
        status = f"FAIL  ({'; '.join(issues)})"
    else:
        status = "PASS"
    buf.write(f"  STATUS: {status}\n")
    print(f"  [{tbl}]  →  {status}")
    return status


table_statuses = {}
for tbl in tables:
    table_statuses[tbl] = audit_table(tbl, audit_buf)

audit_report_path = f"{RPT_DIR}/data_audit.txt"
with open(audit_report_path, "w") as f:
    f.write("DATA AUDIT REPORT\n")
    f.write("=" * 70 + "\n")
    f.write(audit_buf.getvalue())
    f.write("\n\nSUMMARY\n" + "=" * 40 + "\n")
    for t, s in table_statuses.items():
        f.write(f"  {t:<30} {s}\n")

print(f"\n  Saved: {audit_report_path}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: UNIT CONSISTENCY CHECK
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: UNIT CONSISTENCY CHECK")
print("=" * 70)

unit_issues = []

# --- Wavelength range (optical_nk should be in nm, plausible range 50–20000) ---
wl_stats = pd.read_sql(
    "SELECT MIN(wavelength_nm) wl_min, MAX(wavelength_nm) wl_max FROM optical_nk", conn
).values[0]
print(f"  optical_nk wavelength range: {wl_stats[0]:.1f} – {wl_stats[1]:.1f} nm")
if wl_stats[0] < 50 or wl_stats[1] > 20000:
    unit_issues.append(f"optical_nk wavelength out of plausible nm range: {wl_stats[0]}–{wl_stats[1]}")
    print("  WARN: wavelength appears NOT to be in nm")
else:
    print("  PASS: wavelength in plausible nm range (50–20000)")

wl_sld = pd.read_sql(
    "SELECT MIN(wavelength_nm) wl_min, MAX(wavelength_nm) wl_max FROM calculated_sld", conn
).values[0]
print(f"  calculated_sld wavelength range: {wl_sld[0]:.1f} – {wl_sld[1]:.1f} nm")

# --- SLD range validation ---
for tbl, xcol, ncol in [
    ("calculated_sld",  "sld_xray_real",  "sld_neutron_real"),
    ("calculated_slds", "xray_sld_real",  "neutron_sld_real"),
]:
    df_s = pd.read_sql(f"SELECT {xcol}, {ncol} FROM [{tbl}]", conn)
    xr = df_s[xcol].dropna()
    nr = df_s[ncol].dropna()
    print(f"\n  {tbl}")
    print(f"    X-ray SLD:   {xr.min():.4e} – {xr.max():.4e} Å⁻²  (expected ~8e-9 to 1.5e-4)")
    print(f"    Neutron SLD: {nr.min():.4e} – {nr.max():.4e} Å⁻²  (expected ~-6e-7 to 7e-6)")
    if xr.max() > 2e-4:
        unit_issues.append(f"{tbl}.{xcol} max exceeds 2e-4 Å⁻²: {xr.max():.4e}")
    if nr.min() < -1e-4:
        unit_issues.append(f"{tbl}.{ncol} min below -1e-4 Å⁻²: {nr.min():.4e}")

# --- Modulus relationship: tan(δ) = loss/storage ---
vis = pd.read_sql(
    "SELECT v.material_id, m.name, v.storage_modulus_pa, v.loss_modulus_pa "
    "FROM viscoelasticity v JOIN materials m ON v.material_id=m.id "
    "WHERE v.storage_modulus_pa IS NOT NULL AND v.loss_modulus_pa IS NOT NULL",
    conn,
)
print("\n  Viscoelasticity tan(δ) = loss / storage:")
for _, row in vis.iterrows():
    s = row["storage_modulus_pa"]
    tan_d = row["loss_modulus_pa"] / s if s != 0 else float("nan")
    flag = "  WARN: viscous-dominated (tan_δ > 1)" if pd.notna(tan_d) and abs(tan_d) > 1 else ""
    print(f"    {row['name']:<20}  E'={s:.3e} Pa  tan_δ={tan_d:.4f}{flag}")
    if pd.notna(tan_d) and abs(tan_d) > 1:
        unit_issues.append(f"tan_δ > 1 for {row['name']}: {tan_d:.3f}")

# --- MW cross-table agreement ---
mat = pd.read_sql(
    "SELECT name, molecular_weight FROM materials WHERE molecular_weight IS NOT NULL", conn
)
pub = pd.read_sql(
    "SELECT material_name, MW FROM pubchem_data WHERE MW IS NOT NULL", conn
)
mw_merged = mat.merge(pub, left_on="name", right_on="material_name", how="inner")
mw_merged["diff_pct"] = (
    abs(mw_merged["molecular_weight"] - mw_merged["MW"]) / mw_merged["MW"] * 100
)
print("\n  MW cross-table check (materials.molecular_weight vs pubchem_data.MW):")
for _, row in mw_merged.iterrows():
    flag = "  WARN >5%" if row["diff_pct"] > 5 else "  OK"
    print(
        f"    {row['name']:<20}  materials={row['molecular_weight']:.5g}"
        f"  pubchem={row['MW']:.5g}  diff={row['diff_pct']:.2f}%{flag}"
    )
    if row["diff_pct"] > 5:
        unit_issues.append(
            f"MW mismatch >5% for {row['name']}: materials={row['molecular_weight']} "
            f"vs pubchem={row['MW']}"
        )

print(f"\n  Total unit consistency issues: {len(unit_issues)}")
for iss in unit_issues:
    print(f"    - {iss}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: CROSS-TABLE CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: CROSS-TABLE CONSISTENCY")
print("=" * 70)

cons_buf  = io.StringIO()
cons_issues = []

def cprint(msg):
    print("  " + msg)
    cons_buf.write(msg + "\n")

mat_all  = pd.read_sql("SELECT id, name FROM materials", conn)
mat_ids  = set(mat_all["id"].astype(int))
mat_names = set(mat_all["name"])

cprint(f"materials table: {len(mat_all)} rows  IDs: {sorted(mat_ids)}")

# FK integrity
fk_tables = {
    "optical_nk":           "material_id",
    "calculated_sld":       "material_id",
    "calculated_slds":      "material_id",
    "chemical_descriptors": "material_id",
    "dielectric":           "material_id",
    "dielectrics":          "material_id",
    "viscoelasticity":      "material_id",
}
cprint("")
for tbl, fk_col in fk_tables.items():
    df_fk = pd.read_sql(f"SELECT DISTINCT {fk_col} FROM [{tbl}]", conn)
    orphans = set(df_fk[fk_col].dropna().astype(int)) - mat_ids
    if orphans:
        cons_issues.append(f"Orphan {fk_col}s in {tbl}: {orphans}")
        cprint(f"FAIL {tbl}: orphan material_ids = {orphans}")
    else:
        cprint(f"PASS {tbl}: all material_ids exist in materials")

# pubchem name alignment
pub_names = set(
    pd.read_sql("SELECT material_name FROM pubchem_data", conn)["material_name"]
)
name_delta = pub_names - mat_names
if name_delta:
    cons_issues.append(f"pubchem_data names not in materials.name: {name_delta}")
    cprint(f"WARN pubchem_data: names not matching materials → {name_delta}")
else:
    cprint("PASS pubchem_data: all material_names match materials.name")

# Density coverage
dens_df = pd.read_sql("SELECT id, name, density_g_cm3 FROM materials", conn)
missing_dens = dens_df[dens_df["density_g_cm3"].isna()]
cprint(f"\nDensity coverage: {dens_df['density_g_cm3'].notna().sum()}/17")
if len(missing_dens):
    cprint(f"  Missing density: {missing_dens['name'].tolist()}")
    cons_issues.append(f"Missing density for {len(missing_dens)} materials: {missing_dens['name'].tolist()}")

# Completeness matrix
cprint("\nMaterial completeness matrix (presence across 7 FK tables):")
presence = {
    tbl: set(
        pd.read_sql(f"SELECT DISTINCT {fk_col} FROM [{tbl}]", conn)[fk_col]
        .dropna().astype(int)
    )
    for tbl, fk_col in fk_tables.items()
}
for _, row in mat_all.iterrows():
    mid = row["id"]
    present_in = [t for t, s in presence.items() if mid in s]
    cprint(f"  {row['name']:<20} id={mid:<3}  {len(present_in)}/7  → {', '.join(present_in)}")

# Dielectric value agreement between the two dielectric tables
in_diel_a = set(
    pd.read_sql("SELECT DISTINCT material_id FROM dielectric", conn)["material_id"].astype(int)
)
in_diel_b = set(
    pd.read_sql("SELECT DISTINCT material_id FROM dielectrics", conn)["material_id"].astype(int)
)
both_diel = in_diel_a & in_diel_b
cprint(f"\nMaterials in BOTH dielectric tables: {both_diel} (ids)")
if both_diel:
    for mid in sorted(both_diel):
        mname = mat_all[mat_all["id"] == mid]["name"].values[0]
        dr = pd.read_sql(
            f"SELECT AVG(dielectric_real) v FROM dielectric WHERE material_id={mid}", conn
        )["v"].values[0]
        ds = pd.read_sql(
            f"SELECT AVG(real_permittivity) v FROM dielectrics WHERE material_id={mid}", conn
        )["v"].values[0]
        diff_pct = abs(dr - ds) / ds * 100 if ds else None
        flag = (
            f"  WARN diff={diff_pct:.1f}%"
            if diff_pct is not None and diff_pct > 5
            else "  OK"
        )
        cprint(
            f"  {mname:<20} dielectric.dielectric_real={dr:.4g}"
            f"  dielectrics.real_permittivity={ds:.4g}{flag}"
        )
        if diff_pct is not None and diff_pct > 5:
            cons_issues.append(
                f"Dielectric value mismatch for {mname}: {dr:.4g} vs {ds:.4g} ({diff_pct:.1f}%)"
            )

consistency_report_path = f"{RPT_DIR}/consistency_report.txt"
with open(consistency_report_path, "w") as f:
    f.write("CROSS-TABLE CONSISTENCY REPORT\n")
    f.write("=" * 70 + "\n")
    f.write(cons_buf.getvalue())
    f.write("\nISSUES SUMMARY\n" + "=" * 40 + "\n")
    if cons_issues:
        for iss in cons_issues:
            f.write(f"  - {iss}\n")
    else:
        f.write("  No issues found.\n")

print(f"\n  Saved: {consistency_report_path}")
print(f"  Issues found: {len(cons_issues)}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: DIELECTRIC CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4: DIELECTRIC CORRELATION MATRIX")
print("=" * 70)

# ── Build flat dataset ──────────────────────────────────────────────────────
mat_base = pd.read_sql(
    "SELECT id AS material_id, name, density_g_cm3, molecular_weight FROM materials", conn
)

# Unified dielectric constant:
# Primary: dielectric.dielectric_real (9 materials, DC static)
# Secondary: dielectrics.real_permittivity (3 materials, 1 kHz)
diel_a = pd.read_sql("SELECT material_id, dielectric_real FROM dielectric", conn)
diel_a = diel_a.groupby("material_id", as_index=False)["dielectric_real"].mean()
diel_a.rename(columns={"dielectric_real": "dielectric_const"}, inplace=True)

diel_b = pd.read_sql("SELECT material_id, real_permittivity FROM dielectrics", conn)
diel_b = diel_b.groupby("material_id", as_index=False)["real_permittivity"].mean()
diel_b.rename(columns={"real_permittivity": "dielectric_const_b"}, inplace=True)

flat = mat_base.merge(diel_a, on="material_id", how="left")
flat = flat.merge(diel_b, on="material_id", how="left")
# Fill from secondary table only where primary is missing
flat["dielectric_const"] = flat["dielectric_const"].fillna(flat["dielectric_const_b"])
flat.drop(columns=["dielectric_const_b"], inplace=True)

# Optical n, k at 633 nm (nearest wavelength within 630–636)
nk633 = pd.read_sql(
    "SELECT material_id, n AS n_633nm, k AS k_633nm FROM optical_nk "
    "WHERE wavelength_nm BETWEEN 630 AND 636 "
    "ORDER BY material_id, ABS(wavelength_nm - 633.0)",
    conn,
)
nk633 = nk633.groupby("material_id", as_index=False).first()

# Optical n, k at 785 nm
nk785 = pd.read_sql(
    "SELECT material_id, n AS n_785nm, k AS k_785nm FROM optical_nk "
    "WHERE wavelength_nm BETWEEN 780 AND 790 "
    "ORDER BY material_id, ABS(wavelength_nm - 785.0)",
    conn,
)
nk785 = nk785.groupby("material_id", as_index=False).first()

# Average SLDs from calculated_slds (uses xray_sld_real / neutron_sld_real)
sld_df = pd.read_sql(
    "SELECT material_id, "
    "       AVG(xray_sld_real)   AS xray_sld, "
    "       AVG(neutron_sld_real) AS neutron_sld "
    "FROM calculated_slds GROUP BY material_id",
    conn,
)

# Viscoelasticity (aggregate per material)
vis_df = pd.read_sql(
    "SELECT material_id, "
    "       AVG(storage_modulus_pa) AS storage_modulus_pa, "
    "       AVG(loss_modulus_pa)    AS loss_modulus_pa, "
    "       AVG(viscosity_mpa_s)    AS viscosity_mpa_s "
    "FROM viscoelasticity GROUP BY material_id",
    conn,
)

# Chemical descriptors (long → wide)
cd = pd.read_sql(
    "SELECT material_id, descriptor_name, value FROM chemical_descriptors", conn
)
cd_wide = (
    cd.pivot_table(index="material_id", columns="descriptor_name", values="value", aggfunc="first")
    .reset_index()
)
cd_wide.columns.name = None

# PubChem MW and XLogP (supplemental)
pub_slim = pd.read_sql(
    "SELECT p.MW AS pubchem_MW, p.XLogP, m.id AS material_id "
    "FROM pubchem_data p JOIN materials m ON p.material_name = m.name",
    conn,
)

# Assemble
for df_part in [nk633, nk785, sld_df, vis_df, cd_wide, pub_slim]:
    flat = flat.merge(df_part, on="material_id", how="left")

print(f"  Flat dataset shape: {flat.shape}")

# Coverage summary for key columns
key_cols = ["dielectric_const", "n_633nm", "k_633nm", "n_785nm",
            "xray_sld", "neutron_sld", "density_g_cm3",
            "storage_modulus_pa", "viscosity_mpa_s"]
for kc in key_cols:
    if kc in flat.columns:
        print(f"    {kc:<30} non-null: {flat[kc].notna().sum()}/{len(flat)}")

# ── Correlation matrix ──────────────────────────────────────────────────────
num_cols = flat.select_dtypes(include=[np.number]).columns.tolist()
num_cols = [c for c in num_cols if c != "material_id"]

MIN_PAIRS = 4
valid_cols = [c for c in num_cols if flat[c].notna().sum() >= MIN_PAIRS]
print(f"\n  Columns with ≥{MIN_PAIRS} non-null: {len(valid_cols)} of {len(num_cols)}")

heatmap_data = flat[valid_cols].corr(method="pearson")

n_v = len(valid_cols)
fig_size = max(12, n_v * 0.85)
fig, ax = plt.subplots(figsize=(fig_size, fig_size * 0.85))

mask = np.triu(np.ones_like(heatmap_data, dtype=bool), k=1)
sns.heatmap(
    heatmap_data,
    mask=mask,
    annot=True,
    fmt=".2f",
    cmap="RdBu_r",
    vmin=-1,
    vmax=1,
    linewidths=0.35,
    square=True,
    ax=ax,
    annot_kws={"size": 7},
    cbar_kws={"label": "Pearson r", "shrink": 0.65},
)
ax.set_title(
    "Materials Dataset — Pearson Correlation Matrix\n"
    "(dielectric + optical n,k + SLD + mechanical + chemical descriptors)",
    fontsize=12,
    pad=14,
)
plt.xticks(rotation=45, ha="right", fontsize=7.5)
plt.yticks(rotation=0, fontsize=7.5)
plt.tight_layout()
fig_path = f"{FIG_DIR}/corr_dielectric.png"
plt.savefig(fig_path, dpi=300, bbox_inches="tight")
plt.close()
print(f"  Saved: {fig_path}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: N-VALUE CORRELATION WITH DIELECTRIC CONSTANT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 5: N-VALUE CORRELATION CHECK")
print("=" * 70)

# Identify all columns whose name contains the letter n (case-insensitive)
n_cols = [
    c for c in flat.columns
    if "n" in c.lower() and c not in ("name", "material_id", "dielectric_const")
]
print(f"  Columns containing 'n' (case-insensitive): {n_cols}\n")

print(f"  {'Column':<30} {'Non-null':>8}  {'r':>8}  {'p':>8}  {'N_pairs':>8}  Significant")
print("  " + "-" * 75)

n_corr_rows = []
for nc in n_cols:
    sub = flat[[nc, "dielectric_const"]].dropna()
    N = len(sub)
    if N >= 3:
        r, p = stats.pearsonr(sub[nc], sub["dielectric_const"])
        sig = "YES" if p < 0.05 else "no"
        flag = "  [UNRELIABLE]" if N < 6 else ""
        print(
            f"  {nc:<30} {flat[nc].notna().sum():>8}  {r:>+8.4f}  {p:>8.4f}  {N:>8}  {sig}{flag}"
        )
        n_corr_rows.append(
            {
                "Feature_A": nc,
                "Feature_B": "dielectric_const",
                "Pearson_r": r,
                "P_value": p,
                "N_pairs": N,
                "Significant": sig,
                "UNRELIABLE": N < 6,
            }
        )
    else:
        print(f"  {nc:<30} {flat[nc].notna().sum():>8}  {'—':>8}  {'—':>8}  {N:>8}  insufficient pairs")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: FULL CORRELATION EXPORT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 6: EXPORT CORRELATION SUMMARY")
print("=" * 70)

# All valid_cols vs dielectric_const
export_rows = []
for col in valid_cols:
    if col == "dielectric_const":
        continue
    sub = flat[[col, "dielectric_const"]].dropna()
    N = len(sub)
    if N < 2:
        continue
    r, p = stats.pearsonr(sub[col], sub["dielectric_const"])
    sig = "YES" if p < 0.05 else "no"
    export_rows.append(
        {
            "Feature_A": col,
            "Feature_B": "dielectric_const",
            "Pearson_r": round(r, 6),
            "P_value": round(p, 6),
            "N_pairs": N,
            "Significant": sig,
            "UNRELIABLE": N < 6,
        }
    )

corr_csv = pd.DataFrame(export_rows).sort_values("Pearson_r", key=abs, ascending=False)
csv_path = "correlation_summary_dielectric.csv"
corr_csv.to_csv(csv_path, index=False)
print(f"  Saved: {csv_path}  ({len(corr_csv)} rows)")

print(f"\n  Top 15 correlations with dielectric_const (by |r|):")
print(corr_csv.head(15).to_string(index=False))

unreliable = corr_csv["UNRELIABLE"].sum()
significant = (corr_csv["Significant"] == "YES").sum()
print(f"\n  Total features tested: {len(corr_csv)}")
print(f"  Significant (p < 0.05): {significant}")
print(f"  UNRELIABLE  (N_pairs < 6): {unreliable}")

conn.close()
print("\n" + "=" * 70)
print("ALL 6 STEPS COMPLETE")
print("=" * 70)
