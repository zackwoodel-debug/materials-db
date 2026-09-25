"""Cross-family sanity battery on every family's optical rows: n finite and strictly positive (> 1e-3), wavelength finite and > 0, k finite.

Why 1e-3: the formula evaluators floor n^2 at 1e-30 (n ~ 1e-15) where a fit goes negative outside its validity range; the schema trigger only
rejects n < 0, so such a floored row would load silently. No loaded row does today (smallest n is 0.061, a metal), and this keeps it that way.
Negative k does exist in three tabulated sources (measurement noise around zero); it is pinned by name, so a new one must be looked at.
"""
import math
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

N_MIN = 1e-3
NEGATIVE_K_ALLOWED = {  # (material name, dataset_label) -> most negative k accepted
    ("Copper(I) oxide", "cuprite | Querry1985"): -0.03,
    ("Hematite", "hematite | Querry1985 | o-ray"): -0.15,
    ("Micro resist ma-N 1407 (negative resist)", "Sarkar2019"): -0.03,
}
FAMILY_WRAPPERS = {"nitride": "load_nitrides_db", "polymer": "load_polymers_db", "inorganic3": "load_inorganic3_db", "halide": "load_halides_db"}


def optical_violations(conn):
    """Human-readable list of every optical row breaking the battery (empty = clean)."""
    bad = []
    q = ("SELECT m.name, o.dataset_label, o.wavelength_nm, o.n, o.k FROM optical_dispersion o JOIN materials m USING(material_id)")
    for name, label, wl, n, k in conn.execute(q):
        if n is None or not math.isfinite(n) or n <= N_MIN:
            bad.append(f"{name} | {label} | {wl} nm: n={n} (must be finite and > {N_MIN})")
        if wl is None or not math.isfinite(wl) or wl <= 0:
            bad.append(f"{name} | {label}: wavelength_nm={wl}")
        if k is not None and not math.isfinite(k):
            bad.append(f"{name} | {label} | {wl} nm: k={k}")
        elif k is not None and k < 0 and k < NEGATIVE_K_ALLOWED.get((name, label), 0.0):
            bad.append(f"{name} | {label} | {wl} nm: k={k} is negative and this dataset is not in the pinned allow-list")
    return bad


@pytest.fixture(scope="module")
def family_dbs(tmp_path_factory):
    dbs = {"oxide": ROOT / "data" / "materials_oxide_test.db"}  # tracked (135 materials)
    for fam, modname in FAMILY_WRAPPERS.items():
        mod = __import__(modname)
        db = tmp_path_factory.mktemp(fam) / f"{fam}.db"
        old, mod.DB_PATH = mod.DB_PATH, db
        try:
            mod.main()
        finally:
            mod.DB_PATH = old
        dbs[fam] = db
    return dbs


@pytest.mark.parametrize("fam", ["oxide", "nitride", "polymer", "inorganic3", "halide"])
def test_family_has_no_floored_nonphysical_or_unexplained_negative_optical_rows(family_dbs, fam):
    conn = sqlite3.connect(f"{Path(family_dbs[fam]).as_uri()}?mode=ro", uri=True)
    assert conn.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] > 1000
    assert optical_violations(conn) == []
    conn.close()


def test_the_pinned_negative_k_datasets_really_exist_so_the_allow_list_cannot_go_stale(family_dbs):
    seen = set()
    for db in family_dbs.values():
        c = sqlite3.connect(f"{Path(db).as_uri()}?mode=ro", uri=True)
        seen |= set(c.execute("SELECT m.name, o.dataset_label FROM optical_dispersion o JOIN materials m USING(material_id) WHERE o.k < 0"))
        c.close()
    assert seen == set(NEGATIVE_K_ALLOWED)


@pytest.mark.parametrize("bad_n", [1e-15, 0.0, 5e-4, float("inf"), None])
def test_battery_catches_a_floored_or_nonphysical_n(tmp_path, bad_n):
    """Negative control: plant one bad row into a copy of a real DB; the battery must name it."""
    import shutil
    db = tmp_path / "c.db"
    shutil.copy(Path(__file__).resolve().parents[1] / "data" / "materials_oxide_test.db", db)
    conn = sqlite3.connect(str(db))
    conn.execute("DROP TRIGGER IF EXISTS trg_optical_check_ins")
    row = conn.execute("SELECT material_id, dataset_label, raw_record_table, source_id FROM optical_dispersion LIMIT 1").fetchone()
    conn.execute("INSERT INTO optical_dispersion(material_id, wavelength_nm, n, k, dataset_label, raw_record_table, raw_record_id, source_id) "
                 "VALUES (?, 41000.0, ?, 0.0, ?, ?, -1, ?)", (row[0], bad_n, row[1], row[2], row[3]))
    found = optical_violations(conn)
    assert len(found) == 1 and "41000.0 nm" in found[0]
    conn.close()


@pytest.mark.parametrize("bad_k", [-0.5, float("inf")])
def test_battery_catches_a_new_negative_k_and_a_nonfinite_k(tmp_path, bad_k):
    """(SQLite stores NaN as NULL, so infinity is the non-finite value that can actually be persisted.)"""
    import shutil
    db = tmp_path / "c.db"
    shutil.copy(ROOT / "data" / "materials_oxide_test.db", db)
    conn = sqlite3.connect(str(db))
    mid, label, tab, src = conn.execute("SELECT material_id, dataset_label, raw_record_table, source_id FROM optical_dispersion LIMIT 1").fetchone()
    conn.execute("INSERT INTO optical_dispersion(material_id, wavelength_nm, n, k, dataset_label, raw_record_table, raw_record_id, source_id) "
                 "VALUES (?, 50000.0, 2.0, ?, ?, ?, -1, ?)", (mid, bad_k, label, tab, src))
    found = optical_violations(conn)
    assert len(found) == 1 and "50000.0 nm" in found[0]
    conn.close()
