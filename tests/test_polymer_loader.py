"""LOADER-DEPENDENT tests for the polymer family (scripts/load_family_db.py + scripts/load_polymers_db.py).

The loader-independent catalog/selection tests live in tests/test_polymer_pipeline.py (those were the PRE-LOAD results).
These cover: NULL-formula handling, deferred-entry skip, idempotent load, the (material, source, dataset_label) dedupe key, the
opt-in formula-vs-tabulated duplicate collapse, and row-by-row preservation of the selected wavelength ranges.
"""
import inspect
import json
import math
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "migration_scripts"))

import load_family_db as fam  # noqa: E402
import load_polymers_db as poly  # noqa: E402
from validate_datasets import validate_optical_material  # noqa: E402

RI = ROOT / "refractiveindex_db" / "database" / "data"
SEL = json.loads((ROOT / "data" / "step1_selections_polymers.json").read_text())
PVP = "organic/(C6H9NO)n - polyvinylpyrrolidone/nk/Konig.yml"
KW = dict(allow_null_formula=True, reference_sources=False, collapse_block_duplicates=True)


def _counts(db):
    c = sqlite3.connect(str(db))
    out = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("materials", "optical_dispersion", "physical_properties", "sources", "chemical_descriptors")}
    c.close()
    return out


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("poly") / "materials_polymer_test.db"
    rep = fam.run_family("polymer", poly.CSV_PATH, poly.SELECTIONS_PATH, db, fresh=True, **KW)
    return db, rep


def _mini(tmp_path, rows, sel):
    cat = tmp_path / "c.csv"
    pd.DataFrame(rows).to_csv(cat, index=False)
    s = tmp_path / "s.json"
    s.write_text(json.dumps(sel))
    return cat, s


def _pvp_sel():
    return {"PVP": SEL["PVP"]}


# ---------------------------------------------------------------- NULL formula

def test_null_formula_is_rejected_by_default_and_accepted_only_with_the_opt_in(tmp_path):
    cat, s = _mini(tmp_path, [dict(name="Grade X", formula=None, selection_key="GX")], {})
    with pytest.raises(fam.CatalogError, match="blank formula|missing required"):
        fam.run_family("oxide", cat, s, tmp_path / "a.db")
    db = tmp_path / "b.db"
    fam.run_family("polymer", cat, s, db, allow_null_formula=True, reference_sources=False)
    c = sqlite3.connect(str(db))
    assert c.execute("SELECT formula FROM materials WHERE name='Grade X'").fetchone() == (None,)  # NULL, never 'nan' or a token
    c.close()


def test_null_formula_still_needs_a_name_and_a_selection_key(tmp_path):
    cat, s = _mini(tmp_path, [dict(name="", formula=None, selection_key="K")], {})
    with pytest.raises(fam.CatalogError, match="blank name"):
        fam.load_catalog(cat, allow_null_formula=True)
    cat, s = _mini(tmp_path, [dict(name="No key", formula=None)], {})
    with pytest.raises(fam.CatalogError, match="selection_key"):
        fam.load_catalog(cat, allow_null_formula=True)


def test_polymer_catalog_loads_null_formula_only_for_the_twelve_grade_materials(loaded):
    c = sqlite3.connect(str(loaded[0]))
    nulls = {r[0] for r in c.execute("SELECT name FROM materials WHERE formula IS NULL")}
    assert nulls == set(pd.read_csv(poly.CSV_PATH).query("formula != formula")["name"])  # NaN rows == NULL rows
    assert len(nulls) == 12 and c.execute("SELECT COUNT(*) FROM materials WHERE lower(coalesce(formula,'x')) IN ('nan','none','unspecified','')").fetchone()[0] == 0
    c.close()


# ---------------------------------------------------------------- deferred

DEFER = dict(selection=None, deferred=True, reason="synthetic deferral for this test")


