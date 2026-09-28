"""scripts/analyze_db.py on a small synthetic database with planted problems: every planted anomaly is found and counted, the
technique field is judged by content (a channel such as 'refractiveindex.info' is not a technique), units are classified by
where they live, the blueprint maps columns to concrete targets, and the database is never modified."""
import hashlib
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_db as az  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "mini.sqlite"
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT NOT NULL, formula TEXT, inchikey TEXT, cas_number TEXT,
                                pubchem_cid INTEGER, molecular_weight REAL);
        CREATE TABLE sources (source_id INTEGER PRIMARY KEY, doi TEXT, title TEXT, authors TEXT, journal TEXT, year INTEGER,
                              technique TEXT, url TEXT, uncertainty REAL, notes TEXT);
        CREATE TABLE optical_dispersion (record_id INTEGER PRIMARY KEY, material_id INTEGER, wavelength_nm REAL, n REAL, k REAL,
                                         temperature_c REAL, dataset_label TEXT, raw_record_table TEXT, raw_record_id INTEGER,
                                         source_id INTEGER);
        CREATE TABLE physical_properties (record_id INTEGER PRIMARY KEY, material_id INTEGER, density_g_cm3 REAL, xray_sld REAL,
                                          neutron_sld REAL, dielectric_constant REAL, temperature_c REAL, frequency_hz REAL,
                                          wavelength_nm REAL, energy_ev REAL, dataset_label TEXT, raw_record_table TEXT,
                                          raw_record_id INTEGER, source_id INTEGER);
        INSERT INTO materials VALUES (1, 'Glass A', NULL, NULL, NULL, NULL, NULL),
                                     (2, 'Silicon', 'Si', 'XUIMIQQOEAHHFN', NULL, 5461123, 28.1);
        INSERT INTO sources VALUES (1, '10.1/x', 'A paper', 'X', 'J', 2001, 'refractiveindex.info', NULL, NULL, NULL),
                                   (2, NULL, 'A catalog', NULL, NULL, NULL, 'spectroscopic ellipsometry', NULL, NULL, NULL);
        INSERT INTO optical_dispersion (material_id, wavelength_nm, n, k, temperature_c, dataset_label, raw_record_table,
                                        raw_record_id, source_id) VALUES
          (1, 500, 1.5, 0.0, 20, 'CAT2017', 'specs/a.yml', 0, 2), (1, 600, 1.49, -1e-6, 20, 'CAT2017', 'specs/a.yml', 1, 2),
          (1, 600, 1.49, 0.0, 20, 'CAT2017', 'specs/a.yml', 2, 2),
          (2, 500, 4.3, 0.07, NULL, 'film on glass | Paper2001', 'main/Si.yml', 0, 1),
          (2, 700, 3.8, 0.01, NULL, 'film on glass | Paper2001', 'main/Si.yml', 1, 1),
          (2, 800, 3.7, 0.005, NULL, 'film on glass | Paper2001', 'main/Si.yml', 2, 1);
        INSERT INTO physical_properties (material_id, density_g_cm3, dataset_label, source_id) VALUES
          (2, 2.33, 'density_literature', 1), (1, 40.0, 'density_bad', 2);
    """)
    c.commit()
    c.close()
    return p


def test_audit_finds_every_planted_problem_and_never_writes(db, tmp_path):
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    out = tmp_path / "audit"
    assert az.main([str(db), "--out", str(out)]) == 0
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before  # read-only
    for f in ("schema_gaps.csv", "schema_gaps.md", "data_completeness.csv", "anomalies.csv", "migration_recommendations.yaml"):
        assert (out / f).exists(), f
    an = pd.read_csv(out / "anomalies.csv").set_index("anomaly")["count"].to_dict()
    assert an["negative k"] == 1 and an["duplicate wavelength within one spectrum"] == 1
    assert an["density <= 0 or > 23 g/cm3"] == 1 and an["source with neither DOI nor URL"] == 1
    comp = pd.read_csv(out / "data_completeness.csv").set_index(["scope", "metric"]).percent
    assert comp[("spectrum", "sources.technique filled (any value)")] == 100.0
    assert comp[("spectrum", "measurement technique actually named")] == 50.0  # ellipsometry yes, 'refractiveindex.info' no
    assert comp[("spectrum", "temperature stated on every point")] == 50.0
    assert comp[("material", "has an external identifier (InChIKey / PubChem / CAS)")] == 50.0


def test_units_are_classified_by_where_they_live(db):
    cols = az.introspect_schema(az.DB(db)).set_index(["table", "column"]).unit_storage
    assert cols[("optical_dispersion", "wavelength_nm")] == "in column name"
    assert cols[("optical_dispersion", "n")] == "dimensionless (implied)"


def test_blueprint_maps_columns_to_concrete_targets(db, tmp_path):
    az.main([str(db), "--out", str(tmp_path / "a")])
    recs = yaml.safe_load((tmp_path / "a" / "migration_recommendations.yaml").read_text())
    m = {r["column"]: r for r in recs["column_mapping"]}
    assert m["optical_dispersion.wavelength_nm"]["entity"] == "PropertyValue"
    assert m["optical_dispersion.wavelength_nm"]["target_field"] == "x_value"
    assert m["optical_dispersion.temperature_c"]["target_field"] == "temperature_K"
    assert m["optical_dispersion.dataset_label"]["action"] == "split"
    assert set(recs["entities"]) == {"Material", "Specimen", "Measurement", "PropertyValue", "ProvenanceRecord"}
    assert "specimen_id" in recs["entities"]["Specimen"]["missing_in_current_schema"]
