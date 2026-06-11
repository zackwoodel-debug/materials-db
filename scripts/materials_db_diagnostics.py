#!/usr/bin/env python3
"""
Production-grade diagnostics for the materials-db SQLite database.

Features:
- Dynamic schema inspection and safe ingestion
- Pearson correlation heatmap (lower triangle only)
- Missingness visualization using missingno
- Pairplot with KDE distributions
- Variance Inflation Factor (VIF) analysis
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import warnings

BASE_DIR = Path(__file__).resolve().parent.parent
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import missingno as msno
import numpy as np
import pandas as pd
import seaborn as sns
from statsmodels.stats.outliers_influence import variance_inflation_factor

warnings.filterwarnings("ignore")

sns.set_theme(style="whitegrid", palette="muted", context="talk")
plt.style.use("seaborn-v0_8-whitegrid")

DATABASE_PATH = BASE_DIR / "data" / "materials.db"
DEFAULT_TABLE = "spr_data"
FIGURE_DIR = BASE_DIR / "figures" / "diagnostics"

PAIRPLOT_MAX_FEATURES = 8
PAIRPLOT_SAMPLE_SIZE = 2000


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def connect_database(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found:\n{db_path}")

    return sqlite3.connect(db_path)


def list_tables(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
    SELECT name, type
    FROM sqlite_master
    WHERE type IN ('table', 'view')
    ORDER BY type, name;
    """
    return pd.read_sql_query(query, conn)


def choose_table(conn: sqlite3.Connection, preferred_table: str = DEFAULT_TABLE) -> str:
    tables = list_tables(conn)
    available = tables["name"].tolist()

    if preferred_table in available:
        return preferred_table

    if not available:
        raise RuntimeError("No tables or views found.")

    print(
        f"[INFO] Preferred table '{preferred_table}' not found.\n"
        f"Using '{available[0]}' instead."
    )
    return available[0]


def load_table(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    query = f"SELECT * FROM {quote_identifier(table_name)}"
    df = pd.read_sql_query(query, conn)

    print(f"\nLoaded '{table_name}'")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")
    return df


def split_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    numeric_df = df.select_dtypes(include=np.number)
    categorical_cols = [column for column in df.columns if column not in numeric_df.columns]
    return numeric_df, categorical_cols


def figure_path(output_dir: Path, table_name: str, stem: str) -> Path:
    safe_table_name = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in table_name
    )
    return output_dir / f"{safe_table_name}_{stem}.png"


def plot_correlation_heatmap(
    numeric_df: pd.DataFrame, table_name: str, output_dir: Path
) -> Path | None:
    if numeric_df.shape[1] < 2:
        print("[WARNING] Not enough numeric columns for correlations.")
        return None

    corr = numeric_df.corr(method="pearson")
    mask = np.triu(np.ones_like(corr, dtype=bool))

    plt.figure(figsize=(12, 10))
    sns.heatmap(
        corr,
        mask=mask,
        cmap="vlag",
        center=0,
        annot=True,
        fmt=".2f",
        linewidths=0.5,
        square=True,
        cbar_kws={"shrink": 0.8},
        annot_kws={"fontsize": 8},
    )
    plt.title("Pearson Correlation Matrix", fontsize=16)
    plt.tight_layout()

    path = figure_path(output_dir, table_name, "pearson_correlation")
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    return path


def plot_missingness(
    df: pd.DataFrame, table_name: str, output_dir: Path
) -> list[Path]:
    if df.empty:
        return []

    paths = []

    plt.figure(figsize=(14, 7))
    msno.matrix(df, sparkline=False)
    plt.title("Missingness Matrix")
    plt.tight_layout()
    path = figure_path(output_dir, table_name, "missingness_matrix")
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    paths.append(path)

    if df.isna().any().sum() >= 2:
        plt.figure(figsize=(10, 7))
        msno.heatmap(df)
        plt.title("Missingness Correlation Heatmap")
        plt.tight_layout()
        path = figure_path(output_dir, table_name, "missingness_heatmap")
        plt.savefig(path, dpi=300, bbox_inches="tight")
        plt.close()
        paths.append(path)
    else:
        print("[WARNING] Not enough columns with missing values for missingness heatmap.")

    return paths