def test_deferred_entry_produces_zero_rows_and_is_reported_not_warned(tmp_path):
    sel = dict(_pvp_sel(), DEFERRED_X=DEFER)
    cat, s = _mini(tmp_path, [dict(name="Polyvinylpyrrolidone", formula="(C6H9NO)n", selection_key="PVP"),
                              dict(name="Deferred X", formula="(CH2)n", selection_key="DEFERRED_X")], sel)
    db = tmp_path / "d.db"
    rep = fam.run_family("polymer", cat, s, db, strict=True, **KW)  # strict must NOT fail on a deferral
    c = sqlite3.connect(str(db))
    assert c.execute("SELECT COUNT(*) FROM materials WHERE name='Deferred X'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion o JOIN materials m USING(material_id) WHERE m.name='Deferred X'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 1
    c.close()
    assert [d["key"] for d in rep.deferred] == ["DEFERRED_X"] and rep.deferred[0]["in_catalog"] and not rep.warnings and not rep.skipped


def test_deferred_keys_absent_from_the_catalog_are_recorded_without_a_warning(tmp_path):
    cat, s = _mini(tmp_path, [dict(name="Polyvinylpyrrolidone", formula="(C6H9NO)n", selection_key="PVP")],
                   dict(_pvp_sel(), A=DEFER, B=DEFER))
    rep = fam.run_family("polymer", cat, s, tmp_path / "e.db", strict=True, **KW)
    assert sorted((d["key"], d["in_catalog"]) for d in rep.deferred) == [("A", False), ("B", False)] and rep.warnings == []


def test_the_real_polymer_load_defers_nothing(loaded):
    assert loaded[1].deferred == [] and loaded[1].warnings == []


# ---------------------------------------------------------------- idempotency and the dedupe key

def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion")}
    before = dump(db)
    rep = fam.run_family("polymer", poly.CSV_PATH, poly.SELECTIONS_PATH, db, **KW)  # no fresh: upsert
    assert sum(rep.inserted.values()) == 0 and not rep.conflicts and dump(db) == before


def test_dedupe_key_material_source_label_blocks_the_same_dataset_from_a_different_file(tmp_path):
    db = tmp_path / "k.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(fam.SCHEMA_PATH.read_text())
    mid = conn.execute("INSERT INTO materials(name) VALUES('Poly X')").lastrowid
    sid = conn.execute("INSERT INTO sources(title, technique) VALUES('S','refractiveindex.info')").lastrowid
    rep = fam.Report("t")
    a1 = dict(data_path="organic/(C16H14O3)n - polycarbonate/nk/Zhang.yml", dataset_label="Same2020")
    a2 = dict(data_path="organic/(C8H8)n - polystyrene/nk/Zhang.yml", dataset_label="Same2020")
    n1 = fam.load_optical_axis(conn, mid, sid, a1, None, rep)
    before = conn.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0]
    n2 = fam.load_optical_axis(conn, mid, sid, a2, None, rep)  # different data file, same (material, source, label)
    assert n1 > 0 and n2 == 0 and conn.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == before
    assert [c["kind"] for c in rep.conflicts] == ["optical_duplicate_key"] and rep.conflicts[0]["action"].startswith("not inserted")
    # a different label (or a different source) is a different dataset and is allowed
    assert fam.load_optical_axis(conn, mid, sid, dict(a2, dataset_label="Other2020"), None, rep) > 0
    conn.close()


# ---------------------------------------------------------------- collapse of formula-vs-tabulated duplicates (opt-in)

def _load_pvp(tmp_path, collapse):
    conn = sqlite3.connect(str(tmp_path / f"p{collapse}.db"))
    conn.executescript(fam.SCHEMA_PATH.read_text())
    mid = conn.execute("INSERT INTO materials(name) VALUES('PVP')").lastrowid
    sid = conn.execute("INSERT INTO sources(title, technique) VALUES('S','refractiveindex.info')").lastrowid
    rep = fam.Report("t")
    fam.load_optical_axis(conn, mid, sid, dict(data_path=PVP, dataset_label="Konig2014"), None, rep, collapse_block_duplicates_flag=collapse)
    return conn, rep


def test_collapse_is_off_by_default_so_other_families_keep_their_rows(tmp_path):
    d = {k: v.default for k, v in inspect.signature(fam.run_family).parameters.items()}
    assert d["collapse_block_duplicates"] is False and d["allow_null_formula"] is False and d["reference_sources"] is True
    conn, rep = _load_pvp(tmp_path, collapse=False)
    dups = conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY wavelength_nm HAVING COUNT(*)>1)").fetchone()[0]
    assert dups == 2 and rep.collapsed == [] and conn.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == 526


