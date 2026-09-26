"""Tests for inorganic batch 4 (match_ri_info_inorganic4.py, build_inorganic4_csv.py, load_inorganic4_db.py): the phosphate and
sulfate crystals. Optical values are recomputed by hand from the RI.info files and SLDs with periodictable directly; the ZrO2
deferral and the n2-only books are re-derived from the source."""
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

import inorganic4_material_list as lst  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_inorganic4_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from dataset_kind import is_model_fit  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
CAT = pd.read_csv(DATA / "inorganic4.csv")
SEL = json.loads((DATA / "step1_selections_inorganic4.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
TEXTBOOK_RHO = {"AlPO4": 2.62, "CaSO4": 2.97, "KH2PO4": 2.34, "NH4H2PO4": 1.80, "KTiOPO4": 3.02, "RbTiOPO4": 3.60}
TEXTBOOK_N633 = {"AlPO4": 1.52, "KH2PO4": 1.51, "NH4H2PO4": 1.52, "KTiOPO4": 1.76, "RbTiOPO4": 1.78}  # ordinary / alpha


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("i4") / "materials_inorganic4_test.db"
    rep = fam.run_family("inorganic4", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    return db, rep


def test_catalog_is_the_six_crystals_and_nothing_deferred_leaks_in():
    assert list(CAT.selection_key) == [c["key"] for c in lst.CANDIDATES]
    assert set(CAT.selection_key).isdisjoint(set(lst.DEFERRED) | set(lst.OUT_OF_FAMILY))


def test_zro2_deferral_reasons_are_still_true_in_the_source():
    book = next(b for e in yaml.safe_load(open(RI / "catalog-nk.yml")) if e.get("SHELF") == "main"
                for b in e.get("content", []) if b.get("BOOK") == "ZrO2")
    path = {p["PAGE"]: p["data"] for p in book["content"] if p.get("data")}
    pages = {p: yaml.safe_load(open(RI / "data" / path[p])) for p in ("Wood", "Synowicki", "Bodurov")}
    import re
    assert "Y2O3" in re.sub(r"<[^>]+>", "", pages["Wood"]["COMMENTS"]) and "mixed crystals/ZrO2-Y2O3" in path["Wood"]
    assert is_model_fit(path["Synowicki"])
    assert "nanoparticles" in pages["Bodurov"]["COMMENTS"].lower()


def test_books_named_in_the_docstring_hold_only_nonlinear_n2_data():
    nk = open(RI / "catalog-nk.yml").read()
    for book in ("CaO", "SrO", "Ga2O3", "Er2O3", "Gd3Ga5O12", "YAlO3", "KTiOAsO4"):
        assert f"BOOK: {book}\n" not in nk, book
        assert list((RI / "data" / "main" / book).glob("n2/*.yml")), book


def test_density_is_the_ambient_structure_and_near_the_handbook_value():
    for r in CAT.itertuples():
        assert r.density_source == "MP_DFT" and f"(#{lst.AMBIENT_STRUCTURE[r.selection_key][1]})" in r.mp_space_group, r.formula
        assert abs(r.density_g_cm3 - TEXTBOOK_RHO[r.formula]) / TEXTBOOK_RHO[r.formula] < 0.05, r.formula


def test_csv_sld_equals_an_independent_periodictable_recompute():
    import periodictable as pt
    for r in CAT.itertuples():
        fm = pt.formula(r.formula)
        xr, xi = pt.xray_sld(fm, density=r.density_g_cm3, energy=8.048)
        nr, ni, _ = pt.neutron_sld(fm, density=r.density_g_cm3)
        assert (r.xray_sld_real, r.xray_sld_imag, r.neutron_sld_real, r.neutron_sld_imag) == pytest.approx((xr, xi, nr, ni), rel=1e-6), r.formula


def test_csv_n633_is_the_hand_evaluated_primary_page_and_near_the_handbook_value():
    for r in CAT.itertuples():
        want = _hand_n(SEL[r.selection_key]["axes"][0]["data_path"])
        assert (want is None) == pd.isna(r.n_633), r.formula
        if want is not None:
            assert r.n_633 == pytest.approx(want, abs=1e-6) and r.n_633 == pytest.approx(TEXTBOOK_N633[r.formula], abs=0.02), r.formula


def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 6
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES) == 15
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == sum(len(fod.parse_file(RI / "data" / a["data_path"])[0]) for _, a in AXES)
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE k < 0 OR n <= 0.001").fetchone()[0] == 0
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("inorganic4", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
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
