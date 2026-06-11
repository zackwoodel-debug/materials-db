"""
Materials Science Correlation Analysis
Parts 1-5: Schema exploration, PubChem enrichment, flat DataFrame, correlation matrices, summary
"""

import sqlite3
import json
import time
import os
import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────
BASE      = Path(__file__).resolve().parent.parent
DB_PATH   = BASE / "data" / "materials.db"
CACHE     = BASE / "data" / "pubchem_cache.json"
OUT_CSV   = BASE / "analysis_dataset.csv"
SUMM_CSV  = BASE / "correlation_summary.csv"
FIG_DIR   = BASE / "figures"
FIG_DIR.mkdir(exist_ok=True)

PUBCHEM_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
    "{name}/property/"
    "MolecularFormula,IsomericSMILES,MolecularWeight,"
    "XLogP,HBondDonorCount,HBondAcceptorCount,"
    "RotatableBondCount,TPSA/JSON"
)

TARGETS = ["n", "k", "xray_sld_real", "neutron_sld_real", "density_g_cm3"]

sns.set_theme(style="whitegrid", font_scale=0.9)

# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — EXPLORE SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 1 — DATABASE SCHEMA EXPLORATION")
print("="*70)

conn = sqlite3.connect(DB_PATH)

cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nTables found: {tables}\n")

table_dfs = {}
numeric_cols_by_table = {}

for tbl in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
    n_rows = cur.fetchone()[0]

    cur.execute(f"PRAGMA table_info([{tbl}])")
    schema = cur.fetchall()
    col_names = [c[1] for c in schema]
    col_types = [c[2] for c in schema]

    print(f"{'─'*60}")
    print(f"  Table: {tbl}  ({n_rows} rows)")
    for name, typ in zip(col_names, col_types):
        print(f"    {name:<30} {typ}")

    df = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)
    table_dfs[tbl] = df
    print(f"\n  First 5 rows:")
    print(df.head(5).to_string())
    print()

    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols_by_table[tbl] = num_cols
    if num_cols:
        print(f"  Numeric columns: {num_cols}")
    print()

print("\n[PART 1 COMPLETE]")

# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — PUBCHEM ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 2 — PUBCHEM ENRICHMENT")
print("="*70)

# get unique material names from materials table
mat_df = table_dfs.get("materials", pd.DataFrame())
name_col = None
for candidate in ["name", "material_name", "Name", "Material"]:
    if candidate in mat_df.columns:
        name_col = candidate
        break

if name_col is None and not mat_df.empty:
    # guess first text column
    name_col = mat_df.select_dtypes(include="object").columns[0]

if name_col:
    material_names = mat_df[name_col].dropna().unique().tolist()
else:
    material_names = []

print(f"\nMaterials to query: {material_names}")

# load cache
if CACHE.exists():
    with open(CACHE) as f:
        cache = json.load(f)
    print(f"Loaded existing cache with {len(cache)} entries")
else:
    cache = {}

resolved = 0
failed   = []

for mat in material_names:
    if mat in cache:
        print(f"  [CACHE] {mat}")
        resolved += 1
        continue

    url = PUBCHEM_URL.format(name=requests.utils.quote(str(mat)))
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            props = data["PropertyTable"]["Properties"][0]
            cache[mat] = props
            resolved += 1
            print(f"  [OK]    {mat}  MW={props.get('MolecularWeight','?')}")
        else:
            cache[mat] = None
            failed.append(mat)
            print(f"  [FAIL]  {mat}  (HTTP {resp.status_code})")
    except Exception as e:
        cache[mat] = None
        failed.append(mat)
        print(f"  [ERROR] {mat}  ({e})")

    # save cache after each fetch to never lose progress
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=2)
    time.sleep(0.3)   # PubChem rate limit

print(f"\nResolved: {resolved}/{len(material_names)}   Failed: {len(failed)}")
if failed:
    print(f"Failed names: {failed}")