def test_collapse_keeps_the_tabulated_row_and_reports_every_drop_with_both_n_values(tmp_path):
    conn, rep = _load_pvp(tmp_path, collapse=True)
    assert conn.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == 524
    assert conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY wavelength_nm HAVING COUNT(*)>1)").fetchone()[0] == 0
    table = {}
    for b in yaml.safe_load(open(RI / PVP))["DATA"]:
        if b["type"] == "tabulated nk":
            table = {round(float(l.split()[0]) * 1000, 6): float(l.split()[1]) for l in b["data"].strip().splitlines()}
    assert sorted(c["wavelength_nm"] for c in rep.collapsed) == [375.0, 1000.0]
    for c in rep.collapsed:
        kept = conn.execute("SELECT n FROM optical_dispersion WHERE wavelength_nm=?", (c["wavelength_nm"],)).fetchone()[0]
        assert kept == pytest.approx(table[c["wavelength_nm"]], abs=1e-12) == pytest.approx(c["kept_n"], abs=1e-12)  # source's own tabulated n
        assert c["kept"] == "tabulated" and c["dropped"] == "formula-sampled" and abs(c["delta_n"]) < 1e-4
        assert c["dropped_n"] != c["kept_n"] and set(c) >= {"kept_n", "dropped_n", "delta_n", "dropped_raw_record_id"}


def test_collapse_never_guesses_when_the_tabulated_row_cannot_be_identified(tmp_path, monkeypatch):
    wl = np.array([500.0, 600.0, 600.0, 700.0])
    n = np.array([1.50, 1.55, 1.56, 1.60])  # duplicate at 600 nm, but no source table value matches either row
    monkeypatch.setattr(fam, "parse_file", lambda p: (wl, n, None, "", None))
    conn = sqlite3.connect(str(tmp_path / "u.db"))
    conn.executescript(fam.SCHEMA_PATH.read_text())
    mid = conn.execute("INSERT INTO materials(name) VALUES('X')").lastrowid
    sid = conn.execute("INSERT INTO sources(title) VALUES('S')").lastrowid
    rep = fam.Report("t")
    fam.load_optical_axis(conn, mid, sid, dict(data_path=PVP, dataset_label="L"), None, rep, collapse_block_duplicates_flag=True)
    assert conn.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == 4  # nothing dropped
    assert rep.collapsed == [] and [w["kind"] for w in rep.warnings] == ["unresolved_duplicate_wavelength"]


# ---------------------------------------------------------------- the real 14 / 14 load

