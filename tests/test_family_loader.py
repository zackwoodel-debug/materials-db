"""Tests for the family-parameterized loader (scripts/load_family_db.py).

Covers: malformed catalog, duplicate input, ambiguous match, rollback, dry-run,
idempotent rerun, conflict handling (kept both / never overwritten), --strict,
and that the oxide wrapper is still a working thin entry point.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import load_family_db as fam  # noqa: E402

REAL_SELECTIONS = json.loads((ROOT / "data" / "step1_selections.json").read_text())
MGO = REAL_SELECTIONS["MgO"]  # a real, isotropic, single-axis RI.info selection

COLS = ["name", "formula", "polymorph", "inchikey", "density_g_cm3", "density_source", "xray_sld_real"]


def _catalog(tmp_path, rows, cols=COLS, name="cat.csv"):
    p = tmp_path / name
    pd.DataFrame(rows, columns=cols).to_csv(p, index=False)
    return p


def _sel(tmp_path, obj, name="sel.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


def _good_rows():
    return [
        ["Magnesium oxide", "MgO", "periclase", "CPLXHZUBPGIROI-UHFFFAOYSA-N", 3.58, "MP_DFT", 40.0],
        ["Test nitride", "XyN", "wurtzite", "AAAAAAAAAAAAAA-UHFFFAOYSA-N", 5.0, "MP_DFT", 50.0],
    ]


def _good_sel():
    return {"MgO": MGO, "XyN": None}  # XyN: unresolved -> optical skipped


def _counts(db):
    conn = sqlite3.connect(str(db))
    out = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
           for t in ("materials", "physical_properties", "optical_dispersion", "sources")}
    conn.close()
    return out


def _run(tmp_path, db, rows=None, sel=None, **kw):
    cat = _catalog(tmp_path, rows if rows is not None else _good_rows())
    s = _sel(tmp_path, sel if sel is not None else _good_sel())
    return fam.run_family("test", cat, s, db, **kw)


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------- malformed catalog

def test_missing_required_column_rejected(tmp_path):
    cat = _catalog(tmp_path, [["A", 1]], cols=["name", "density_g_cm3"])
    with pytest.raises(fam.CatalogError, match="missing required columns"):
        fam.load_catalog(cat)


def test_empty_and_unreadable_catalog_rejected(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(fam.CatalogError):
        fam.load_catalog(empty)
    header_only = _catalog(tmp_path, [], name="h.csv")
    with pytest.raises(fam.CatalogError, match="no rows"):
        fam.load_catalog(header_only)
    with pytest.raises(fam.CatalogError, match="not found"):
        fam.load_catalog(tmp_path / "nope.csv")


def test_blank_name_rejected(tmp_path):
    cat = _catalog(tmp_path, [["", "MgO", None, None, None, None, None]])
    with pytest.raises(fam.CatalogError, match="blank name"):
        fam.load_catalog(cat)


def test_malformed_selections_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(fam.CatalogError, match="unreadable"):
        fam.load_selections(bad)
    lst = _sel(tmp_path, [1, 2], name="list.json")
    with pytest.raises(fam.CatalogError, match="JSON object"):
        fam.load_selections(lst)


def test_malformed_catalog_leaves_no_db(tmp_path):
    db = tmp_path / "out.db"
    cat = _catalog(tmp_path, [["A", 1]], cols=["name", "x"])
    with pytest.raises(fam.CatalogError):
        fam.run_family("test", cat, _sel(tmp_path, {}), db)
    assert not db.exists()


# ---------------------------------------------------------------- duplicate input

def test_duplicate_name_rejected(tmp_path):
    rows = _good_rows() + [["Magnesium oxide", "MgO2", None, None, None, None, None]]
    with pytest.raises(fam.CatalogError, match="duplicate name"):
        fam.load_catalog(_catalog(tmp_path, rows))


def test_duplicate_formula_needs_distinct_selection_key(tmp_path):
    rows = [["cubic BN", "BN", "cubic", None, None, None, None],
            ["hex BN", "BN", "hexagonal", None, None, None, None]]
    with pytest.raises(fam.CatalogError, match="duplicate selection_key"):
        fam.load_catalog(_catalog(tmp_path, rows))
    cols = COLS + ["selection_key"]
    rows = [r + [k] for r, k in zip(rows, ["BN-c", "BN-h"])]
    df = fam.load_catalog(_catalog(tmp_path, rows, cols=cols, name="k.csv"))
    assert list(df["selection_key"]) == ["BN-c", "BN-h"]


def test_duplicate_inchikey_in_catalog_rejected(tmp_path):
    rows = _good_rows()
    rows[1][3] = rows[0][3]
    with pytest.raises(fam.CatalogError, match="duplicate inchikey"):
        fam.load_catalog(_catalog(tmp_path, rows))


def test_duplicate_inchikey_against_existing_db_does_not_overwrite(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db)
    rows = [["Impostor", "MgO", "periclase", "CPLXHZUBPGIROI-UHFFFAOYSA-N", 9.9, "MP_DFT", 99.0]]
    rep = _run(tmp_path, db, rows=rows, sel={"MgO": MGO})
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM materials WHERE inchikey='CPLXHZUBPGIROI-UHFFFAOYSA-N'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM materials WHERE name='Impostor'").fetchone()[0] == 0
    conn.close()
    assert [c["kind"] for c in rep.conflicts] == ["duplicate_inchikey"]
    assert rep.skipped and rep.skipped[0]["name"] == "Impostor"


# ---------------------------------------------------------------- ambiguous match

@pytest.mark.parametrize("state", ["null", "missing", "candidates_only"])
def test_ambiguous_selection_skips_optical_and_never_auto_picks(tmp_path, state):
    sel = {"MgO": MGO}
    if state == "null":
        sel["XyN"] = None
    elif state == "candidates_only":
        sel["XyN"] = {"candidates": [{"data_path": "main/MgO/x.yml"}, {"data_path": "main/MgO/y.yml"}]}
    db = tmp_path / "out.db"
    rep = _run(tmp_path, db, sel=sel)
    conn = sqlite3.connect(str(db))
    n_opt = conn.execute("SELECT COUNT(*) FROM optical_dispersion o JOIN materials m USING(material_id) "
                         "WHERE m.formula='XyN'").fetchone()[0]
    n_mat = conn.execute("SELECT COUNT(*) FROM materials WHERE formula='XyN'").fetchone()[0]
    conn.close()
    assert n_opt == 0 and n_mat == 1  # material + physical rows still load, optical does not
    assert len(rep.skipped) == 1 and "optical load skipped" in rep.skipped[0]["reason"]


def test_strict_aborts_and_rolls_back_on_ambiguity(tmp_path):
    db = tmp_path / "out.db"
    with pytest.raises(fam.StrictError):
        _run(tmp_path, db, strict=True)
    assert all(v == 0 for v in _counts(db).values())


# ---------------------------------------------------------------- idempotency / conflicts

def test_rerun_adds_zero_logical_rows(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db)
    first = _counts(db)
    assert first["optical_dispersion"] > 0 and first["physical_properties"] > 0
    rep = _run(tmp_path, db)
    assert _counts(db) == first
    assert sum(rep.inserted.values()) == 0
    assert not rep.conflicts


@pytest.mark.parametrize("formula", ["MgAl2O4", "Al2O3"])  # real DOI-less RI.info datasets (1 axis / 2 axes)
def test_rerun_does_not_duplicate_doi_less_sources(tmp_path, formula):
    db = tmp_path / "out.db"
    rows = [["Some oxide", formula, None, None, None, None, None]]
    sel = {formula: REAL_SELECTIONS[formula]}
    _run(tmp_path, db, rows=rows, sel=sel)
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM sources WHERE doi IS NULL AND technique='refractiveindex.info'").fetchone()[0] >= 1
    conn.close()
    first = _counts(db)
    rep = _run(tmp_path, db, rows=rows, sel=sel)
    assert _counts(db) == first and rep.inserted["sources"] == 0


def test_changed_value_keeps_both_and_reports_conflict(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db)
    before = _counts(db)
    rows = _good_rows()
    rows[0][4] = 3.60  # density revised vs. what is already stored
    rep = _run(tmp_path, db, rows=rows)
    after = _counts(db)
    assert after["physical_properties"] == before["physical_properties"] + 1
    assert after["materials"] == before["materials"]
    kinds = [c["kind"] for c in rep.conflicts]
    assert "physical_value" in kinds and rep.conflicts[0]["action"] == "kept both"
    conn = sqlite3.connect(str(db))
    dens = sorted(r[0] for r in conn.execute("SELECT density_g_cm3 FROM physical_properties "
                                             "WHERE density_g_cm3 IS NOT NULL AND dataset_label LIKE 'periclase%'"))
    conn.close()
    assert dens == [3.58, 3.60]


def test_changed_material_field_is_reported_not_overwritten(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db)
    rows = _good_rows()
    rows[0][1] = "MgO2"
    rep = _run(tmp_path, db, rows=rows)
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT formula FROM materials WHERE name='Magnesium oxide'").fetchone()[0] == "MgO"
    conn.close()
    assert any(c["kind"] == "material_field" and c["field"] == "formula" for c in rep.conflicts)


def test_optical_dataset_owned_by_other_material_is_conflict_not_duplicate(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db)
    before = _counts(db)
    rows = [["Magnesium oxide (copy)", "MgO", "periclase", None, None, None, None]]
    rep = _run(tmp_path, db, rows=rows, sel={"MgO": MGO})
    assert _counts(db)["optical_dispersion"] == before["optical_dispersion"]
    assert any(c["kind"] == "optical_dataset" for c in rep.conflicts)


# ---------------------------------------------------------------- rollback

def test_failure_midway_leaves_existing_db_unchanged(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db, rows=_good_rows()[:1], sel={"MgO": MGO})
    before = _counts(db)
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated failure")
        return fam.load_physical_properties(*a, **k)

    rows = _good_rows() + [["Third", "ZzN", None, None, 1.0, "MP_DFT", 1.0]]
    with pytest.raises(RuntimeError, match="simulated failure"):
        _run(tmp_path, db, rows=rows, sel={"MgO": MGO, "XyN": None, "ZzN": None}, load_physical_fn=flaky)
    assert _counts(db) == before


# ---------------------------------------------------------------- dry-run / report

def test_dry_run_writes_nothing_new_db(tmp_path):
    db = tmp_path / "out.db"
    rep = _run(tmp_path, db, dry_run=True)
    assert not db.exists()
    assert rep.inserted["materials"] == 2 and rep.inserted["optical_dispersion"] > 0


def test_dry_run_leaves_existing_db_byte_identical(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db, rows=_good_rows()[:1], sel={"MgO": MGO})
    h = _sha(db)
    rep = _run(tmp_path, db, dry_run=True)
    assert _sha(db) == h
    assert rep.inserted["materials"] == 1  # the new XyN row was evaluated, then rolled back


def test_report_file_written(tmp_path):
    out = tmp_path / "report.json"
    _run(tmp_path, tmp_path / "out.db", report_path=out)
    data = json.loads(out.read_text())
    assert data["family"] == "test" and data["inserted"]["materials"] == 2 and len(data["skipped"]) == 1


def test_fresh_rebuilds_db(tmp_path):
    db = tmp_path / "out.db"
    _run(tmp_path, db)
    _run(tmp_path, db, rows=_good_rows()[:1], sel={"MgO": MGO}, fresh=True)
    assert _counts(db)["materials"] == 1


# ---------------------------------------------------------------- oxide wrapper

def test_oxide_wrapper_still_exposes_legacy_helper_api():
    import load_oxides_db as ox
    for name in ("DB_PATH", "CSV_PATH", "SELECTIONS_PATH", "fresh_db", "main", "load_physical_properties",
                 "load_optical_axis", "get_or_create_source", "parse_ri_references", "label_join",
                 "XRAY_ENERGY_EV", "XRAY_WAVELENGTH_NM", "NEUTRON_WAVELENGTH_NM"):
        assert hasattr(ox, name), name
    assert ox.load_physical_properties is fam.load_physical_properties
