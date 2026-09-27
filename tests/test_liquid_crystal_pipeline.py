"""Tests for the liquid-crystal family (liquid_crystal_material_list.py, build_liquid_crystals_csv.py via listed_family.py,
load_liquid_crystals_db.py). Independent checks: hand evaluation of every RI.info formula; every o/e pair of one source and
temperature has n_e > n_o (positive nematics); the Wu 1993 series lie below each compound's clearing point and n_e falls with
temperature; the excluded 5CB page is re-derived as a duplicate from the source; 5CB / 5PCH identity against PubChem's formula."""
import json
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
sys.path.insert(0, str(ROOT / "tests"))

import listed_family  # noqa: E402
import liquid_crystal_material_list as lst  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_liquid_crystals_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
CAT = pd.read_csv(DATA / "liquid_crystals.csv").set_index("selection_key")
SEL = json.loads((DATA / "step1_selections_liquid_crystals.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
PAGES = listed_family.catalog_pages()
CLEARING_C = {"5CB": 35.0, "5PCH": 54.0}  # nematic-isotropic transition


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("lc") / "materials_liquid_crystal_test.db"
    rep = fam.run_family("liquid_crystal", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE,
                         allow_null_formula=True)
    return db, rep


def test_every_page_of_every_book_is_loaded_or_excluded():
    for m in lst.MATERIALS:
        book = m["pages"][0]["book"]
        on_ri = {p for (sh, b, p) in PAGES if sh == "other" and b == book}
        loaded = {a["page"] for a in SEL[m["key"]]["axes"]}
        excluded = {p for (sh, b, p) in lst.EXCLUDED_PAGES if b == book}
        assert loaded | excluded == on_ri and not loaded & excluded, book


def test_the_excluded_5cb_page_duplicates_the_29_9_degc_page():
    page = lambda p: yaml.safe_load(open(RI / "data" / PAGES[("other", "5CB", p)][0]))
    dup, ref = page("Wu-27.2C-e"), page("Wu-29.9C-e")
    assert [b["coefficients"] for b in dup["DATA"]] == [b["coefficients"] for b in ref["DATA"]]
    assert "29.9" in dup["COMMENTS"] and dup["CONDITIONS"]["temperature"] == pytest.approx(300.35)  # says 27.2 degC, holds 29.9 degC data
    assert [b["coefficients"] for b in page("Wu-27.2C-o")["DATA"]] != [b["coefficients"] for b in page("Wu-29.9C-o")["DATA"]]


def test_positive_birefringence_for_every_o_e_pair():
    for key, v in SEL.items():
        by = {}
        for a in v["axes"]:
            by.setdefault(a["tag"], {})[a["axis"]] = _hand_n(a["data_path"], 0.6)
        pairs = [(t, d) for t, d in by.items() if {"o-ray", "e-ray"} <= set(d)]
        assert pairs and all(d["e-ray"] > d["o-ray"] + 0.02 for _, d in pairs), key


def test_temperature_series_are_nematic_labelled_and_n_e_falls_on_heating():
    for key, clearing in CLEARING_C.items():
        wu = [a for a in SEL[key]["axes"] if a["tag"].startswith("Wu1993-")]
        assert all(a["temperature_c"] < clearing and a["tag"] == f"Wu1993-{a['temperature_c']:.1f}C" for a in wu), key
        ne = sorted((a["temperature_c"], _hand_n(a["data_path"], 0.6)) for a in wu if a["axis"] == "e-ray")
        assert all(b[1] < a[1] for a, b in zip(ne, ne[1:])), (key, ne)


def test_identity_of_the_two_compounds_and_mixtures_have_no_formula():
    assert CAT.at["5CB", "formula"] == "C18H19N" and int(CAT.at["5CB", "pubchem_cid"]) == 92319
    assert CAT.at["5PCH", "formula"] == "C18H25N" and int(CAT.at["5PCH", "pubchem_cid"]) == 109063
    assert CAT[CAT.materialclass == "liquid crystal mixture"].formula.isna().all() and (CAT.materialclass == "liquid crystal mixture").sum() == 7


def test_primary_n633_is_hand_evaluated():
    for key, r in CAT.iterrows():
        assert r.n_633 == pytest.approx(_hand_n(SEL[key]["axes"][0]["data_path"]), abs=1e-6), key


def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 9
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES) == 45
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    for k, a in AXES:  # every stated temperature is on its rows
        if a["temperature_c"] is not None:
            (t,), = c.execute("SELECT DISTINCT temperature_c FROM optical_dispersion WHERE raw_record_table=?", (a["data_path"],)).fetchall()
            assert t == pytest.approx(a["temperature_c"], abs=0.2), (k, a["page"])
    c.close()


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_every_dataset_is_preserved_row_by_row(loaded, key, axis):
    wl, n, *_ = fod.parse_file(RI / "data" / axis["data_path"])
    c = sqlite3.connect(str(loaded[0]))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(wl) and all(g[0] == i and g[1] == pytest.approx(float(wl[i]), rel=1e-12) and g[2] == pytest.approx(float(n[i]), rel=1e-12) for i, g in enumerate(got))
    if wl.min() <= 633 <= wl.max():
        assert float(np.interp(633.0, wl, n)) == pytest.approx(_hand_n(axis["data_path"]), abs=5e-3)
