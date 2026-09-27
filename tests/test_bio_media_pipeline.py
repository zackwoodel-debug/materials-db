"""Tests for the biological-media family (bio_media_material_list.py, build_bio_media_csv.py via listed_family.py,
load_bio_media_db.py). Independent physics check: dissolved solutes raise the refractive index of water, so at 633 nm
water < PBS < DMEM and serum / plasma > PBS (10% FBS within 0.002 of plain DMEM). Tissues lie in the physiological range. The glycerol-mixture deferral and
its source error are re-derived from the source."""
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

import bio_media_material_list as lst  # noqa: E402
import listed_family  # noqa: E402
import load_bio_media_db as wrap  # noqa: E402
import load_family_db as fam  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
CAT = pd.read_csv(DATA / "bio_media.csv").set_index("selection_key")
SEL = json.loads((DATA / "step1_selections_bio_media.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
PAGES = listed_family.catalog_pages()
N = {(k, a["phase"]): _hand_n(a["data_path"]) for k, a in AXES if a["page"].startswith("Barroso") or a["page"].startswith("Liu")}


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("bio") / "materials_bio_media_test.db"
    rep = fam.run_family("bio_media", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE,
                         allow_null_formula=True)
    return db, rep


def test_every_page_of_every_book_is_loaded():
    for m in lst.MATERIALS:
        for book in {p["book"] for p in m["pages"]}:
            on_ri = {p for (sh, b, p) in PAGES if sh == "other" and b == book}
            assert {a["page"] for a in SEL[m["key"]]["axes"] if a["book"] == book} == on_ri, book


def test_solutes_raise_the_index_of_water():
    water = _hand_n("main/H2O/nk/Daimon-21.5C.yml")
    pbs, dmem, dmem_fbs = N[("PBS", "DPBS")], N[("DMEM", "DMEM")], N[("DMEM", "DMEM + 10% FBS")]
    assert water < pbs < dmem  # large solute steps
    assert N[("blood", "serum")] > pbs and N[("blood", "plasma")] > pbs
    # 10% FBS should add ~+0.001, but the source reads 0.001 LOWER than plain DMEM: separate samples, within measurement
    # uncertainty; recorded, not corrected
    assert abs(dmem_fbs - dmem) < 0.002


def test_tissues_and_fluids_are_in_the_physiological_range():
    for key, r in CAT.iterrows():
        if not pd.isna(r.n_633):
            assert 1.33 < r.n_633 < 1.50, key


def test_the_liu_whole_blood_caveat_is_recorded_and_still_true():
    liu = yaml.safe_load(open(RI / "data" / PAGES[("other", "blood", "Liu")][0]))
    assert "omitted" in liu["COMMENTS"] and [b["type"] for b in liu["DATA"]] == ["formula 2"]
    assert N[("blood", "whole blood")] < 1.36  # below typical whole blood (~1.38-1.40), close to serum / plasma
    assert "CAUTION" in CAT.at["blood", "flags"] and "1.348" in CAT.at["blood", "flags"]


def test_glycerol_mixture_deferral_and_its_source_error():
    for page, stated in (("Sarkar-50", "50"), ("Sarkar-75", "75")):
        path, title = PAGES[("other", "D2O-C3H5_OH_3", page)]
        assert f"{stated} wt%" in title and "25 wt% glycerol" in yaml.safe_load(open(RI / "data" / path))["COMMENTS"]
    assert not any("glycerol" in a["data_path"].lower() and "C3H5" in a["data_path"] for _, a in AXES)


def test_primary_n633_is_hand_evaluated():
    for key, r in CAT.iterrows():
        want = _hand_n(SEL[key]["axes"][0]["data_path"])
        assert (want is None) == pd.isna(r.n_633), key
        if want is not None:
            assert r.n_633 == pytest.approx(want, abs=1e-6), key


def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 6
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES) == 15
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    neg = c.execute("SELECT DISTINCT dataset_label FROM optical_dispersion WHERE k < 0").fetchall()
    assert neg == [("whole blood | Rowe2017",)]  # FTIR noise around k = 0, allow-listed in build_release and the sanity test
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
