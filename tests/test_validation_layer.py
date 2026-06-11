"""Tests for dataset_validation and spectral_validation population."""

import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "materials_normalized.db"
REPORTS_DIR = ROOT / "reports"

import sys
sys.path.insert(0, str(ROOT / "scripts"))

from populate_validation import (
    classify_scalar,
    classify_spectral,
    pairwise_spectral,
    rel_error_pct,
    _short_label,
)


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------

class TestRelErrorPct:
    def test_identical(self):
        assert rel_error_pct(5.0, 5.0) == pytest.approx(0.0)

    def test_symmetric_about_mid(self):
        r1 = rel_error_pct(10.0, 8.0)
        r2 = rel_error_pct(8.0, 10.0)
        assert r1 == pytest.approx(-r2)

    def test_both_zero(self):
        assert rel_error_pct(0.0, 0.0) == pytest.approx(0.0)

    def test_sign(self):
        # a > b → positive
        assert rel_error_pct(10.0, 8.0) > 0
        # a < b → negative
        assert rel_error_pct(8.0, 10.0) < 0

    def test_known_value(self):
        # (10 - 8) / ((10+8)/2) * 100 = 2/9*100 ≈ 22.22%
        assert rel_error_pct(10.0, 8.0) == pytest.approx(22.222, abs=0.01)


class TestClassifyScalar:
    def test_excellent(self):
        assert classify_scalar(0.0) == "excellent"
        assert classify_scalar(1.0) == "excellent"
        assert classify_scalar(-1.9) == "excellent"

    def test_warning(self):
        assert classify_scalar(2.0) == "warning"
        assert classify_scalar(5.0) == "warning"
        assert classify_scalar(-9.9) == "warning"

    def test_suspicious(self):
        assert classify_scalar(10.0) == "suspicious"
        assert classify_scalar(-25.0) == "suspicious"
        assert classify_scalar(100.0) == "suspicious"

    def test_boundary_at_two_pct(self):
        assert classify_scalar(1.999) == "excellent"
        assert classify_scalar(2.001) == "warning"

    def test_boundary_at_ten_pct(self):
        assert classify_scalar(9.999) == "warning"
        assert classify_scalar(10.001) == "suspicious"


class TestClassifySpectral:
    def test_many_points_excellent(self):
        cls = classify_spectral(pearson_r=0.99995, rmse=0.0005,
                                n_points=100, signal_range=2.0)
        assert cls == "excellent"

    def test_many_points_warning(self):
        cls = classify_spectral(pearson_r=0.9995, rmse=0.01,
                                n_points=50, signal_range=2.0)
        assert cls == "warning"

    def test_many_points_suspicious(self):
        cls = classify_spectral(pearson_r=0.95, rmse=0.5,
                                n_points=50, signal_range=2.0)
        assert cls == "suspicious"

    def test_few_points_excellent_low_nrmse(self):
        cls = classify_spectral(pearson_r=None, rmse=0.005,
                                n_points=1, signal_range=2.0)
        assert cls == "excellent"

    def test_few_points_warning(self):
        cls = classify_spectral(pearson_r=None, rmse=0.08,
                                n_points=2, signal_range=2.0)
        assert cls == "warning"

    def test_few_points_suspicious_high_nrmse(self):
        cls = classify_spectral(pearson_r=None, rmse=1.5,
                                n_points=2, signal_range=2.0)
        assert cls == "suspicious"


