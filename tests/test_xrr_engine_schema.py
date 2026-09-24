"""Tests for the xrr-engine-schema-fix work: xrr_engine.py / simulate_xrr.py
supporting both the legacy materials.db schema and the new oxide-schema
(updated_sql_schema.sql) database, selecting layers by material +
dataset_label, and computing SLD via periodictable instead of the old
hardcoded (17-element) ATOMS table.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.calculators.xrr_engine import (  # noqa: E402
    _detect_schema, _normalize_formula, compute_xrr, read_material,
)
from materials_db.calculators.simulate_xrr import parse_stack, _LAYER_RE  # noqa: E402

LEGACY_SCHEMA = """
CREATE TABLE materials (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, formula TEXT, density_g_cm3 REAL
);
"""

OXIDE_SCHEMA = """
CREATE TABLE materials (
    material_id INTEGER PRIMARY KEY, name TEXT UNIQUE, formula TEXT
);
CREATE TABLE physical_properties (
    record_id INTEGER PRIMARY KEY, material_id INTEGER, density_g_cm3 REAL,
    dataset_label TEXT
);
"""


@pytest.fixture
def legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(LEGACY_SCHEMA)
    conn.execute("INSERT INTO materials (name, formula, density_g_cm3) VALUES (?, ?, ?)",
                 ("PMMA", "(C5H8O2)n", 1.19))
    conn.execute("INSERT INTO materials (name, formula, density_g_cm3) VALUES (?, ?, ?)",
                 ("Silicon", "Si", 2.329))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def oxide_db_single(tmp_path):
    """One material, one density row -- the common case (matches the real
    50-oxide dataset, where every material has exactly one polymorph)."""
    db_path = tmp_path / "oxide_single.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(OXIDE_SCHEMA)
    conn.execute("INSERT INTO materials (material_id, name, formula) VALUES (1, ?, ?)",
                 ("Titanium dioxide (rutile / anatase)", "TiO2"))
    conn.execute("INSERT INTO physical_properties (material_id, density_g_cm3, dataset_label) "
                 "VALUES (1, ?, ?)", (4.2362, "rutile | density_MP_DFT"))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def oxide_db_multi(tmp_path):
    """One material name with TWO polymorph density rows -- the ambiguous
    case the real dataset doesn't currently have, but the schema allows."""
    db_path = tmp_path / "oxide_multi.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(OXIDE_SCHEMA)
    conn.execute("INSERT INTO materials (material_id, name, formula) VALUES (1, ?, ?)",
                 ("Titanium dioxide", "TiO2"))
    conn.execute("INSERT INTO physical_properties (material_id, density_g_cm3, dataset_label) "
                 "VALUES (1, ?, ?)", (4.2362, "rutile | density_MP_DFT"))
    conn.execute("INSERT INTO physical_properties (material_id, density_g_cm3, dataset_label) "
                 "VALUES (1, ?, ?)", (3.8934, "anatase | density_MP_DFT"))
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Schema detection
# ---------------------------------------------------------------------------

def test_detect_schema_legacy(legacy_db):
    conn = sqlite3.connect(str(legacy_db))
    assert _detect_schema(conn) == "legacy"
    conn.close()


def test_detect_schema_oxide(oxide_db_single):
    conn = sqlite3.connect(str(oxide_db_single))
    assert _detect_schema(conn) == "oxide"
    conn.close()


def test_detect_schema_unrecognized(tmp_path):
    db_path = tmp_path / "junk.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE materials (id INTEGER)")
    conn.commit()
    with pytest.raises(ValueError, match="Unrecognized"):
        _detect_schema(conn)
    conn.close()


# ---------------------------------------------------------------------------
# 1. read_material() against both schemas
# ---------------------------------------------------------------------------

def test_read_material_legacy_unchanged_behavior(legacy_db):
    formula, density = read_material(str(legacy_db), "Silicon")
    assert formula == "Si"
    assert density == 2.329


def test_read_material_legacy_rejects_dataset_label(legacy_db):
    with pytest.raises(ValueError, match="no dataset_label concept"):
        read_material(str(legacy_db), "Silicon", dataset_label="anything")


def test_read_material_oxide_single_no_label_needed(oxide_db_single):
    formula, density = read_material(str(oxide_db_single), "Titanium dioxide (rutile / anatase)")
    assert formula == "TiO2"
    assert density == 4.2362


def test_read_material_oxide_lookup_by_formula_fallback(oxide_db_single):
    """materials.name is a full descriptive name in the oxide dataset; users
    naturally look up by formula instead."""
    formula, density = read_material(str(oxide_db_single), "TiO2")
    assert formula == "TiO2"
    assert density == 4.2362