def select_pairplot_features(numeric_df: pd.DataFrame) -> list[str]:
    variances = numeric_df.var()
    usable = variances[variances > 0].index
    subset = numeric_df[usable]
    missing_fraction = subset.isna().mean()
    return missing_fraction.sort_values().index.tolist()[:PAIRPLOT_MAX_FEATURES]


def plot_pairplot(
    numeric_df: pd.DataFrame, table_name: str, output_dir: Path
) -> Path | None:
    features = select_pairplot_features(numeric_df)

    if len(features) < 2:
        print("[WARNING] Not enough numeric features for pairplot.")
        return None

    pair_df = numeric_df[features].dropna()
    if pair_df.empty:
        print("[WARNING] No complete rows available for pairplot.")
        return None

    if len(pair_df) > PAIRPLOT_SAMPLE_SIZE:
        pair_df = pair_df.sample(PAIRPLOT_SAMPLE_SIZE, random_state=42)

    grid = sns.pairplot(
        pair_df,
        diag_kind="kde",
        corner=True,
        plot_kws={"alpha": 0.5, "s": 20},
    )
    grid.fig.suptitle("Feature Distribution Pairplot", y=1.02)
    grid.fig.tight_layout()

    path = figure_path(output_dir, table_name, "pairplot")
    grid.fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(grid.fig)
    return path


def compute_vif(numeric_df: pd.DataFrame) -> pd.DataFrame:
    x = numeric_df.copy()
    x = x.dropna(axis=1, how="all")
    x = x.fillna(x.median())
    variances = x.var()
    x = x.loc[:, variances > 0]

    if x.shape[1] < 2:
        print("[WARNING] Not enough predictors for VIF.")
        return pd.DataFrame()

    vif_df = pd.DataFrame(
        {
            "feature": x.columns,
            "VIF": [
                variance_inflation_factor(x.values, index)
                for index in range(x.shape[1])
            ],
        }
    )
    return vif_df.sort_values("VIF", ascending=False).reset_index(drop=True)


def print_summary(
    df: pd.DataFrame, numeric_df: pd.DataFrame, categorical_cols: list[str]
) -> None:
    print("\n==========================")
    print("DATABASE SUMMARY")
    print("==========================")
    print(f"Rows               : {len(df):,}")
    print(f"Columns            : {len(df.columns)}")
    print(f"Numeric columns    : {numeric_df.shape[1]}")
    print(f"Non-numeric columns: {len(categorical_cols)}")
    print("\nNumeric columns:")
    print(numeric_df.columns.tolist())

    if categorical_cols:
        print("\nCategorical columns:")
        print(categorical_cols)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run diagnostics on a materials-db SQLite table."
    )
    parser.add_argument("--db", type=Path, default=DATABASE_PATH, help="SQLite database path.")
    parser.add_argument(
        "--table",
        default=DEFAULT_TABLE,
        help=f"Table or view to inspect. Defaults to '{DEFAULT_TABLE}'.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=FIGURE_DIR,
        help="Directory for generated figures and CSV outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with connect_database(args.db) as conn:
        print("\nAvailable tables/views:")
        tables = list_tables(conn)
        print(tables)

        target_table = choose_table(conn, preferred_table=args.table)
        df = load_table(conn, target_table)

    numeric_df, categorical_cols = split_columns(df)
    print_summary(df, numeric_df, categorical_cols)

    generated_paths = []
    generated_paths.append(plot_correlation_heatmap(numeric_df, target_table, args.output_dir))
    generated_paths.extend(plot_missingness(df, target_table, args.output_dir))
    generated_paths.append(plot_pairplot(numeric_df, target_table, args.output_dir))

    vif_df = compute_vif(numeric_df)
    if not vif_df.empty:
        vif_path = args.output_dir / f"{target_table}_vif.csv"
        vif_df.to_csv(vif_path, index=False)
        generated_paths.append(vif_path)

        print("\n==========================")
        print("VIF RESULTS")
        print("==========================")
        print(vif_df.to_string(index=False))

    print("\nGenerated outputs:")
    for path in filter(None, generated_paths):
        print(path)


if __name__ == "__main__":
    main()