class TestPairwiseSpectral:
    def test_identical_arrays(self):
        wl = np.array([400.0, 500.0, 600.0, 700.0])
        v = np.array([1.5, 1.48, 1.46, 1.44])
        m = pairwise_spectral(wl, v, wl, v.copy())
        assert m["rmse"] == pytest.approx(0.0, abs=1e-10)
        assert m["mae"] == pytest.approx(0.0, abs=1e-10)
        assert m["max_deviation"] == pytest.approx(0.0, abs=1e-10)
        assert m["n_overlap_points"] == 4

    def test_no_overlap(self):
        wl_a = np.array([200.0, 300.0, 400.0])
        wl_b = np.array([500.0, 600.0, 700.0])
        m = pairwise_spectral(wl_a, np.ones(3), wl_b, np.ones(3))
        assert m == {}

    def test_partial_overlap(self):
        wl_a = np.array([400.0, 500.0, 600.0, 700.0])
        wl_b = np.array([550.0, 650.0, 750.0])
        va = np.array([1.5, 1.48, 1.46, 1.44])
        vb = np.array([1.47, 1.45, 1.43])
        m = pairwise_spectral(wl_a, va, wl_b, vb)
        assert m["overlap_wl_min"] == pytest.approx(550.0)
        assert m["overlap_wl_max"] == pytest.approx(700.0)

    def test_single_point_each(self):
        wl_a = np.array([633.0])
        wl_b = np.array([633.0])
        va = np.array([0.18])
        vb = np.array([0.1956])
        m = pairwise_spectral(wl_a, va, wl_b, vb)
        assert m["n_overlap_points"] == 1
        assert m["rmse"] == pytest.approx(abs(0.18 - 0.1956), abs=1e-6)
        # pearson_r undefined for 1 point
        assert m["pearson_r"] is None

    def test_pearson_computed_for_3_plus_points(self):
        wl = np.array([400.0, 500.0, 600.0, 700.0])
        va = np.array([1.5, 1.48, 1.46, 1.44])
        # Perfect linear shift → r=1.0
        vb = va + 0.01
        m = pairwise_spectral(wl, va, wl, vb)
        assert m["pearson_r"] == pytest.approx(1.0, abs=1e-10)
        assert m["rmse"] == pytest.approx(0.01, abs=1e-10)

    def test_constant_signal_range_fallback(self):
        """Single-point case uses abs(mean) as signal_range denominator."""
        wl_a = np.array([633.0])
        wl_b = np.array([633.0])
        m = pairwise_spectral(wl_a, np.array([2.0]), wl_b, np.array([2.0]))
        assert m["rmse"] == pytest.approx(0.0, abs=1e-10)

    def test_rmse_mae_max_dev_consistency(self):
        wl = np.array([400.0, 500.0, 600.0])
        va = np.array([1.5, 1.6, 1.3])
        vb = np.array([1.4, 1.7, 1.2])
        m = pairwise_spectral(wl, va, wl, vb)
        diffs = np.abs(va - vb)
        assert m["mae"] == pytest.approx(float(np.mean(diffs)), abs=1e-8)
        assert m["max_deviation"] == pytest.approx(float(np.max(diffs)), abs=1e-8)
        assert m["rmse"] == pytest.approx(
            float(np.sqrt(np.mean((va - vb) ** 2))), abs=1e-8
        )


class TestShortLabel:
    def test_none_input(self):
        assert _short_label(None) == "(unlabelled)"

    def test_html_multiline_truncated(self):
        label = "Author Name.\nTitle\n<a href=...>Journal</a>\n"
        result = _short_label(label)
        assert "\n" not in result

    def test_short_passes_through(self):
        assert _short_label("short") == "short"

    def test_truncation_at_max_len(self):
        long = "A" * 100
        result = _short_label(long, max_len=80)
        assert len(result) <= 81  # 80 + "…"
        assert result.endswith("…")


# ---------------------------------------------------------------------------
# Integration tests — require live DB
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def con():
    if not DB_PATH.exists():
        pytest.skip(f"DB not found: {DB_PATH}")
    c = sqlite3.connect(DB_PATH)
    yield c
    c.close()


class TestDatasetValidationTable:
    def test_table_exists(self, con):
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='dataset_validation'"
        ).fetchone()
        assert row is not None

    def test_has_rows(self, con):
        n = con.execute("SELECT COUNT(*) FROM dataset_validation").fetchone()[0]
        assert n > 0, "dataset_validation is empty"

    def test_no_self_comparisons(self, con):
        """dataset_a must not equal dataset_b."""
        bad = con.execute(
            "SELECT COUNT(*) FROM dataset_validation WHERE dataset_a = dataset_b"
        ).fetchone()[0]
        assert bad == 0, f"{bad} rows have dataset_a == dataset_b"

    def test_all_classifications_valid(self, con):
        valid = {"excellent", "warning", "suspicious"}
        rows = con.execute(
            "SELECT DISTINCT classification FROM dataset_validation "
            "WHERE classification IS NOT NULL"
        ).fetchall()
        for (cls,) in rows:
            assert cls in valid, f"Unknown classification: {cls!r}"

    def test_sld_agreement_between_sources(self, con):
        """Both SLD calculation sources should agree to within floating-point."""
        bad = con.execute("""
            SELECT COUNT(*) FROM dataset_validation
            WHERE property_name IN ('xray_sld', 'neutron_sld')
              AND classification = 'suspicious'
        """).fetchone()[0]
        assert bad == 0, f"{bad} SLD pairs flagged suspicious"

    def test_relative_error_and_rmse_consistent(self, con):
        """For scalar comparisons, rmse = |a-b| so rmse >= 0."""
        rows = con.execute("SELECT rmse FROM dataset_validation").fetchall()
        for (rmse,) in rows:
            if rmse is not None:
                assert rmse >= 0, f"Negative RMSE: {rmse}"

    def test_no_null_property_name(self, con):
        n = con.execute(
            "SELECT COUNT(*) FROM dataset_validation WHERE property_name IS NULL"
        ).fetchone()[0]
        assert n == 0

    def test_dielectric_conditions_noted(self, con):
        """Dielectric comparisons across different conditions have notes."""
        rows = con.execute("""
            SELECT notes FROM dataset_validation
            WHERE property_name = 'dielectric_constant'
              AND notes LIKE '%conditions differ%'
        """).fetchall()
        # Water, DPPC, PMMA all have condition mismatches
        assert len(rows) >= 3

    def test_unique_constraint_respected(self, con):
        rows = con.execute("""
            SELECT material_id, property_name, dataset_a, dataset_b, COUNT(*) as c
            FROM dataset_validation
            GROUP BY material_id, property_name, dataset_a, dataset_b
            HAVING c > 1
        """).fetchall()
        assert rows == [], f"Duplicate rows: {rows}"


