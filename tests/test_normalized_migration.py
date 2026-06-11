from pathlib import Path
import sqlite3
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "migration_scripts"))

from migrate_normalized import classify, compute_consensus
from validate_datasets import classify_correlation, compare_spectra


def test_optical_dispersion_generates_dielectric_terms(tmp_path):
    db_path = tmp_path / "schema.db"
    schema_path = ROOT / "updated_sql_schema.sql"

    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO materials(material_id, name) VALUES(1, 'Water')")
        conn.execute("INSERT INTO sources(source_id, notes) VALUES(1, 'test source')")
        conn.execute(
            """
            INSERT INTO optical_dispersion(material_id, wavelength_nm, n, k, source_id)
            VALUES(1, 633.0, 1.5, 0.1, 1)
            """
        )
        eps_real, eps_imag = conn.execute(
            "SELECT eps_real, eps_imag FROM optical_dispersion"
        ).fetchone()

    assert eps_real == 2.24
    assert eps_imag == 0.30000000000000004


def test_mechanical_context_is_required(tmp_path):
    db_path = tmp_path / "schema.db"
    schema_path = ROOT / "updated_sql_schema.sql"

    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO materials(material_id, name) VALUES(1, 'PMMA')")
        conn.execute("INSERT INTO sources(source_id, notes) VALUES(1, 'test source')")
        try:
            conn.execute(
                """
                INSERT INTO mechanical_properties(
                    material_id, storage_modulus, temperature_c, frequency_hz, source_id
                )
                VALUES(1, 1.2, NULL, 1.0, 1)
                """
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Mechanical properties accepted missing temperature")


def test_consensus_classification_thresholds():
    assert classify([100.0, 103.0])[0] == "excellent"
    assert classify([100.0, 108.0])[0] == "warning"
    assert classify([100.0, 125.0])[0] == "suspicious"


def test_compute_consensus_from_physical_properties(tmp_path):
    db_path = tmp_path / "schema.db"
    schema_path = ROOT / "updated_sql_schema.sql"

    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO materials(material_id, name) VALUES(1, 'Gold')")
        conn.execute("INSERT INTO sources(source_id, notes) VALUES(1, 'source a')")
        conn.execute("INSERT INTO sources(source_id, notes) VALUES(2, 'source b')")
        conn.execute(
            """
            INSERT INTO physical_properties(material_id, density_g_cm3, source_id)
            VALUES(1, 19.30, 1), (1, 19.34, 2)
            """
        )
        inserted = compute_consensus(conn)
        row = conn.execute(
            """
            SELECT consensus_value, num_sources, classification
            FROM consensus_properties
            WHERE material_id = 1 AND property_name = 'density_g_cm3'
            """
        ).fetchone()

    assert inserted >= 1
    assert round(row[0], 2) == 19.32
    assert row[1] == 2
    assert row[2] == "excellent"


def test_spectrum_similarity_metrics():
    left = np.array([1.0, 2.0, 3.0, 4.0])
    right = np.array([1.01, 2.01, 3.01, 4.01])

    metrics = compare_spectra(left, right)

    assert metrics["classification"] == "excellent"
    assert metrics["pearson_r"] > 0.99
    assert metrics["rmse"] > 0
    assert classify_correlation(0.93) == "warning"
