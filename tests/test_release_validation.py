"""scripts/release_validation.py on a synthetic database with known answers: like-for-like pairing, metrics, classification,
consensus from measured ambient datasets only, and the confidence score. The release build's own output is checked in
tests/test_release_build.py."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_validation as rv  # noqa: E402

MEASURED = "main/GaAs/nk/Aspnes.yml"   # dataset_kind: measured
MEASURED2 = "main/GaAs/nk/Jellison.yml"
MEASURED3 = "main/GaAs/nk/Papatryfonos.yml"
MODEL = "main/GaAs/nk/Adachi.yml"      # dataset_kind: model fit (calculation script)


def _db(datasets):
    """datasets: (material_id, label, raw_record_table, temperature_c, [(wl, n, k), ...])"""
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE optical_dispersion (material_id INT, dataset_label TEXT, raw_record_table TEXT, wavelength_nm REAL, n REAL,
                                         k REAL, temperature_c REAL);
        CREATE TABLE dataset_validation (validation_id INTEGER PRIMARY KEY, material_id INT, property_name TEXT, dataset_a TEXT,
                                         dataset_b TEXT, pearson_r REAL, rmse REAL, mean_relative_error REAL, classification TEXT, notes TEXT);
        CREATE TABLE consensus_properties (material_id INT, property_name TEXT, consensus_value REAL, std_dev REAL, num_sources INT,
                                           confidence_score REAL, classification TEXT, PRIMARY KEY(material_id, property_name));""")
    for mid, label, table, t, rows in datasets:
        c.executemany("INSERT INTO optical_dispersion VALUES (?,?,?,?,?,?,?)", [(mid, label, table, wl, n, k, t) for wl, n, k in rows])
    return c


def flat(n, k=None, lo=400, hi=900, step=10):
    return [(float(w), n, k) for w in range(lo, hi + 1, step)]


def test_parse_label():
    assert rv.parse_label("wurtzite | Pastrnak1966 | o-ray") == ("wurtzite", "Pastrnak1966", "o-ray")
    assert rv.parse_label("Aspnes1983") == (None, "Aspnes1983", None)
    assert rv.parse_label("Boyd1972 | e-ray") == (None, "Boyd1972", "e-ray")
    assert rv.parse_label("liquid | Hale1973") == ("liquid", "Hale1973", None)


def test_pair_metrics_and_classification():
    c = _db([(1, "A1990", MEASURED, None, flat(3.00)), (1, "B1991", MEASURED2, None, flat(3.03)),
             (1, "C1992", MEASURED3, None, flat(3.60))])
    rv.populate(c)
    got = {(a, b): (err, cls) for a, b, err, cls in c.execute(
        "SELECT dataset_a, dataset_b, mean_relative_error, classification FROM dataset_validation WHERE property_name='n'")}
    assert got[("A1990", "B1991")][0] == pytest.approx(0.03 / 3.015) and got[("A1990", "B1991")][1] == "excellent"
    assert got[("A1990", "C1992")][1] == "suspicious"  # 18%
    assert got[("B1991", "C1992")][1] == "suspicious"


def test_only_like_for_like_is_compared():
    c = _db([(1, "hexagonal | A1990 | o-ray", MEASURED, None, flat(2.5)),
             (1, "hexagonal | B1991 | e-ray", MEASURED2, None, flat(2.6)),      # other axis
             (1, "cubic | C1992", MEASURED3, None, flat(2.5)),                  # other phase
             (1, "hexagonal | D1993 | o-ray", MODEL, 600.0, flat(2.9)),          # other temperature
             (2, "hexagonal | E1994 | o-ray", MEASURED, None, flat(2.5))])       # other material
    rv.populate(c)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation").fetchone()[0] == 0


def test_no_overlap_means_no_comparison():
    c = _db([(1, "A1990", MEASURED, None, flat(3.0, lo=400, hi=600)), (1, "B1991", MEASURED2, None, flat(3.0, lo=700, hi=900))])
    rv.populate(c)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation").fetchone()[0] == 0


def test_k_near_zero_is_compared_in_absolute_terms():
    c = _db([(1, "A1990", MEASURED, None, flat(3.0, 0.0001)), (1, "B1991", MEASURED2, None, flat(3.0, 0.0011))])
    rv.populate(c)
    err, cls, notes = c.execute("SELECT mean_relative_error, classification, notes FROM dataset_validation WHERE property_name='k'").fetchone()
    assert err == pytest.approx(0.001) and cls == "excellent" and "absolute" in notes


def test_consensus_uses_measured_ambient_datasets_only():
    c = _db([(1, "A1990", MEASURED, None, flat(3.00)), (1, "B1991", MEASURED2, 22.0, flat(3.02)),
             (1, "C1992", MEASURED3, 26.85, flat(3.04)),
             (1, "Model1989", MODEL, None, flat(9.0)),                     # a model fit never votes
             (1, "Hot2025", MEASURED, 600.0, flat(9.0))])                  # nor a non-ambient dataset
    rv.populate(c)
    val, sd, n, conf, cls = c.execute("SELECT consensus_value, std_dev, num_sources, confidence_score, classification "
                                      "FROM consensus_properties WHERE property_name='n_633nm'").fetchone()
    assert (val, n, cls) == (pytest.approx(3.02), 3, "excellent") and sd == pytest.approx(0.02)
    spread = 0.04 / 3.02
    assert conf == pytest.approx((1 - 0.5 ** 3) * (1 - spread / 0.10), abs=1e-4)


def test_single_source_confidence_is_one_half_and_model_only_gives_no_consensus():
    c = _db([(1, "A1990", MEASURED, None, flat(3.0)), (2, "Model1989", MODEL, None, flat(3.0))])
    rv.populate(c)
    rows = c.execute("SELECT material_id, property_name, confidence_score, classification FROM consensus_properties").fetchall()
    assert rows == [(1, "n_633nm", 0.5, "single_source")]


def test_consensus_is_per_phase_and_axis_and_needs_633_nm_inside_the_data():
    c = _db([(1, "wurtzite | A1990 | o-ray", MEASURED, None, flat(2.1)), (1, "wurtzite | B1991 | e-ray", MEASURED2, None, flat(2.2)),
             (1, "wurtzite | C1992 | o-ray", MEASURED3, None, flat(2.1, lo=700, hi=900))])  # does not reach 633 nm
    rv.populate(c)
    names = {r[0]: r[1] for r in c.execute("SELECT property_name, num_sources FROM consensus_properties")}
    assert names == {"n_633nm | wurtzite | o-ray": 1, "n_633nm | wurtzite | e-ray": 1}


def test_rerun_replaces_rather_than_appends():
    c = _db([(1, "A1990", MEASURED, None, flat(3.0)), (1, "B1991", MEASURED2, None, flat(3.01))])
    rv.populate(c)
    rv.populate(c)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM consensus_properties").fetchone()[0] == 1