class TestSpectralValidationTable:
    def test_table_exists(self, con):
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='spectral_validation'"
        ).fetchone()
        assert row is not None

    def test_has_rows(self, con):
        n = con.execute("SELECT COUNT(*) FROM spectral_validation").fetchone()[0]
        assert n > 0

    def test_gold_comparison_present(self, con):
        rows = con.execute("""
            SELECT sv.material_id, sv.property, sv.classification
            FROM spectral_validation sv
            JOIN materials m ON m.material_id = sv.material_id
            WHERE m.name = 'Gold'
        """).fetchall()
        assert len(rows) >= 2  # n and k
        props = {r[1] for r in rows}
        assert "n" in props
        assert "k" in props

    def test_dppc_peg_null_label_handled(self, con):
        """Materials with NULL dataset labels must be included in spectral_validation."""
        for name in ("DPPC", "PEG"):
            rows = con.execute("""
                SELECT sv.sv_id FROM spectral_validation sv
                JOIN materials m ON m.material_id = sv.material_id
                WHERE m.name = ?
            """, (name,)).fetchall()
            assert len(rows) >= 1, f"{name} missing from spectral_validation"

    def test_no_overlap_rows_have_null_metrics(self, con):
        rows = con.execute("""
            SELECT sv_id, pearson_r, rmse, mae, max_deviation
            FROM spectral_validation WHERE n_overlap_points = 0
        """).fetchall()
        for svid, pr, rmse, mae, mxd in rows:
            assert pr is None, f"sv_id={svid}: pearson_r should be NULL for no-overlap"
            assert rmse is None, f"sv_id={svid}: rmse should be NULL for no-overlap"

    def test_overlap_rows_have_valid_metrics(self, con):
        rows = con.execute("""
            SELECT sv_id, rmse, mae, max_deviation, n_overlap_points
            FROM spectral_validation WHERE n_overlap_points > 0
        """).fetchall()
        for svid, rmse, mae, mxd, np_ in rows:
            assert rmse is not None, f"sv_id={svid}: rmse NULL despite overlap"
            assert rmse >= 0, f"sv_id={svid}: negative rmse"
            assert mae >= 0, f"sv_id={svid}: negative mae"
            assert mxd >= mae, (
                f"sv_id={svid}: max_deviation {mxd} < mae {mae}"
            )

    def test_classifications_valid_where_set(self, con):
        valid = {"excellent", "warning", "suspicious"}
        rows = con.execute(
            "SELECT DISTINCT classification FROM spectral_validation "
            "WHERE classification IS NOT NULL"
        ).fetchall()
        for (cls,) in rows:
            assert cls in valid

    def test_wavelength_range_sensible(self, con):
        rows = con.execute("""
            SELECT sv_id, overlap_wl_min, overlap_wl_max
            FROM spectral_validation WHERE overlap_wl_min IS NOT NULL
        """).fetchall()
        for svid, lo, hi in rows:
            assert lo > 0, f"sv_id={svid}: overlap_wl_min <= 0"
            assert hi >= lo, f"sv_id={svid}: overlap_wl_max < overlap_wl_min"
            assert hi < 1e7, f"sv_id={svid}: unreasonably large wavelength"

    def test_gold_k_comparison_values(self, con):
        """Gold k at 633nm: interpolated=3.45, full spectrum ≈3.433 → RMSE ≈ 0.017."""
        row = con.execute("""
            SELECT rmse, classification FROM spectral_validation sv
            JOIN materials m ON m.material_id = sv.material_id
            WHERE m.name = 'Gold' AND sv.property = 'k'
              AND sv.n_overlap_points > 0
        """).fetchone()
        assert row is not None
        rmse, cls = row
        assert rmse == pytest.approx(0.017, abs=0.005)