# write pubchem_data table
rows = []
for mat, props in cache.items():
    if props is None:
        rows.append({"material_name": mat})
    else:
        rows.append({
            "material_name":   mat,
            "SMILES":          props.get("IsomericSMILES"),
            "molecular_formula": props.get("MolecularFormula"),
            "MW":              props.get("MolecularWeight"),
            "XLogP":           props.get("XLogP"),
            "HBondDonors":     props.get("HBondDonorCount"),
            "HBondAcceptors":  props.get("HBondAcceptorCount"),
            "RotatableBonds":  props.get("RotatableBondCount"),
            "TPSA":            props.get("TPSA"),
        })

pubchem_df = pd.DataFrame(rows)
pubchem_df.to_sql("pubchem_data", conn, if_exists="replace", index=False)
table_dfs["pubchem_data"] = pubchem_df
conn.commit()
print(f"\npubchem_data table written to DB  ({len(pubchem_df)} rows)")
print(pubchem_df.to_string())

print("\n[PART 2 COMPLETE]")

# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 — BUILD FLAT ANALYSIS DATAFRAME
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 3 — FLAT ANALYSIS DATAFRAME")
print("="*70)

# reload all tables fresh after pubchem write
all_tables = {}
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for (tbl,) in cur.fetchall():
    all_tables[tbl] = pd.read_sql(f"SELECT * FROM [{tbl}]", conn)

# ── base: materials table, normalise id → material_id ───────────────────────
base = all_tables.get("materials", pd.DataFrame()).copy()
if "id" in base.columns and "material_id" not in base.columns:
    base = base.rename(columns={"id": "material_id"})

# ── pivot chemical_descriptors: long → wide (one row per material) ──────────
if "chemical_descriptors" in all_tables:
    cd = all_tables["chemical_descriptors"].copy()
    if {"material_id", "descriptor_name", "value"}.issubset(cd.columns):
        cd_wide = cd.pivot_table(
            index="material_id", columns="descriptor_name", values="value", aggfunc="first"
        ).reset_index()
        cd_wide.columns.name = None
        all_tables["chemical_descriptors_wide"] = cd_wide

# tables that join on material_id (integer FK)
# for tables with repeated rows per material (optical_nk, sld, etc.) aggregate
def agg_numeric(df, key="material_id"):
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    agg_cols = [c for c in num_cols if c != key]
    if not agg_cols:
        return df[[key]].drop_duplicates()
    return df.groupby(key)[agg_cols].mean().reset_index()

merge_order = [
    ("optical_nk",               True),
    ("viscoelasticity",          True),
    ("dielectrics",              True),
    ("dielectric",               True),
    ("calculated_slds",          True),
    ("calculated_sld",           True),
    ("chemical_descriptors_wide",False),
    ("lab_measurements_needed",  True),
]

flat = base.copy()
for tbl, do_agg in merge_order:
    if tbl not in all_tables:
        continue
    right = all_tables[tbl].copy()
    if "material_id" not in right.columns:
        print(f"  Skipping {tbl} — no material_id column")
        continue
    if do_agg:
        right = agg_numeric(right, key="material_id")
    # drop cols already in flat (except join key)
    dup_cols = [c for c in right.columns if c != "material_id" and c in flat.columns]
    if dup_cols:
        right = right.drop(columns=dup_cols)
    flat = flat.merge(right, on="material_id", how="left")
    print(f"  Merged {tbl:<36}  shape now: {flat.shape}")

# ── attach pubchem by name ───────────────────────────────────────────────────
if "pubchem_data" in all_tables:
    pc = all_tables["pubchem_data"].copy()
    # normalise join key: materials.name → material_name
    name_col_base = None
    for c in ["name", "Name"]:
        if c in flat.columns:
            name_col_base = c
            break
    if name_col_base and "material_name" in pc.columns:
        flat = flat.merge(
            pc.rename(columns={"material_name": name_col_base}),
            on=name_col_base, how="left"
        )
        print(f"  Merged pubchem_data (by name)            shape now: {flat.shape}")

