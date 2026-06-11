"""Tests for property inventory and statistics layer."""

import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "materials_normalized.db"

# Import functions from the script under test.
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from property_inventory import (
    compute_stats,
    _mad,
    is_numeric_type,
    get_column_info,
    discover_tables,
    build_inventory,
    material_count_for_table,
    NON_NUMERIC_COLS,
    SKIP_TABLES,
)


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------

class TestComputeStats:
    def test_basic(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        s = compute_stats(arr)
        assert s["min"] == 1.0
        assert s["max"] == 5.0
        assert s["mean"] == pytest.approx(3.0)
        assert s["median"] == 3.0
        assert s["std"] == pytest.approx(math.sqrt(2.5))

    def test_iqr(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        s = compute_stats(arr)
        # numpy linear interpolation: Q1=2.0, Q3=4.0 → IQR=2.0
        assert s["iqr"] == pytest.approx(2.0, abs=1e-9)

    def test_mad_constant(self):
        arr = np.array([5.0, 5.0, 5.0])
        assert _mad(arr) == 0.0

    def test_empty_array(self):
        s = compute_stats(np.array([]))
        for v in s.values():
            assert math.isnan(v)

    def test_single_element(self):
        s = compute_stats(np.array([42.0]))
        assert s["min"] == 42.0
        assert s["max"] == 42.0
        assert s["std"] == 0.0

    def test_mad_nonzero(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert _mad(arr) == pytest.approx(1.0)


class TestIsNumericType:
    @pytest.mark.parametrize("t", ["REAL", "INTEGER", "INT", "FLOAT", "NUMERIC", "DOUBLE"])
    def test_numeric(self, t):
        assert is_numeric_type(t)

    @pytest.mark.parametrize("t", ["TEXT", "BLOB", "", "VARCHAR(255)"])
    def test_non_numeric(self, t):
        assert not is_numeric_type(t)


# ---------------------------------------------------------------------------
# Integration tests — require the live DB
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def con():
    if not DB_PATH.exists():
        pytest.skip(f"DB not found: {DB_PATH}")
    c = sqlite3.connect(DB_PATH)
    yield c
    c.close()


class TestDiscovery:
    def test_tables_found(self, con):
        tables = discover_tables(con)
        names = {t for t, _ in tables}
        assert "materials" in names
        assert "optical_dispersion" in names
        assert "physical_properties" in names

    def test_views_found(self, con):
        tables = discover_tables(con)
        views = {t for t, typ in tables if typ == "view"}
        assert "spr_data" in views
        assert "xrr_data" in views

    def test_column_info_materials(self, con):
        cols = {c: t for c, t in get_column_info(con, "materials")}
        assert "molecular_weight" in cols
        assert is_numeric_type(cols["molecular_weight"])
        # name is TEXT, not numeric
        assert not is_numeric_type(cols["name"])


class TestMaterialCount:
    def test_optical_dispersion(self, con):
        n = material_count_for_table(con, "optical_dispersion")
        assert n > 0

    def test_sources_no_material_id(self, con):
        # sources table has no material_id column
        n = material_count_for_table(con, "sources")
        assert n == -1


class TestBuildInventory:
    @pytest.fixture(scope="class")
    def stats(self, con):
        return build_inventory(con)

    def test_returns_list(self, stats):
        assert isinstance(stats, list)
        assert len(stats) > 0

    def test_required_keys(self, stats):
        required = {
            "table_name", "table_type", "column_name", "units",
            "total_rows", "count", "missing_count", "missing_pct",
            "material_count", "min", "max", "mean", "median", "std", "iqr", "mad",
        }
        for row in stats:
            assert required.issubset(row.keys()), f"Missing keys in {row}"

    def test_skip_tables_absent(self, stats):
        present = {r["table_name"] for r in stats}
        for t in SKIP_TABLES:
            assert t not in present, f"Skipped table {t!r} should not appear"

    def test_non_numeric_cols_absent(self, stats):
        for r in stats:
            col = r["column_name"]
            # strip bracket suffix from legacy_chemical_descriptors rows
            base = col.split("[")[0]
            assert base not in NON_NUMERIC_COLS, f"Non-numeric col {col!r} in table {r['table_name']!r}"

    def test_optical_dispersion_wavelength(self, stats):
        row = next(
            (r for r in stats
             if r["table_name"] == "optical_dispersion" and r["column_name"] == "wavelength_nm"),
            None,
        )
        assert row is not None, "optical_dispersion.wavelength_nm not found"
        assert row["count"] == 2819
        assert row["missing_pct"] == 0.0
        assert row["min"] > 0
        assert row["units"] == "nm"

    def test_physical_density(self, stats):
        row = next(
            (r for r in stats
             if r["table_name"] == "physical_properties" and r["column_name"] == "density_g_cm3"),
            None,
        )
        assert row is not None
        assert row["count"] > 0
        assert row["units"] == "g/cm³"

    def test_missing_pct_bounds(self, stats):
        for r in stats:
            assert 0.0 <= r["missing_pct"] <= 100.0

    def test_count_plus_missing_equals_total(self, stats):
        for r in stats:
            assert r["count"] + r["missing_count"] == r["total_rows"], (
                f"{r['table_name']}.{r['column_name']}: "
                f"{r['count']} + {r['missing_count']} != {r['total_rows']}"
            )

    def test_legacy_descriptors_expanded(self, stats):
        desc_rows = [r for r in stats if r["table_name"] == "legacy_chemical_descriptors"]
        assert len(desc_rows) > 1, "legacy_chemical_descriptors should be expanded by descriptor_name"
        col_names = {r["column_name"] for r in desc_rows}
        assert any("value[" in c for c in col_names)

    def test_mean_within_min_max(self, stats):
        for r in stats:
            if r["count"] > 0 and not math.isnan(r["mean"]):
                assert r["min"] <= r["mean"] <= r["max"], (
                    f"{r['table_name']}.{r['column_name']}: "
                    f"mean {r['mean']} outside [{r['min']}, {r['max']}]"
                )


class TestPropertyStatisticsTable:
    def test_table_exists(self, con):
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='property_statistics'"
        ).fetchone()
        assert row is not None, "property_statistics table missing — run property_inventory.py first"

    def test_row_count(self, con):
        n = con.execute("SELECT COUNT(*) FROM property_statistics").fetchone()[0]
        assert n > 50, f"Expected >50 rows, got {n}"

    def test_no_duplicate_keys(self, con):
        dupes = con.execute("""
            SELECT table_name, column_name, COUNT(*) AS c
            FROM property_statistics
            GROUP BY table_name, column_name
            HAVING c > 1
        """).fetchall()
        assert dupes == [], f"Duplicate rows found: {dupes}"

    def test_optical_wavelength_stats_sane(self, con):
        row = con.execute("""
            SELECT count, min_val, max_val, mean_val
            FROM property_statistics
            WHERE table_name='optical_dispersion' AND column_name='wavelength_nm'
        """).fetchone()
        assert row is not None
        count, mn, mx, mean = row
        assert count == 2819
        assert mn > 0
        assert mx > mn
        assert mn <= mean <= mx

    def test_units_populated(self, con):
        rows = con.execute(
            "SELECT table_name, column_name, units FROM property_statistics WHERE units IS NULL"
        ).fetchall()
        assert rows == [], f"NULL units found: {rows}"
