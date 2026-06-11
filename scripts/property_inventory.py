"""
Property inventory and statistics layer for materials_normalized.db.

Discovers all tables/views, identifies numerical columns dynamically,
computes descriptive statistics, writes a property_statistics table,
and exports CSV + Markdown reports.
"""

import sqlite3
import os
import math
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

DB_PATH = Path(__file__).parent.parent / "data" / "materials_normalized.db"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Columns known to carry units — extended as needed.
UNITS_MAP = {
    "molecular_weight": "g/mol",
    "exact_mass": "g/mol",
    "tpsa": "Å²",
    "wavelength_nm": "nm",
    "n": "dimensionless",
    "k": "dimensionless",
    "eps_real": "dimensionless",
    "eps_imag": "dimensionless",
    "temperature_c": "°C",
    "temperature_C": "°C",
    "frequency_hz": "Hz",
    "storage_modulus": "Pa",
    "loss_modulus": "Pa",
    "storage_modulus_pa": "Pa",
    "loss_modulus_pa": "Pa",
    "viscosity_pas": "Pa·s",
    "viscosity_mpa_s": "mPa·s",
    "shear_rate_s_inv": "s⁻¹",
    "density_g_cm3": "g/cm³",
    "xray_sld": "Å⁻²",
    "neutron_sld": "Å⁻²",
    "sld_xray_real": "Å⁻²",
    "sld_xray_imag": "Å⁻²",
    "sld_neutron_real": "Å⁻²",
    "sld_neutron_imag": "Å⁻²",
    "xray_sld_real": "Å⁻²",
    "xray_sld_imag": "Å⁻²",
    "neutron_sld_real": "Å⁻²",
    "neutron_sld_imag": "Å⁻²",
    "dielectric_constant": "dimensionless",
    "dielectric_real": "dimensionless",
    "dielectric_imag": "dimensionless",
    "real_permittivity": "dimensionless",
    "imag_permittivity": "dimensionless",
    "energy_ev": "eV",
    "uncertainty": "dimensionless",
    "confidence_score": "dimensionless",
    "consensus_value": "mixed",
    "std_dev": "mixed",
    "num_sources": "count",
    "year": "year",
    "MW": "g/mol",
    "XLogP": "dimensionless",
    "HBondDonors": "count",
    "HBondAcceptors": "count",
    "RotatableBonds": "count",
    "TPSA": "Å²",
    "logP": "dimensionless",
    "h_bond_donors": "count",
    "h_bond_acceptors": "count",
    "rotatable_bonds": "count",
    "exact_mass_legacy": "g/mol",
    "MolWt": "g/mol",
    "ExactMolWt": "g/mol",
    "NumHDonors": "count",
    "NumHAcceptors": "count",
    "NumRotatableBonds": "count",
    "MolLogP": "dimensionless",
    "NumAromaticRings": "count",
    "NumRings": "count",
    "FractionCSP3": "dimensionless",
    "NumHeavyAtoms": "count",
    "BertzCT": "dimensionless",
    "heavy_atom_count": "count",
    "aromatic_rings": "count",
    "hbond_donors": "count",
    "hbond_acceptors": "count",
    "logp": "dimensionless",
    "priority": "dimensionless",
}

# Tables/views to skip for statistics (no meaningful numerical payload).
SKIP_TABLES = {
    "material_synonyms",
    "dataset_validation",
    "legacy_lab_measurements_needed",
    "legacy_references_db",
}

# Non-numerical column patterns to always exclude.
NON_NUMERIC_COLS = {
    "material_id", "record_id", "validation_id", "synonym_id", "source_id",
    "id", "reference_id", "pubchem_cid", "raw_record_id",
    "name", "formula", "smiles", "inchikey", "cas_number", "material_name",
    "doi", "title", "authors", "journal", "technique", "url", "notes",
    "descriptor_json", "morgan_fp", "dataset_label", "raw_record_table",
    "context_flag", "calculation_method", "classification",
    "measurement_regime", "material_class", "source_library",
    "descriptor_name", "source_ref", "synonym",
    "frequency_range", "wavelength_range", "reason", "protocol_notes",
    "status", "instrument", "measurement_type", "parameter",
    "citation_text", "bibtex",
}


def get_connection():
    return sqlite3.connect(DB_PATH)


def discover_tables(con):
    """Return (name, type) for every table and view."""
    cur = con.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name"
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def get_column_info(con, table_name):
    """Return list of (col_name, col_type) for a table/view."""
    try:
        cur = con.execute(f"PRAGMA table_info(\"{table_name}\")")
        return [(row[1], row[2]) for row in cur.fetchall()]
    except Exception:
        return []


def is_numeric_type(col_type: str) -> bool:
    t = col_type.upper()
    return any(kw in t for kw in ("INT", "REAL", "FLOAT", "NUMERIC", "DOUBLE", "DECIMAL", "NUMBER"))


def _mad(series: np.ndarray) -> float:
    """Median absolute deviation."""
    if len(series) == 0:
        return float("nan")
    return float(np.median(np.abs(series - np.median(series))))