# de-duplicate columns
flat = flat.loc[:, ~flat.columns.duplicated()]

flat.to_csv(OUT_CSV, index=False)
print(f"\nSaved: {OUT_CSV}")
print(f"Shape: {flat.shape}")
print("\nColumn null counts:")
null_counts = flat.isnull().sum()
for col, cnt in null_counts.items():
    pct = 100 * cnt / max(len(flat), 1)
    print(f"  {col:<40} {cnt:>4} nulls  ({pct:.0f}%)")

print("\n[PART 3 COMPLETE]")

# ═══════════════════════════════════════════════════════════════════════════════
# PART 4 — CORRELATION MATRICES
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 4 — CORRELATION MATRICES")
print("="*70)

# identifier columns to always drop
ID_COLS = {
    "material_name", "name", "Name", "SMILES", "smiles",
    "molecular_formula", "MolecularFormula", "formula",
    "id", "material_id", "CID", "IUPACName",
    "pubchem_cid", "material_class", "notes", "reference_id",
}

# column rename map: prefer the cleaner/more populated duplicate
COL_PREFER = {
    "sld_xray_real":    "xray_sld_real",   # keep xray_sld_real, drop sld_xray_real
    "sld_xray_imag":    None,               # drop — nearly all zero
    "sld_neutron_real": "neutron_sld_real", # keep neutron_sld_real
}

summary_rows = []

def style_heatmap(ax, title):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.tick_params(axis="y", rotation=0,  labelsize=8)

# ── clean up the flat df before correlations ─────────────────────────────────
# drop exact duplicates of SLD columns (two tables had overlapping data)
flat_corr = flat.copy()
for dup_col, keep_col in COL_PREFER.items():
    if dup_col in flat_corr.columns:
        flat_corr.drop(columns=[dup_col], inplace=True)

# also drop columns that are completely zero-variance (would give NaN correlations)
for col in flat_corr.select_dtypes(include=[np.number]).columns:
    if flat_corr[col].dropna().nunique() <= 1:
        flat_corr.drop(columns=[col], inplace=True)

print(f"Working columns after cleanup: {flat_corr.shape[1]}")