def test_read_material_not_found(legacy_db):
    with pytest.raises(ValueError, match="not found"):
        read_material(str(legacy_db), "Unobtainium")


# ---------------------------------------------------------------------------
# 2. Selecting a layer by material + dataset_label
# ---------------------------------------------------------------------------

def test_read_material_oxide_ambiguous_without_label(oxide_db_multi):
    with pytest.raises(ValueError, match="Ambiguous.*2 density rows"):
        read_material(str(oxide_db_multi), "Titanium dioxide")


def test_read_material_oxide_disambiguated_by_label(oxide_db_multi):
    formula, density = read_material(str(oxide_db_multi), "Titanium dioxide", dataset_label="rutile")
    assert density == 4.2362

    formula, density = read_material(str(oxide_db_multi), "Titanium dioxide", dataset_label="anatase")
    assert density == 3.8934


def test_read_material_oxide_label_no_match(oxide_db_multi):
    with pytest.raises(ValueError, match="No density found"):
        read_material(str(oxide_db_multi), "Titanium dioxide", dataset_label="brookite")


def test_layer_regex_parses_bracket_syntax():
    cases = {
        "Vacuum": ("Vacuum", None, None),
        "PMMA:120": ("PMMA", None, "120"),
        "TiO2[rutile]:50": ("TiO2", "rutile", "50"),
        "TiO2[rutile | Devore1951 | o-ray]:50": ("TiO2", "rutile | Devore1951 | o-ray", "50"),
        "Silicon": ("Silicon", None, None),
    }
    for entry, (name, label, thickness) in cases.items():
        m = _LAYER_RE.match(entry)
        assert m is not None, entry
        assert m.group("name").strip() == name
        assert m.group("label") == label
        assert m.group("thickness") == thickness


def test_parse_stack_selects_correct_polymorph_by_label(oxide_db_multi):
    layers = parse_stack("Vacuum,TiO2[rutile]:50,TiO2[anatase]:50,Vacuum", str(oxide_db_multi))
    assert layers[1]["density"] == 4.2362
    assert layers[2]["density"] == 3.8934


def test_parse_stack_ambiguous_material_without_label_raises(oxide_db_multi):
    with pytest.raises(ValueError, match="Ambiguous"):
        parse_stack("Vacuum,TiO2:50,Vacuum", str(oxide_db_multi))


# ---------------------------------------------------------------------------
# 3. periodictable-based SLD covers elements the old ATOMS table didn't
# ---------------------------------------------------------------------------

def test_compute_xrr_handles_element_missing_from_old_atoms_table():
    """Bi, Hf, Ta, Nb, etc. weren't in the old 17-element ATOMS dict and
    would raise 'Element(s) not in atomic table'. periodictable covers the
    full periodic table."""
    r = compute_xrr("Bi12GeO20", density_g_cm3=9.2)
    assert r["SLD"] > 0
    assert r["counts"] == {"Bi": 12, "Ge": 1, "O": 20}


def test_compute_xrr_polymer_repeat_unit_formula_normalized():
    """(C5H8O2)n (PMMA's stored formula in materials.db) must not be passed
    to periodictable's strict parser as-is."""
    r = compute_xrr("(C5H8O2)n", density_g_cm3=1.19)
    assert r["counts"] == {"C": 5, "H": 8, "O": 2}
    assert r["SLD"] == pytest.approx(1.0933e-05, rel=0.01)


def test_normalize_formula_leaves_parenthesized_oxide_formulas_alone():
    """LuAl3(BO3)4 is a real, non-polymer formula with internal parens --
    must NOT be treated as a polymer-repeat wrapper (that regex only matches
    when parens wrap the *entire* string)."""
    assert _normalize_formula("LuAl3(BO3)4") == "LuAl3(BO3)4"
    assert _normalize_formula("(C8H8)n") == "C8H8"


def test_compute_xrr_units_are_plain_inverse_angstrom_squared():
    """Regression test for the unit-conversion bug caught during manual
    testing: periodictable.xray_sld() returns units of 1e-6 A^-2, but
    parratt() expects plain A^-2. Known literature SLD values are ~1e-5 to
    ~1e-4 A^-2 for common materials -- if compute_xrr ever returns a value
    ~1e6 too large again, this catches it before it silently breaks the
    critical-angle physics (reflectivity stops decaying at all)."""
    r = compute_xrr("Au", density_g_cm3=19.32)
    assert 1e-5 < r["SLD"] < 2e-4, f"SLD={r['SLD']} is outside the physically sensible A^-2 range"