class TestSpectralAnomaliesTable:
    def test_table_exists(self, con):
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='spectral_anomalies'"
        ).fetchone()
        assert row is not None

    def test_has_rows(self, con):
        n = con.execute("SELECT COUNT(*) FROM spectral_anomalies").fetchone()[0]
        assert n > 0

    def test_severity_values_valid(self, con):
        rows = con.execute(
            "SELECT DISTINCT severity FROM spectral_anomalies"
        ).fetchall()
        valid = {"warning", "critical"}
        for (sev,) in rows:
            assert sev in valid, f"Unknown severity: {sev!r}"

    def test_anomaly_types_valid(self, con):
        rows = con.execute(
            "SELECT DISTINCT anomaly_type FROM spectral_anomalies"
        ).fetchall()
        valid = {
            "duplicate_wavelength", "non_monotonic_grid", "sparse_coverage",
            "discontinuity", "zero_variance", "unphysical_value", "duplicate_spectrum",
        }
        for (atype,) in rows:
            assert atype in valid, f"Unknown anomaly_type: {atype!r}"

    def test_gold_discontinuity_flagged(self, con):
        """Gold JC full-spectrum has a large gap near the end (IR)."""
        row = con.execute("""
            SELECT anomaly_type FROM spectral_anomalies sa
            JOIN materials m ON m.material_id = sa.material_id
            WHERE m.name = 'Gold' AND sa.anomaly_type = 'discontinuity'
        """).fetchone()
        assert row is not None, "Gold IR discontinuity not flagged"

    def test_sparse_datasets_flagged(self, con):
        """Single-point and 2-point datasets must be flagged as sparse_coverage."""
        n = con.execute("""
            SELECT COUNT(*) FROM spectral_anomalies
            WHERE anomaly_type = 'sparse_coverage'
        """).fetchone()[0]
        assert n >= 8, f"Expected ≥8 sparse flags, got {n}"

    def test_no_unphysical_n_in_known_good_materials(self, con):
        """Water, Gold, SiO2 should have no unphysical n values."""
        for name in ("Water", "Gold", "SiO2"):
            row = con.execute("""
                SELECT COUNT(*) FROM spectral_anomalies sa
                JOIN materials m ON m.material_id = sa.material_id
                WHERE m.name = ? AND sa.property = 'n'
                  AND sa.anomaly_type = 'unphysical_value'
            """, (name,)).fetchone()
            assert row[0] == 0, f"{name}: unexpected unphysical n flag"

    def test_no_raw_data_modified(self, con):
        """Row counts in optical_dispersion must be unchanged (2819)."""
        n = con.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0]
        assert n == 2819, f"optical_dispersion row count changed: {n}"


class TestReportFiles:
    def test_dataset_similarity_report_exists(self):
        p = REPORTS_DIR / "dataset_similarity_report.md"
        assert p.exists()
        content = p.read_text()
        assert "# Dataset Similarity Report" in content
        assert "## Per-Property Results" in content

    def test_spectral_validation_report_exists(self):
        p = REPORTS_DIR / "spectral_validation_report.md"
        assert p.exists()
        content = p.read_text()
        assert "# Spectral Validation Report" in content
        assert "## Overall Database Statistics" in content

    def test_dataset_validation_csv_exists(self):
        p = REPORTS_DIR / "dataset_validation.csv"
        assert p.exists()
        lines = p.read_text().strip().splitlines()
        assert lines[0].startswith("validation_id")
        assert len(lines) >= 2  # header + data

    def test_spectral_validation_csv_exists(self):
        p = REPORTS_DIR / "spectral_validation.csv"
        assert p.exists()
        lines = p.read_text().strip().splitlines()
        assert lines[0].startswith("sv_id")
        assert len(lines) >= 2

    def test_csv_columns_match_expected(self):
        p = REPORTS_DIR / "dataset_validation.csv"
        header = p.read_text().splitlines()[0]
        expected = [
            "validation_id", "material_id", "material_name",
            "property_name", "dataset_a", "dataset_b",
            "pearson_r", "rmse", "mean_relative_error",
            "classification", "notes",
        ]
        for col in expected:
            assert col in header, f"Missing column {col!r} in dataset_validation.csv"

    def test_spectral_csv_has_no_overlap_rows(self):
        p = REPORTS_DIR / "spectral_validation.csv"
        lines = p.read_text().strip().splitlines()
        no_overlap = [l for l in lines[1:] if "no overlapping" in l]
        assert len(no_overlap) >= 4, "Expected ≥4 no-overlap rows in spectral CSV"
