"""materials_db.core.invariants: every FAIL invariant catches a planted violation (in a minimal, unconstrained database, so the
check's own logic is exercised, not just the schema's NOT NULLs), a clean database passes, the newest local release passes every
FAIL invariant, and docs/INVARIANTS.md is generated from the registry."""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from materials_db.core import invariants as inv  # noqa: E402

DDL = """
CREATE TABLE materials (material_id INTEGER, name TEXT, formula TEXT);
CREATE TABLE sources (source_id INTEGER, doi TEXT, url TEXT, title TEXT);
CREATE TABLE optical_dispersion (material_id INTEGER, wavelength_nm REAL, n REAL, k REAL, dataset_label TEXT, source_id INTEGER);
CREATE TABLE physical_properties (material_id INTEGER, density_g_cm3 REAL, dataset_label TEXT, source_id INTEGER);
"""
ALLOWED = {("Glass", "noisy | Smith2020"): -0.01}


def _clean_db():
    con = sqlite3.connect(":memory:")
    con.executescript(DDL)
    con.executescript("""
        INSERT INTO materials VALUES (1, 'Glass', NULL), (2, 'Gold', 'Au');
        INSERT INTO sources VALUES (1, '10.1/x', NULL, 'Paper'), (2, NULL, 'https://example.org', 'Datasheet');
        INSERT INTO optical_dispersion VALUES (1, 500, 1.5, 0, 'Smith2020', 1), (1, 600, 1.49, -0.005, 'noisy | Smith2020', 1),
                                              (2, 500, 0.97, 1.87, 'Jones1999', 2);
        INSERT INTO physical_properties VALUES (2, 19.3, 'fcc | density_MP_DFT', 2), (1, 2.5, 'density_literature', 1);
    """)
    return con


def _failing(con):
    return {i.name for i, _ in inv.failures(inv.evaluate(con, "release", dict(negative_k_allowed=ALLOWED)))}


def test_a_clean_database_passes():
    assert _failing(_clean_db()) == set()


@pytest.mark.parametrize("name, plant", [
    ("optical_rows_have_a_source", "UPDATE optical_dispersion SET source_id = NULL WHERE wavelength_nm = 500 AND material_id = 1"),
    ("physical_rows_have_a_source", "UPDATE physical_properties SET source_id = NULL WHERE material_id = 2"),
    ("optical_sources_exist", "UPDATE optical_dispersion SET source_id = 99 WHERE material_id = 2"),
    ("physical_sources_exist", "UPDATE physical_properties SET source_id = 99 WHERE material_id = 1"),
    ("density_has_a_known_state", "UPDATE physical_properties SET dataset_label = 'density_guess' WHERE material_id = 1"),
    ("n_is_positive_and_finite", "UPDATE optical_dispersion SET n = -1 WHERE material_id = 2"),
    ("n_is_positive_and_finite", "UPDATE optical_dispersion SET n = NULL WHERE material_id = 2"),
    ("negative_k_only_where_reviewed", "UPDATE optical_dispersion SET k = -0.2 WHERE dataset_label = 'noisy | Smith2020'"),
    ("negative_k_only_where_reviewed", "UPDATE optical_dispersion SET k = -1e-6 WHERE material_id = 2"),
    ("wavelength_is_positive_and_finite", "UPDATE optical_dispersion SET wavelength_nm = 0 WHERE material_id = 2"),
    ("material_ids_are_unique", "INSERT INTO materials VALUES (2, 'Gold 2', 'Au')"),
    ("material_names_are_unique_after_normalization", "INSERT INTO materials VALUES (3, ' gold ', 'Au')"),
])
def test_each_fail_invariant_catches_its_violation(name, plant):
    con = _clean_db()
    con.execute(plant)
    assert name in _failing(con)


def test_warn_invariants_report_without_failing():
    con = _clean_db()
    con.execute("INSERT INTO sources VALUES (3, NULL, NULL, 'Handbook')")
    results = inv.evaluate(con, "release", dict(negative_k_allowed=ALLOWED))
    assert inv.failures(results) == []
    assert inv.summary(results)["sources_have_a_locator"] == dict(severity="WARN", holds=False, violations=1,
                                                                 example="source 3 has neither DOI nor URL: 'Handbook'")


def test_every_invariant_has_a_name_rationale_and_known_severity():
    names = [i.name for i in inv.INVARIANTS]
    assert len(names) == len(set(names))
    assert all(i.rationale and i.severity in (inv.FAIL, inv.WARN) and i.scope in ("release", "legacy") for i in inv.INVARIANTS)


def test_legacy_database_is_evaluated_and_only_warns():
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'materials.db'}?mode=ro", uri=True)
    results = inv.evaluate(con, "legacy")
    assert inv.failures(results) == [] and results  # the unsourced legacy rows are reported (WARN), never a release blocker


def test_invariants_md_is_generated_from_the_registry():
    import write_invariants_md
    assert (ROOT / "docs" / "INVARIANTS.md").read_text() == write_invariants_md.render(), "run: python3 scripts/write_invariants_md.py"


def test_newest_local_release_passes_every_fail_invariant():
    from materials_db.access import AccessError, find_release
    try:
        _, sqlite_path = find_release()
    except AccessError:
        pytest.skip("no release built locally")
    import build_release as br
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    assert inv.failures(inv.evaluate(con, "release", dict(negative_k_allowed=br.NEGATIVE_K_ALLOWED))) == []