def test_real_load_facts_and_scope(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 39
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == 45
    expected = sum(len(fam.parse_file(RI / a["data_path"])[0]) for v in SEL.values() if "axes" in v for a in v["axes"]) - len(rep.collapsed)
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == expected
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == [] and len(rep.collapsed) == 2  # only the two PVP boundary rows
    names = {r[0] for r in c.execute("SELECT name FROM materials")}
    assert {"Polyetherimide (PEI)", "Poly(D-lactic acid) (PDLA)", "Poly(methyl methacrylate) (Tomson)", "Poly(methyl methacrylate) (Mitsubishi)",
            "Polydimethylsiloxane (Dow Corning, 10:1 mass ratio)", "Kapton HN (polyimide film)", "Linear low-density polyethylene (LLDPE)"} <= names
    assert not any("CR-39" in n or "Hydroxypropyl" in n or "1:1 mixture" in n or "(uncured)" in n.lower() for n in names)
    lab = lambda nm: {r[0] for r in c.execute("SELECT DISTINCT dataset_label FROM optical_dispersion o JOIN materials m USING(material_id) WHERE m.name=?", (nm,))}
    assert lab("Polycarbonate") == {"Zhang2020"} and lab("Polystyrene") == {"Zhang2020"} and lab("F8BT") == {"Kamptner2024 | o-ray", "Kamptner2024 | e-ray"}
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion o JOIN materials m USING(material_id) WHERE m.name='Polyvinyl alcohol' AND o.dataset_label != 'Schnepf2017'").fetchone()[0] == 0
    c.close()


def test_density_sld_descriptors_and_reference_sources_stay_empty(loaded):
    c = sqlite3.connect(str(loaded[0]))
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == 0  # no density, no SLD, no fallback densities
    assert c.execute("SELECT COUNT(*) FROM chemical_descriptors").fetchone()[0] == 0
    assert not [r for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%descriptor%' AND name!='chemical_descriptors'")]
    assert c.execute("SELECT COUNT(*) FROM sources WHERE technique != 'refractiveindex.info'").fetchone()[0] == 0  # no MP/PubChem/periodictable phantoms
    assert "grade" not in [r[1] for r in c.execute("PRAGMA table_info(materials)")]
    c.close()


def test_reference_sources_off_refuses_a_catalog_that_carries_density(tmp_path):
    cat, s = _mini(tmp_path, [dict(name="Dense", formula="(CH2)n", selection_key="D", density_g_cm3=0.95)], {})
    with pytest.raises(fam.CatalogError, match="reference_sources=False"):
        fam.run_family("polymer", cat, s, tmp_path / "x.db", allow_null_formula=True, reference_sources=False)


def test_every_optical_row_is_valid_and_carries_label_and_source(loaded):
    c = sqlite3.connect(str(loaded[0]))
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE dataset_label IS NULL OR dataset_label='' OR source_id IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label, wavelength_nm HAVING COUNT(*)>1)").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, source_id, dataset_label HAVING COUNT(DISTINCT raw_record_table)>1)").fetchone()[0] == 0
    for n, k, wl in c.execute("SELECT n, k, wavelength_nm FROM optical_dispersion"):
        assert n is not None and math.isfinite(n) and n >= 0 and wl > 0 and (k is None or math.isfinite(k))
    c.close()


AXES = [(k, a) for k, v in SEL.items() if "axes" in v for a in v["axes"]]


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_selected_wavelength_range_is_preserved_row_by_row(loaded, key, axis):
    db, rep = loaded
    fam_wl, fam_n, *_ = fam.parse_file(RI / axis["data_path"])
    dropped = {c["dropped_raw_record_id"] for c in rep.collapsed if c["data_path"] == axis["data_path"]}
    exp = [(i, float(fam_wl[i]), float(fam_n[i])) for i in range(len(fam_wl)) if i not in dropped]
    c = sqlite3.connect(str(db))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(exp) and got[0][1] == float(fam_wl.min()) and got[-1][1] == float(fam_wl.max())
    assert all(e[0] == g[0] and e[1] == pytest.approx(g[1], rel=1e-12) and e[2] == pytest.approx(g[2], rel=1e-12) for e, g in zip(exp, got))
    assert got[-1][1] < 2_000_000.0  # the loader window is unchanged and nothing needs it wider


# ---------------------------------------------------------------- self-pair detector (validate_datasets.py, on scratch copies only)

def test_no_self_pairs_in_the_polymer_db_and_the_detector_really_detects_them(loaded, tmp_path):
    db = tmp_path / "v.db"
    shutil.copy(loaded[0], db)
    c = sqlite3.connect(str(db))
    ids = [r[0] for r in c.execute("SELECT material_id FROM materials")]
    pairs = sum(validate_optical_material(c, i) for i in ids)
    assert pairs == 6  # only the six conjugated polymers have two datasets (o- and e-ray of one film): a genuine pair each
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE pearson_r >= 0.999999").fetchone()[0] == 0  # distinct axes, never identical
    assert {r[0] for r in c.execute("SELECT DISTINCT dataset_a || ' / ' || dataset_b FROM dataset_validation")} == {"Kamptner2024 | e-ray / Kamptner2024 | o-ray"}
    pc = c.execute("SELECT material_id FROM materials WHERE name='Polycarbonate'").fetchone()[0]
    c.execute("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) "
              "SELECT material_id,wavelength_nm,n,k,'DUP-CONTROL','ctrl/'||raw_record_table,raw_record_id,source_id FROM optical_dispersion WHERE material_id=?", (pc,))
    validate_optical_material(c, pc)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE pearson_r >= 0.999999").fetchone()[0] == 1  # negative control
    c.close()