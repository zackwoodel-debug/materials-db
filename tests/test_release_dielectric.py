"""scripts/release_dielectric.py: which materials get Materials Project DFPT dielectric constants, and a benchmark of the stored
values against measured static dielectric constants (room temperature, handbook values)."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_dielectric as rdl  # noqa: E402

CACHE = json.loads(rdl.CACHE.read_text())
STRUCT = json.loads((ROOT / "data" / "descriptors" / "mp_structural.json").read_text())["entries"]
# measured static dielectric constants (CRC / semiconductor handbooks)
MEASURED = {"LiF": 9.0, "KCl": 4.8, "C": 5.7, "CaF2": 6.8, "MgO": 9.8, "NaCl": 5.9, "Si": 11.7, "AlSb": 12.0, "ZnS": 8.3, "AlAs": 10.1,
            "GaP": 11.1, "ZnSe": 9.1, "CdTe": 10.2, "Ge": 16.0, "GaSb": 15.7, "InSb": 16.8, "GaAs": 12.9, "InP": 12.5}


def test_cache_values_are_the_mean_of_the_principal_values_and_physical():
    import numpy as np
    assert CACHE["mp_database_version"] == json.loads((ROOT / "data" / "descriptors" / "mp_structural.json").read_text())["mp_database_version"]
    for mp, e in CACHE["entries"].items():
        assert e["e_total"] == pytest.approx(float(np.mean(e["eigenvalues_total"])), rel=1e-4), mp
        assert e["e_total"] == pytest.approx(e["e_electronic"] + e["e_ionic"], rel=1e-4), mp
        assert e["e_electronic"] >= 1.0 and e["e_ionic"] >= -1e-3, mp


def test_the_gap_cutoff_keeps_the_benchmark_within_its_stated_bounds():
    """Kept (MP gap >= 0.5 eV): -10% .. +30% of the measured value. Excluded ones are exactly the badly overestimated ones."""
    by_formula = {STRUCT[mp]["formula_pretty"]: (STRUCT[mp]["band_gap_ev"], e["e_total"]) for mp, e in CACHE["entries"].items()}
    for f, measured in MEASURED.items():
        gap, eps = by_formula[f]
        err = (eps - measured) / measured
        if gap >= rdl.MIN_GAP_EV:
            assert -0.10 <= err <= 0.30, (f, gap, eps)
        else:
            assert err > 0.30, (f, gap, eps)  # the cut-off only removes values that are far off


def _db(materials):
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE chemical_descriptors (material_id INT, descriptor_json TEXT);
        CREATE TABLE sources (source_id INTEGER PRIMARY KEY, doi TEXT UNIQUE, title TEXT, authors TEXT, journal TEXT, year INT,
                              technique TEXT, url TEXT, notes TEXT);
        CREATE TABLE physical_properties (record_id INTEGER PRIMARY KEY, material_id INT, density_g_cm3 REAL, dielectric_constant REAL,
                                          frequency_hz REAL, dataset_label TEXT, source_id INT);""")
    for mid, name, struct, density_label in materials:
        c.execute("INSERT INTO materials VALUES (?,?)", (mid, name))
        c.execute("INSERT INTO chemical_descriptors VALUES (?,?)", (mid, json.dumps(dict(structural=struct))))
        if density_label:
            c.execute("INSERT INTO physical_properties(material_id, density_g_cm3, dataset_label, source_id) VALUES (?,?,?,0)", (mid, 3.0, density_label))
    return c


def test_rows_labels_and_exclusions(tmp_path):
    cache = tmp_path / "d.json"
    cache.write_text(json.dumps(dict(mp_database_version="X", entries={
        "mp-1": dict(e_total=10.0, e_electronic=8.0), "mp-2": dict(e_total=5.0, e_electronic=4.0),
        "mp-3": dict(e_total=30.0, e_electronic=25.0)})))
    c = _db([(1, "Crystal", dict(mp_id="mp-1", applies_to="the material (chosen)", band_gap_ev=2.0), "rock salt | density_MP_DFT"),
             (2, "Glass", dict(mp_id="mp-2", applies_to="crystalline reference only: amorphous", band_gap_ev=5.0), None),
             (3, "Narrow", dict(mp_id="mp-3", applies_to="the material", band_gap_ev=0.2), None),
             (4, "NoData", dict(mp_id="mp-9", applies_to="the material", band_gap_ev=3.0), None)])
    r = rdl.populate(c, cache)
    rows = c.execute("SELECT material_id, dielectric_constant, frequency_hz, dataset_label FROM physical_properties "
                     "WHERE dielectric_constant IS NOT NULL ORDER BY dielectric_constant").fetchall()
    assert rows == [(1, 8.0, None, "rock salt | dielectric_electronic | MP_DFPT"), (1, 10.0, 0.0, "rock salt | dielectric_static_total | MP_DFPT")]
    assert [x["material"] for x in r["not_stored_reference_only"]] == ["Glass"]
    assert [x["material"] for x in r["not_stored_narrow_gap"]] == ["Narrow"]
    assert c.execute("SELECT doi FROM sources").fetchone()[0] == "10.1038/sdata.2016.134"