def compute_stats(values: np.ndarray) -> dict:
    """Compute descriptive statistics for a 1-D array of non-null values."""
    if len(values) == 0:
        keys = ["min", "max", "mean", "median", "std", "iqr", "mad"]
        return {k: float("nan") for k in keys}
    q1, q3 = float(np.percentile(values, 25)), float(np.percentile(values, 75))
    return {
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "iqr": q3 - q1,
        "mad": _mad(values),
    }


def material_count_for_table(con, table_name) -> int:
    """Return distinct material count for tables that have material_id."""
    cols = {c for c, _ in get_column_info(con, table_name)}
    if "material_id" not in cols:
        return -1
    try:
        row = con.execute(
            f"SELECT COUNT(DISTINCT material_id) FROM \"{table_name}\""
        ).fetchone()
        return row[0] if row else -1
    except Exception:
        return -1


def build_inventory(con):
    """
    Walk every non-skipped table/view, find numerical columns,
    load data, compute stats, return list of stat dicts.
    """
    rows = []
    tables = discover_tables(con)

    for table_name, table_type in tables:
        if table_name in SKIP_TABLES:
            continue

        col_info = get_column_info(con, table_name)
        numeric_cols = [
            (col, ctype)
            for col, ctype in col_info
            if col not in NON_NUMERIC_COLS and is_numeric_type(ctype)
        ]

        if not numeric_cols:
            continue

        # For legacy_chemical_descriptors the "value" column covers many descriptors —
        # break out by descriptor_name instead of treating all values as one distribution.
        if table_name == "legacy_chemical_descriptors":
            rows.extend(_expand_legacy_descriptors(con))
            continue

        mat_count = material_count_for_table(con, table_name)

        try:
            df = pd.read_sql_query(f"SELECT * FROM \"{table_name}\"", con)
        except Exception as e:
            print(f"  [WARN] Could not read {table_name}: {e}")
            continue

        total_rows = len(df)

        for col, ctype in numeric_cols:
            if col not in df.columns:
                continue
            series = pd.to_numeric(df[col], errors="coerce")
            non_null = series.dropna().values
            count = int(series.notna().sum())
            missing = int(series.isna().sum())
            missing_pct = round(missing / total_rows * 100, 2) if total_rows > 0 else 0.0

            stats = compute_stats(non_null)
            rows.append({
                "table_name": table_name,
                "table_type": table_type,
                "column_name": col,
                "units": UNITS_MAP.get(col, "unknown"),
                "total_rows": total_rows,
                "count": count,
                "missing_count": missing,
                "missing_pct": missing_pct,
                "material_count": mat_count if mat_count >= 0 else None,
                **stats,
            })

    return rows


def _expand_legacy_descriptors(con):
    """Unpack legacy_chemical_descriptors by descriptor_name."""
    try:
        df = pd.read_sql_query(
            "SELECT material_id, descriptor_name, value FROM legacy_chemical_descriptors", con
        )
    except Exception:
        return []

    rows = []
    mat_total = df["material_id"].nunique()
    for desc_name, grp in df.groupby("descriptor_name"):
        series = pd.to_numeric(grp["value"], errors="coerce")
        non_null = series.dropna().values
        count = int(series.notna().sum())
        missing = int(series.isna().sum())
        total = len(series)
        missing_pct = round(missing / total * 100, 2) if total > 0 else 0.0
        stats = compute_stats(non_null)
        rows.append({
            "table_name": "legacy_chemical_descriptors",
            "table_type": "table",
            "column_name": f"value[{desc_name}]",
            "units": UNITS_MAP.get(desc_name, "unknown"),
            "total_rows": total,
            "count": count,
            "missing_count": missing,
            "missing_pct": missing_pct,
            "material_count": mat_total,
            **stats,
        })
    return rows