for target in TARGETS:
    print(f"\n{'─'*60}")
    print(f"  TARGET: {target}")

    if target not in flat_corr.columns:
        print(f"  *** Column '{target}' not found — skipping")
        continue

    # numeric-only, drop identifiers
    num_df = flat_corr.select_dtypes(include=[np.number]).copy()
    drop_ids = [c for c in num_df.columns if c.lower() in {i.lower() for i in ID_COLS}]
    num_df.drop(columns=drop_ids, inplace=True, errors="ignore")

    if target not in num_df.columns:
        print(f"  *** Target '{target}' not numeric — skipping")
        continue

    # drop columns with <3 non-null values (can't compute correlation)
    num_df = num_df.dropna(axis=1, thresh=3)

    feature_cols = [c for c in num_df.columns if c != target]
    if not feature_cols:
        print("  No features found — skipping")
        continue

    analysis_df = num_df[[target] + feature_cols].dropna(subset=[target])

    # ── Figure A: Full correlation heatmap ───────────────────────────────────
    corr_full = analysis_df.corr(method="pearson")

    fig, ax = plt.subplots(figsize=(14, 12))
    mask = np.zeros_like(corr_full, dtype=bool)   # show full matrix
    sns.heatmap(
        corr_full,
        ax=ax,
        cmap="RdBu_r",
        vmin=-1, vmax=1,
        annot=True,
        fmt=".1f",
        linewidths=0.4,
        linecolor="#e0e0e0",
        cbar_kws={"shrink": 0.8, "label": "Pearson r"},
        annot_kws={"size": 7},
    )
    style_heatmap(ax, f"Full Correlation Matrix — {target}")
    fig.tight_layout()
    path_a = FIG_DIR / f"corr_full_{target}.png"
    fig.savefig(path_a, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path_a.name}")

    # ── Identify high-correlation pairs & drop weaker feature ────────────────
    target_corr = analysis_df.corr(method="pearson")[target].drop(target)
    target_corr_abs = target_corr.abs()

    high_pairs = []
    feat_list  = list(feature_cols)
    # build upper-triangle pairs
    for i in range(len(feat_list)):
        for j in range(i + 1, len(feat_list)):
            fi, fj = feat_list[i], feat_list[j]
            if fi not in analysis_df.columns or fj not in analysis_df.columns:
                continue
            valid = analysis_df[[fi, fj]].dropna()
            if len(valid) < 3:
                continue
            r = valid[fi].corr(valid[fj])
            if abs(r) > 0.85:
                high_pairs.append((fi, fj, r))

    to_drop = set()
    for fi, fj, r in high_pairs:
        ri = target_corr_abs.get(fi, 0)
        rj = target_corr_abs.get(fj, 0)
        loser = fj if ri >= rj else fi
        to_drop.add(loser)
        print(f"    High pair: {fi} ↔ {fj}  r={r:.3f}  → drop '{loser}'")

    kept_features = [c for c in feature_cols if c not in to_drop]
    print(f"  Kept  ({len(kept_features)}): {kept_features}")
    print(f"  Dropped ({len(to_drop)}): {list(to_drop)}")

    # ── Figure B: Cleaned heatmap ─────────────────────────────────────────────
    kept_cols = kept_features + [target]
    clean_df  = analysis_df[kept_cols]
    corr_clean = clean_df.corr(method="pearson")

    fig, ax = plt.subplots(figsize=(max(8, len(kept_cols)), max(7, len(kept_cols) - 1)))
    sns.heatmap(
        corr_clean,
        ax=ax,
        cmap="RdBu_r",
        vmin=-1, vmax=1,
        annot=True,
        fmt=".1f",
        linewidths=0.4,
        linecolor="#e0e0e0",
        cbar_kws={"shrink": 0.8, "label": "Pearson r"},
        annot_kws={"size": 8},
    )
    style_heatmap(ax, f"Cleaned Correlation Matrix — {target}")
    fig.tight_layout()
    path_b = FIG_DIR / f"corr_cleaned_{target}.png"
    fig.savefig(path_b, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path_b.name}")

    # ── p-values & Figure C: ranked bar chart ────────────────────────────────
    bar_data = []
    for feat in kept_features:
        pair = analysis_df[[feat, target]].dropna()
        if len(pair) < 3:
            r_val, p_val = np.nan, np.nan
        else:
            r_val, p_val = stats.pearsonr(pair[feat], pair[target])
        bar_data.append({
            "feature": feat,
            "r":       r_val,
            "abs_r":   abs(r_val) if not np.isnan(r_val) else 0,
            "p":       p_val,
            "sig":     (p_val < 0.05) if not np.isnan(p_val) else False,
        })
        summary_rows.append({
            "Feature":    feat,
            "Target":     target,
            "Pearson_r":  round(r_val, 4) if not np.isnan(r_val) else np.nan,
            "P_value":    round(p_val, 4) if not np.isnan(p_val) else np.nan,
            "Significant": "yes" if (not np.isnan(p_val) and p_val < 0.05) else "no",
            "Decision":   "dropped" if feat in to_drop else "kept",
            "Abs_r":      round(abs(r_val), 4) if not np.isnan(r_val) else np.nan,
        })

    bar_df = pd.DataFrame(bar_data).sort_values("abs_r", ascending=True)

    fig, ax = plt.subplots(figsize=(10, max(5, len(bar_df) * 0.45 + 1.5)))
    colors = ["#2ca02c" if s else "#d62728" for s in bar_df["sig"]]
    bars   = ax.barh(bar_df["feature"], bar_df["abs_r"], color=colors, edgecolor="white", height=0.65)

    ax.axvline(0.3, color="#888888", linestyle="--", linewidth=1,   label="|r|=0.3 (weak)")
    ax.axvline(0.7, color="#444444", linestyle="--", linewidth=1.5, label="|r|=0.7 (strong)")

    for bar, row in zip(bars, bar_df.itertuples()):
        r_str = f"{row.r:+.3f}" if not np.isnan(row.r) else "NaN"
        p_str = f"p={row.p:.3f}" if not np.isnan(row.p) else "p=NaN"
        ax.text(
            bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
            f"{r_str}  {p_str}",
            va="center", ha="left", fontsize=7.5,
        )

    green_patch = mpatches.Patch(color="#2ca02c", label="p < 0.05 (significant)")
    red_patch   = mpatches.Patch(color="#d62728", label="p ≥ 0.05 (not significant)")
    ax.legend(handles=[green_patch, red_patch, *ax.get_lines()[:2]],
              loc="lower right", fontsize=8)

    ax.set_xlim(0, 1.25)
    ax.set_xlabel("|Pearson r|", fontsize=10)
    ax.set_title(f"Feature Importance — {target}", fontsize=13, fontweight="bold", pad=12)
    sns.despine(left=True, bottom=False)
    fig.tight_layout()
    path_c = FIG_DIR / f"corr_ranked_{target}.png"
    fig.savefig(path_c, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path_c.name}")

    # also add dropped features to summary
    for feat in to_drop:
        pair = analysis_df[[feat, target]].dropna() if feat in analysis_df.columns else pd.DataFrame()
        if len(pair) >= 3:
            r_val, p_val = stats.pearsonr(pair[feat], pair[target])
        else:
            r_val, p_val = np.nan, np.nan
        summary_rows.append({
            "Feature":    feat,
            "Target":     target,
            "Pearson_r":  round(r_val, 4) if not np.isnan(r_val) else np.nan,
            "P_value":    round(p_val, 4) if not np.isnan(p_val) else np.nan,
            "Significant": "yes" if (not np.isnan(p_val) and p_val < 0.05) else "no",
            "Decision":   "dropped",
            "Abs_r":      round(abs(r_val), 4) if not np.isnan(r_val) else np.nan,
        })

