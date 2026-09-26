"""Tests for the glasses family (glass_material_list.py, build_glasses_csv.py, load_glasses_db.py). Optical values are recomputed
by hand from the RI.info files; densities against the datasheet pages; the DURAN and microsphere exclusions re-derived from the
source."""
import json
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
sys.path.insert(0, str(ROOT / "tests"))

import listed_family as bld  # noqa: E402
import glass_material_list as lst  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_glasses_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
CAT = pd.read_csv(DATA / "glasses.csv")
SEL = json.loads((DATA / "step1_selections_glasses.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
PAGES = bld.catalog_pages()
# datasheet / textbook n at 633 nm
N633 = {"N-BK7": 1.5151, "BOROFLOAT33": 1.4700, "D263TECO": 1.5213, "EagleXG": 1.508, "soda-lime": 1.52, "ZBLAN": 1.50}


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("glass") / "materials_glass_test.db"
    rep = fam.run_family("glass", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE,
                         allow_null_formula=True)
    return db, rep


def test_every_listed_page_is_loaded_once_and_labels_are_unique():
    for m in lst.MATERIALS:
        axes = SEL[m["key"]]["axes"]
        assert {a["page"] for a in axes} == {p for _, _, p, _ in m["pages"]}
        assert len({a["dataset_label"] for a in axes}) == len(axes)
    assert list(CAT.selection_key) == [m["key"] for m in lst.MATERIALS] and CAT.formula.isna().all()


def test_exclusions_are_still_true_in_the_source():
    duran = yaml.safe_load(open(RI / "data" / PAGES[("specs", "SCHOTT-misc", "DURAN")][0]))
    wl, n, *_ = fod.parse_file(RI / "data" / PAGES[("specs", "SCHOTT-misc", "DURAN")][0])
    assert len(wl) == 1 and n[0] == pytest.approx(1.473) and duran["PROPERTIES"]["nd"] == pytest.approx(1.527)
    assert "microspheres" in yaml.safe_load(open(RI / "data" / PAGES[("glass", "soda-lime", "Nyakuchena")][0]))["COMMENTS"]


def test_density_is_the_datasheet_value_where_stated_else_null():
    for m in lst.MATERIALS:
        r = CAT.set_index("selection_key").loc[m["key"]]
        if m["density_page"]:
            rho = yaml.safe_load(open(RI / "data" / PAGES[m["density_page"]][0]))["PROPERTIES"]["density"][0]["value"] / 1000
            assert r.density_g_cm3 == pytest.approx(rho) and r.density_source == "literature (manufacturer datasheet)"
        else:
            assert pd.isna(r.density_g_cm3)
        assert pd.isna(r.xray_sld_real) and pd.isna(r.neutron_sld_real)  # no composition, no SLD


def test_primary_n633_is_hand_evaluated_and_matches_the_datasheet():
    for r in CAT.itertuples():
        want = _hand_n(SEL[r.selection_key]["axes"][0]["data_path"])
        assert (want is None) == pd.isna(r.n_633), r.selection_key
        if want is not None:
            assert r.n_633 == pytest.approx(want, abs=1e-6), r.selection_key
        if r.selection_key in N633:
            assert r.n_633 == pytest.approx(N633[r.selection_key], abs=0.003), r.selection_key
    assert SEL["soda-lime"]["axes"][0]["dataset_label"] == "clear window glass | Rubin1985"


def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 11
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES) == 23
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == sum(len(fod.parse_file(RI / "data" / a["data_path"])[0]) for _, a in AXES)
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == sum(1 for m in lst.MATERIALS if m["density_page"])
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE k < 0 OR n <= 0.001").fetchone()[0] == 0
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("glass", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE,
                         allow_null_formula=True)
    assert sum(rep.inserted.values()) == 0 and not rep.conflicts and dump(db) == before


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_every_dataset_is_preserved_row_by_row(loaded, key, axis):
    wl, n, *_ = fod.parse_file(RI / "data" / axis["data_path"])
    c = sqlite3.connect(str(loaded[0]))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(wl) and all(g[0] == i and g[1] == pytest.approx(float(wl[i]), rel=1e-12) and g[2] == pytest.approx(float(n[i]), rel=1e-12) for i, g in enumerate(got))
    if wl.min() <= 633 <= wl.max():
        assert float(np.interp(633.0, wl, n)) == pytest.approx(_hand_n(axis["data_path"]), abs=5e-3)
