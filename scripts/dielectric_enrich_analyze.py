#!/usr/bin/env python3
"""
scripts/dielectric_enrich_analyze.py
=====================================
Steps:
  1. Insert missing dielectric data for Gold, Silver, TiO2, BSA, Chromium, PEI
  2. Add measurement_regime column to dielectric table; classify all rows
  3. Rebuild flat DataFrame; run correlation matrices (low-freq + all) +
     Maxwell-relation scatter plot
  4. Power analysis for non-significant correlations
  5. Regenerate correlation_summary_dielectric.csv with measurement_regime column
"""

import os
import warnings
import io

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

DB_PATH = "data/materials.db"
FIG_DIR = "figures"
RPT_DIR = "reports"
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(RPT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur  = conn.cursor()

# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def mat_id(name):
    row = cur.execute("SELECT id FROM materials WHERE name=?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Material '{name}' not found in materials table")
    return row[0]

def already_in_dielectric(mid, freq):
    """Return True if (material_id, frequency_hz) pair already exists."""
    return cur.execute(
        "SELECT 1 FROM dielectric WHERE material_id=? AND frequency_hz=?",
        (mid, freq),
    ).fetchone() is not None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — INSERT MISSING DIELECTRIC DATA
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 1 — INSERT MISSING DIELECTRIC DATA")
print("=" * 65)

# Confirm which of the 6 target materials are truly absent
target_names = ["Gold", "Silver", "TiO2", "BSA", "Chromium", "PEI"]
for name in target_names:
    mid = mat_id(name)
    in_d  = cur.execute("SELECT 1 FROM dielectric  WHERE material_id=?", (mid,)).fetchone()
    in_ds = cur.execute("SELECT 1 FROM dielectrics WHERE material_id=?", (mid,)).fetchone()
    status = "PRESENT" if (in_d or in_ds) else "ABSENT"
    print(f"  {name:<12} id={mid:<3}  {status}")

print()

# Data to insert — columns:
#   material_name, dielectric_real, dielectric_imag, freq_hz, temp_c,
#   wavelength_nm, notes
# NULL for tan_delta (computed, not stored separately)
INSERT_DATA = [
    # name          ε_real  ε_imag   freq_hz  temp_c  wl_nm   notes
    ("Gold",        -24.0,   1.5,    3e14,    25.0,   633.0,  "Drude model 633nm"),
    ("Silver",      -15.0,   0.4,    3e14,    25.0,   633.0,  "Drude model 633nm"),
    ("TiO2",         86.0,   0.01,   1000.0,  25.0,   None,   "literature bulk 1 kHz"),
    ("BSA",           4.0,   0.2,    1000.0,  25.0,   None,   "protein film literature 1 kHz"),
    ("Chromium",    -10.7,   20.7,   3e14,    25.0,   633.0,  "Palik handbook 633nm"),
    ("PEI",           3.8,   0.04,   1000.0,  25.0,   None,   "polymer literature 1 kHz"),
]

inserted = 0
skipped  = 0
for name, eps_r, eps_i, freq, temp, wl, note in INSERT_DATA:
    mid = mat_id(name)
    if already_in_dielectric(mid, freq):
        print(f"  SKIP  {name:<12} — already in dielectric (mid={mid}, freq={freq:.3g})")
        skipped += 1
        continue
    cur.execute(
        """
        INSERT INTO dielectric
            (material_id, wavelength_nm, frequency_hz,
             dielectric_real, dielectric_imag, temperature_C, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (mid, wl, freq, eps_r, eps_i, temp, note),
    )
    print(f"  INSERT {name:<12} id={mid:<3}  ε_r={eps_r:>7.2f}  ε_i={eps_i:>5.3f}  "
          f"freq={freq:.3g} Hz  notes={note!r}")
    inserted += 1

conn.commit()
print(f"\n  Inserted: {inserted}  Skipped (already present): {skipped}")

cur.execute("SELECT COUNT(*) FROM dielectric")
print(f"  dielectric table now has {cur.fetchone()[0]} rows")
print("✓ Step 1 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — ADD measurement_regime COLUMN + CLASSIFY ALL ROWS
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 2 — ADD / UPDATE measurement_regime COLUMN")
print("=" * 65)

cur.execute("PRAGMA table_info(dielectric)")
existing_cols = {row[1] for row in cur.fetchall()}

if "measurement_regime" not in existing_cols:
    cur.execute("ALTER TABLE dielectric ADD COLUMN measurement_regime TEXT")
    conn.commit()
    print("  Added column: dielectric.measurement_regime")
else:
    print("  Column measurement_regime already exists — updating values")

# Classification rules (NULL or 0 freq treated as low_frequency)
cur.execute("""
    UPDATE dielectric
    SET measurement_regime =
        CASE
            WHEN frequency_hz IS NULL  THEN 'low_frequency'
            WHEN frequency_hz < 1e9    THEN 'low_frequency'
            ELSE                            'optical_frequency'
        END
""")
conn.commit()

regime_counts = pd.read_sql(
    "SELECT measurement_regime, COUNT(*) n FROM dielectric GROUP BY measurement_regime",
    conn,
)
print(f"  Regime classification:\n{regime_counts.to_string(index=False)}")

# Print full dielectric table after updates
full_diel = pd.read_sql(
    "SELECT d.id, m.name, d.frequency_hz, d.dielectric_real, "
    "       d.dielectric_imag, d.temperature_C, d.measurement_regime, d.notes "
    "FROM dielectric d JOIN materials m ON d.material_id = m.id "
    "ORDER BY d.measurement_regime, d.id",
    conn,
)
print(f"\n  Full dielectric table ({len(full_diel)} rows):")
print(full_diel.to_string(index=False))
print("✓ Step 2 complete")


# ─────────────────────────────────────────────────────────────────────────────
# helpers shared by steps 3-5
# ─────────────────────────────────────────────────────────────────────────────
def pearson_safe(a, b):
    """Return (r, p, n) or (nan, nan, n) when n < 2."""
    sub = pd.DataFrame({"a": a, "b": b}).dropna()
    n = len(sub)
    if n < 2:
        return float("nan"), float("nan"), n
    r, p = stats.pearsonr(sub["a"], sub["b"])
    return float(r), float(p), n


def n_needed_80pct(r, alpha=0.05):
    """Sample size for 80% power at observed r, two-tailed."""
    z_alpha = 1.96    # z for α/2 = 0.025
    z_beta  = 0.842   # z for β  = 0.20 (80% power)
    if abs(r) < 1e-9:
        return float("inf")
    fz = np.arctanh(abs(r))
    n = ((z_alpha + z_beta) / fz) ** 2 + 3
    return int(np.ceil(n))


def correlation_heatmap(df_num, title, save_path, min_pairs=4):
    """Lower-triangle Pearson heatmap. Only include cols with ≥ min_pairs non-null."""
    valid = [c for c in df_num.columns if df_num[c].notna().sum() >= min_pairs]
    corr  = df_num[valid].corr(method="pearson")
    n_v   = len(valid)
    sz    = max(9, n_v * 0.95)
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
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(rotation=0, fontsize=8)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")
    return corr


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — REBUILD FLAT DATAFRAME + CORRELATION MATRICES
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 3 — REBUILD FLAT DATAFRAME + CORRELATION MATRICES")
print("=" * 65)

# ── base: materials ──────────────────────────────────────────────────────────
mat_df = pd.read_sql(
    "SELECT id AS material_id, name, density_g_cm3, molecular_weight FROM materials",
    conn,
)

# ── dielectric (primary source, all regimes) ─────────────────────────────────
diel_df = pd.read_sql(
    "SELECT material_id, dielectric_real, dielectric_imag, "
    "       frequency_hz AS diel_freq_hz, measurement_regime "
    "FROM dielectric",
    conn,
)
# One row per material — for materials with multiple entries pick the most
# informative one (lowest freq for low_freq regime, or optical_freq)
# Strategy: prefer low_frequency DC row; if none, take optical_freq row
diel_low  = diel_df[diel_df["measurement_regime"] == "low_frequency"].copy()
diel_opt  = diel_df[diel_df["measurement_regime"] == "optical_frequency"].copy()

diel_low_agg = diel_low.groupby("material_id", as_index=False).agg(
    dielectric_real  =("dielectric_real",  "mean"),
    dielectric_imag  =("dielectric_imag",  "mean"),
    measurement_regime=("measurement_regime", "first"),
)
diel_opt_agg = diel_opt.groupby("material_id", as_index=False).agg(
    dielectric_real  =("dielectric_real",  "mean"),
    dielectric_imag  =("dielectric_imag",  "mean"),
    measurement_regime=("measurement_regime", "first"),
)

# Combined: low_freq preferred, fill gaps from optical
diel_all = pd.concat([diel_low_agg, diel_opt_agg], ignore_index=True)
diel_all = diel_all.drop_duplicates("material_id", keep="first")

# ── optical n,k at 633 nm ────────────────────────────────────────────────────
nk633 = pd.read_sql(
    "SELECT material_id, n AS n_633nm, k AS k_633nm "
    "FROM optical_nk "
    "WHERE wavelength_nm BETWEEN 630 AND 636 "
    "ORDER BY material_id, ABS(wavelength_nm - 633.0)",
    conn,
)
nk633 = nk633.groupby("material_id", as_index=False).first()

# ── SLDs (averaged per material across wavelengths in calculated_slds) ────────
sld_df = pd.read_sql(
    "SELECT material_id, "
    "       AVG(xray_sld_real)    AS xray_sld_real, "
    "       AVG(neutron_sld_real) AS neutron_sld_real "
    "FROM calculated_slds GROUP BY material_id",
    conn,
)

# ── chemical descriptors wide pivot ──────────────────────────────────────────
cd = pd.read_sql(
    "SELECT material_id, descriptor_name, value FROM chemical_descriptors", conn
)
cd_wide = (
    cd.pivot_table(index="material_id", columns="descriptor_name",
                   values="value", aggfunc="first")
    .reset_index()
)
cd_wide.columns.name = None

# For correlation features we want: MolWt (MW), MolLogP (LogP), TPSA
# Normalise name variants
rename_cd = {}
for col in cd_wide.columns:
    if col in ("MolWt", "ExactMolWt", "exact_mass"):
        rename_cd[col] = "MW"
    elif col in ("MolLogP", "logP"):
        rename_cd[col] = "LogP"
if rename_cd:
    cd_wide.rename(columns=rename_cd, inplace=True)
# Keep one copy if renamed to same name
cd_wide = cd_wide.loc[:, ~cd_wide.columns.duplicated(keep="first")]

# ── assemble flat ─────────────────────────────────────────────────────────────
flat = mat_df.copy()
for part in [diel_all, nk633, sld_df, cd_wide]:
    flat = flat.merge(part, on="material_id", how="left")

print(f"  Flat dataset: {flat.shape[0]} materials × {flat.shape[1]} columns")
print(f"  dielectric_real  non-null: {flat['dielectric_real'].notna().sum()}")
print(f"  n_633nm          non-null: {flat['n_633nm'].notna().sum()}")
print(f"  measurement_regime counts:")
print(flat["measurement_regime"].value_counts(dropna=False).to_string())

# ── Matrix A: low-frequency materials only ────────────────────────────────────
print("\n  --- Matrix A: low_frequency materials ---")
flat_low = flat[flat["measurement_regime"] == "low_frequency"].copy()
print(f"  N = {len(flat_low)} materials")
print(f"  {flat_low['name'].tolist()}")

FEATURES_A = [
    "dielectric_real", "n_633nm", "density_g_cm3", "MW", "LogP", "TPSA",
    "xray_sld_real", "neutron_sld_real",
]
available_A = [f for f in FEATURES_A if f in flat_low.columns]
missing_A   = [f for f in FEATURES_A if f not in flat_low.columns]
if missing_A:
    print(f"  NOTE: columns not found and skipped: {missing_A}")

correlation_heatmap(
    flat_low[available_A].astype(float),
    "Dielectric Matrix A — Low-Frequency Materials Only\n"
    "(DC / kHz permittivity vs structural features)",
    f"{FIG_DIR}/corr_dielectric_lowfreq.png",
    min_pairs=4,
)

# ── Matrix B: all materials (dielectric_real + all numeric features) ──────────
print("\n  --- Matrix B: all materials ---")
print(f"  N = {len(flat[flat['dielectric_real'].notna()])} materials with dielectric_real")

num_all = flat.select_dtypes(include=[np.number]).columns.tolist()
num_all = [c for c in num_all if c != "material_id"]
correlation_heatmap(
    flat[num_all].astype(float),
    "Dielectric Matrix B — All Materials\n"
    "(full feature × feature Pearson correlation)",
    f"{FIG_DIR}/corr_dielectric_all.png",
    min_pairs=4,
)

# ── Maxwell-relation scatter: dielectric_real vs n²  ─────────────────────────
print("\n  --- Maxwell relation scatter plot ---")
mx = flat[["name", "n_633nm", "k_633nm", "dielectric_real", "measurement_regime"]].dropna(
    subset=["n_633nm", "dielectric_real"]
)
mx["n2"] = mx["n_633nm"] ** 2

# For metals: ε_real = n² - k²  (real part of (n+ik)²)
# Annotate both forms
mx["n2_minus_k2"] = mx["n_633nm"] ** 2 - mx["k_633nm"].fillna(0) ** 2

print(f"  Materials in Maxwell plot: {len(mx)}")
print(mx[["name", "n_633nm", "k_633nm", "n2", "n2_minus_k2", "dielectric_real",
          "measurement_regime"]].to_string(index=False))

fig, ax = plt.subplots(figsize=(9, 7))

colors = {"low_frequency": "#2166ac", "optical_frequency": "#d6604d"}
markers = {"low_frequency": "o", "optical_frequency": "^"}

for regime, grp in mx.groupby("measurement_regime", dropna=False):
    if pd.isna(regime):
        regime = "unknown"
    col  = colors.get(regime, "#555555")
    mark = markers.get(regime, "s")
    ax.scatter(grp["n2"], grp["dielectric_real"],
               color=col, marker=mark, s=80, zorder=3,
               label=regime.replace("_", " ").title())

# Label each point
for _, row in mx.iterrows():
    ax.annotate(
        row["name"],
        (row["n2"], row["dielectric_real"]),
        xytext=(5, 3), textcoords="offset points",
        fontsize=8,
        path_effects=[pe.withStroke(linewidth=2, foreground="white")],
    )

# Linear fit: dielectric_real ~ n²
sub_fit = mx[["n2", "dielectric_real"]].dropna()
if len(sub_fit) >= 3:
    slope, intercept, r_fit, p_fit, se = stats.linregress(sub_fit["n2"], sub_fit["dielectric_real"])
    x_range = np.linspace(sub_fit["n2"].min(), sub_fit["n2"].max(), 200)
    ax.plot(x_range, slope * x_range + intercept, "k--", lw=1.5, alpha=0.7,
            label=f"fit: ε = {slope:.2f}·n² {intercept:+.2f}\nr={r_fit:.3f}, p={p_fit:.4f}")

# Ideal Maxwell line (ε = n²)
ideal_x = np.array([max(0, sub_fit["n2"].min() * 0.8), sub_fit["n2"].max() * 1.1])
ax.plot(ideal_x, ideal_x, "g:", lw=1.5, alpha=0.6, label="ε = n² (ideal)")

ax.set_xlabel("n² at 633 nm", fontsize=11)
ax.set_ylabel("dielectric_real (static / optical)", fontsize=11)
ax.set_title("Maxwell Relation: ε vs n²\n"
             "(circles = low-freq permittivity, triangles = optical-freq)", fontsize=12)
ax.legend(fontsize=8, framealpha=0.9)
ax.grid(True, lw=0.4, alpha=0.5)
plt.tight_layout()
maxwell_path = f"{FIG_DIR}/maxwell_relation.png"
plt.savefig(maxwell_path, dpi=300, bbox_inches="tight")
plt.close()
print(f"  Saved: {maxwell_path}")
print("✓ Step 3 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — POWER ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 4 — POWER ANALYSIS (non-significant correlations)")
print("=" * 65)

# Use low-frequency flat for the power analysis
features_for_power = [c for c in available_A if c != "dielectric_real"]
power_rows = []

print(f"\n  {'Feature':<22} {'r':>8}  {'p':>8}  {'cur_n':>6}  {'n_needed':>9}  {'to_add':>8}")
print("  " + "-" * 68)

for feat in features_for_power:
    r, p, n = pearson_safe(flat_low[feat], flat_low["dielectric_real"])
    if np.isnan(r):
        continue
    n_req = n_needed_80pct(r)
    to_add = max(0, n_req - n) if not np.isinf(n_req) else ">>50"
    sig = p < 0.05
    flag = "  *** SIGNIFICANT" if sig else ""
    print(f"  {feat:<22} {r:>+8.4f}  {p:>8.4f}  {n:>6}  {n_req:>9}  {str(to_add):>8}{flag}")
    power_rows.append({
        "Feature": feat,
        "r": round(r, 4),
        "current_n": n,
        "n_needed": n_req,
        "materials_to_add": to_add,
        "p_value": round(p, 5),
        "significant": sig,
    })

power_df = pd.DataFrame(power_rows).sort_values("r", key=abs, ascending=False)
print(f"\n  Summary: {power_df['significant'].sum()} significant, "
      f"{(~power_df['significant']).sum()} need more data")
print("✓ Step 4 complete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — REGENERATE correlation_summary_dielectric.csv
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("STEP 5 — REGENERATE correlation_summary_dielectric.csv")
print("=" * 65)

# For each feature, run correlation against dielectric_real,
# labelled by regime of the subset used
summary_rows = []

# Low-freq subset
lf_features = [c for c in available_A if c != "dielectric_real"]
for feat in lf_features:
    r, p, n = pearson_safe(flat_low[feat], flat_low["dielectric_real"])
    if np.isnan(r):
        continue
    summary_rows.append({
        "Feature_A": feat,
        "Feature_B": "dielectric_real",
        "measurement_regime": "low_frequency",
        "Pearson_r": round(r, 6),
        "P_value": round(p, 6),
        "N_pairs": n,
        "Significant": "YES" if p < 0.05 else "no",
        "UNRELIABLE": n < 6,
    })

# All-materials subset (for optical-frequency correlations)
opt_flat = flat[flat["measurement_regime"] == "optical_frequency"].copy()
opt_feats = [c for c in ["n_633nm", "k_633nm", "xray_sld_real", "density_g_cm3"]
             if c in flat.columns]
for feat in opt_feats:
    r, p, n = pearson_safe(opt_flat[feat], opt_flat["dielectric_real"])
    if np.isnan(r) or n < 2:
        continue
    summary_rows.append({
        "Feature_A": feat,
        "Feature_B": "dielectric_real",
        "measurement_regime": "optical_frequency",
        "Pearson_r": round(r, 6),
        "P_value": round(p, 6),
        "N_pairs": n,
        "Significant": "YES" if p < 0.05 else "no",
        "UNRELIABLE": n < 6,
    })

# Combined (all materials, all regimes)
all_num_feats = [c for c in num_all if c != "dielectric_real"
                 and flat[c].notna().sum() >= 4]
for feat in all_num_feats:
    r, p, n = pearson_safe(flat[feat], flat["dielectric_real"])
    if np.isnan(r) or n < 2:
        continue
    summary_rows.append({
        "Feature_A": feat,
        "Feature_B": "dielectric_real",
        "measurement_regime": "all_materials",
        "Pearson_r": round(r, 6),
        "P_value": round(p, 6),
        "N_pairs": n,
        "Significant": "YES" if p < 0.05 else "no",
        "UNRELIABLE": n < 6,
    })

summary_df = pd.DataFrame(summary_rows).sort_values("Pearson_r", key=abs, ascending=False)
csv_path = "correlation_summary_dielectric.csv"
summary_df.to_csv(csv_path, index=False)
print(f"  Saved: {csv_path}  ({len(summary_df)} rows)")

# Final display table
print(f"\n  {'Feature':<22} {'r':>8}  {'p':>8}  {'N':>4}  {'Regime':<18}  Significant")
print("  " + "-" * 75)
for _, row in summary_df.drop_duplicates(["Feature_A", "measurement_regime"]).head(30).iterrows():
    unreli = "  [UNRELIABLE]" if row["UNRELIABLE"] else ""
    sig    = row["Significant"]
    regime = row["measurement_regime"]
    print(f"  {row['Feature_A']:<22} {row['Pearson_r']:>+8.4f}  {row['P_value']:>8.5f}  "
          f"{row['N_pairs']:>4}  {regime:<18}  {sig}{unreli}")

sig_count    = (summary_df["Significant"] == "YES").sum()
unreli_count = summary_df["UNRELIABLE"].sum()
print(f"\n  Total rows: {len(summary_df)}")
print(f"  Significant (p < 0.05): {sig_count}")
print(f"  UNRELIABLE (N < 6): {unreli_count}")
print("✓ Step 5 complete")

conn.close()
print("\n" + "=" * 65)
print("ALL STEPS COMPLETE")
print("=" * 65)