print("\n[PART 4 COMPLETE]")

# ═══════════════════════════════════════════════════════════════════════════════
# PART 5 — SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PART 5 — SUMMARY")
print("="*70)

summ_df = pd.DataFrame(summary_rows)
summ_df.sort_values(["Target", "Abs_r"], ascending=[True, False], inplace=True)
summ_df.to_csv(SUMM_CSV, index=False)
print(f"\nSaved: {SUMM_CSV}")

print("\n── Top 5 features per target ──────────────────────────────────────────")
for target in TARGETS:
    sub = summ_df[(summ_df["Target"] == target) & (summ_df["Decision"] == "kept")]
    sub = sub.sort_values("Abs_r", ascending=False).head(5)
    if sub.empty:
        continue
    print(f"\n  {target}:")
    for _, row in sub.iterrows():
        sig_tag = "✓" if row["Significant"] == "yes" else "✗"
        print(f"    {sig_tag}  {row['Feature']:<30}  r={row['Pearson_r']:+.4f}  p={row['P_value']:.4f}")

print("\n── Universal predictors (p<0.05 across ALL targets) ──────────────────")
found_targets = summ_df["Target"].unique()
sig_all = (
    summ_df[summ_df["Significant"] == "yes"]
    .groupby("Feature")["Target"]
    .nunique()
)
universal = sig_all[sig_all == len(found_targets)].index.tolist()
if universal:
    for f in sorted(universal):
        print(f"  {f}")
else:
    print("  None found (may need more data / overlapping samples)")

conn.close()
print("\n" + "="*70)
print("ALL PARTS COMPLETE")
print(f"  analysis_dataset.csv  → {OUT_CSV}")
print(f"  correlation_summary.csv → {SUMM_CSV}")
print(f"  figures/              → {FIG_DIR}")
print("="*70)