def write_property_statistics_table(con, stats_rows):
    """Create/replace property_statistics in the DB."""
    con.execute("DROP TABLE IF EXISTS property_statistics")
    con.execute("""
        CREATE TABLE property_statistics (
            stat_id        INTEGER PRIMARY KEY,
            table_name     TEXT    NOT NULL,
            table_type     TEXT    NOT NULL,
            column_name    TEXT    NOT NULL,
            units          TEXT,
            total_rows     INTEGER,
            count          INTEGER,
            missing_count  INTEGER,
            missing_pct    REAL,
            material_count INTEGER,
            min_val        REAL,
            max_val        REAL,
            mean_val       REAL,
            median_val     REAL,
            std_val        REAL,
            iqr_val        REAL,
            mad_val        REAL,
            UNIQUE(table_name, column_name)
        )
    """)
    for r in stats_rows:
        con.execute("""
            INSERT OR REPLACE INTO property_statistics
              (table_name, table_type, column_name, units, total_rows,
               count, missing_count, missing_pct, material_count,
               min_val, max_val, mean_val, median_val, std_val, iqr_val, mad_val)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            r["table_name"], r["table_type"], r["column_name"], r["units"],
            r["total_rows"], r["count"], r["missing_count"], r["missing_pct"],
            r["material_count"],
            r["min"], r["max"], r["mean"], r["median"], r["std"],
            r["iqr"], r["mad"],
        ))
    con.commit()
    print(f"  Wrote {len(stats_rows)} rows to property_statistics table.")


def _fmt(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def write_property_inventory_md(stats_rows):
    path = REPORTS_DIR / "property_inventory.md"
    lines = [
        "# Property Inventory",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "All numerical properties discovered in `materials_normalized.db`.",
        "",
        "| Table | Type | Property (Column) | Units | Total Rows | Non-null | Missing % | Material Count |",
        "|-------|------|-------------------|-------|------------|----------|-----------|----------------|",
    ]
    for r in stats_rows:
        mat = r["material_count"] if r["material_count"] is not None else "—"
        lines.append(
            f"| {r['table_name']} | {r['table_type']} | {r['column_name']} "
            f"| {r['units']} | {r['total_rows']} | {r['count']} "
            f"| {r['missing_pct']}% | {mat} |"
        )
    path.write_text("\n".join(lines) + "\n")
    print(f"  Wrote {path}")


def write_property_statistics_report_md(stats_rows):
    path = REPORTS_DIR / "property_statistics_report.md"
    lines = [
        "# Property Statistics Report",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "Descriptive statistics for all numerical properties in `materials_normalized.db`.",
        "IQR = inter-quartile range (Q3−Q1). MAD = median absolute deviation.",
        "",
    ]

    # Group by table.
    from itertools import groupby
    rows_sorted = sorted(stats_rows, key=lambda r: (r["table_name"], r["column_name"]))
    for table_name, group in groupby(rows_sorted, key=lambda r: r["table_name"]):
        group = list(group)
        table_type = group[0]["table_type"]
        lines.append(f"## `{table_name}` ({table_type})")
        lines.append("")
        lines.append(
            "| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |"
        )
        lines.append(
            "|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|"
        )
        for r in group:
            lines.append(
                f"| {r['column_name']} | {r['units']} "
                f"| {r['count']} | {r['missing_pct']}% "
                f"| {_fmt(r['min'])} | {_fmt(r['max'])} "
                f"| {_fmt(r['mean'])} | {_fmt(r['median'])} "
                f"| {_fmt(r['std'])} | {_fmt(r['iqr'])} "
                f"| {_fmt(r['mad'])} |"
            )
        lines.append("")

    path.write_text("\n".join(lines) + "\n")
    print(f"  Wrote {path}")


def export_csvs(stats_rows):
    df = pd.DataFrame(stats_rows).rename(columns={
        "min": "min_val", "max": "max_val", "mean": "mean_val",
        "median": "median_val", "std": "std_val", "iqr": "iqr_val", "mad": "mad_val",
    })

    inv_path = REPORTS_DIR / "property_inventory.csv"
    stat_path = REPORTS_DIR / "property_statistics.csv"

    inv_cols = [
        "table_name", "table_type", "column_name", "units",
        "total_rows", "count", "missing_count", "missing_pct", "material_count",
    ]
    df[inv_cols].to_csv(inv_path, index=False)
    print(f"  Wrote {inv_path}")

    df.to_csv(stat_path, index=False)
    print(f"  Wrote {stat_path}")


def print_summary(stats_rows):
    df = pd.DataFrame(stats_rows)
    total_props = len(df)
    tables = df["table_name"].nunique()
    fully_populated = (df["missing_pct"] == 0).sum()
    high_missing = (df["missing_pct"] > 50).sum()
    print("\n=== Summary ===")
    print(f"  Tables/views surveyed : {tables}")
    print(f"  Numerical properties  : {total_props}")
    print(f"  Fully populated (0%)  : {fully_populated}")
    print(f"  >50% missing          : {high_missing}")
    print("\n  Top properties by row count:")
    top = df.nlargest(10, "count")[["table_name", "column_name", "count", "missing_pct"]]
    print(top.to_string(index=False))
    print("\n  Properties with data (count > 0):")
    has_data = df[df["count"] > 0][["table_name", "column_name", "count",
                                     "mean_val" if "mean_val" in df.columns else "mean"]].head(20)
    # Handle both naming conventions
    if "mean" in df.columns:
        has_data = df[df["count"] > 0][["table_name", "column_name", "count", "mean"]].head(20)
    print(has_data.to_string(index=False))


def main():
    print(f"Connecting to {DB_PATH}")
    con = get_connection()
    print("Discovering tables and numerical columns...")
    stats_rows = build_inventory(con)
    print(f"  Found {len(stats_rows)} numerical property × table combinations.")

    print("Writing property_statistics table...")
    write_property_statistics_table(con, stats_rows)

    print("Writing Markdown reports...")
    write_property_inventory_md(stats_rows)
    write_property_statistics_report_md(stats_rows)

    print("Exporting CSVs...")
    export_csvs(stats_rows)

    print_summary(stats_rows)
    con.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
