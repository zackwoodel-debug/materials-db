"""Tests for the optical-media family (optical_media_material_list.py, build_optical_media_csv.py via listed_family.py,
load_optical_media_db.py). Independent checks: each Cargille matching liquid's n(633 nm) equals the material it is made to match
(taken from the other families' own data), densities equal the datasheet pages, and the uncured / cure-unstated / k-only
exclusions are re-derived from the source."""
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
import load_family_db as fam  # noqa: E402
import load_optical_media_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import optical_media_material_list as lst  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
CAT = pd.read_csv(DATA / "optical_media.csv").set_index("selection_key")
SEL = json.loads((DATA / "step1_selections_optical_media.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
PAGES = listed_family.catalog_pages()


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("om") / "materials_optical_media_test.db"
    rep = fam.run_family("optical_media", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE,
                         allow_null_formula=True)
    return db, rep


def test_matching_liquids_match_their_target_materials():
    glass = pd.read_csv(DATA / "glasses.csv").set_index("selection_key")
    silica = _hand_n("main/SiO2/nk/Malitson.yml")                    # fused silica (the amorphous SiO2 dataset)
    pmma_grades = [_hand_n(f"organic/(C5H8O2)n - poly(methyl methacrylate)/nk/Zhang-{g}.yml") for g in ("Tomson", "Mitsubishi")]
    assert CAT.at["Cargille-BK7", "n_633"] == pytest.approx(glass.at["N-BK7", "n_633"], abs=5e-4)
    for k in ("Cargille-06350", "Cargille-50350"):
        assert CAT.at[k, "n_633"] == pytest.approx(silica, abs=5e-4), k
    # acrylic: bulk PMMA differs by supplier (Zhang 2020: Tomson 1.4830, Mitsubishi 1.4908 at 633 nm); the liquid sits between them
    assert min(pmma_grades) < CAT.at["Cargille-acrylic", "n_633"] < max(pmma_grades)


def test_density_is_the_datasheet_value_at_its_temperature():
    for m in lst.MATERIALS:
        r = CAT.loc[m["key"]]
        if m["density_page"]:
            rho = yaml.safe_load(open(RI / "data" / PAGES[m["density_page"]][0]))["PROPERTIES"]["density"][0]
            assert r.density_g_cm3 == pytest.approx(rho["value"] / 1000) and r.density_temperature_c == pytest.approx(rho["temperature"] - 273.15)
        else:
            assert pd.isna(r.density_g_cm3)
        assert pd.isna(r.formula) and pd.isna(r.xray_sld_real)


def test_exclusions_are_still_true_in_the_source():
    joseph = yaml.safe_load(open(RI / "data" / PAGES[("other", "Norland_NOA-61", "Joseph")][0]))
    assert "uncured" in (str(joseph.get("COMMENTS")) + PAGES[("other", "Norland_NOA-61", "Joseph")][1]).lower()
    assert "cured" in PAGES[("other", "Norland_NOA-61", "Norland")][1].lower()
    for book in ("Loctite-3526", "Norland_NOA-170", "Norland_NOA-1348"):
        c = str(yaml.safe_load(open(RI / "data" / PAGES[("other", book, "Iezzi")][0])).get("COMMENTS")).lower()
        assert "film" in c and "cured" not in c, book  # cure state not stated: deferred
    for book in ("Leica_Type_F", "Olympus_IMMOIL-F30CC", "Sigma_Aldrich_M5904"):
        types = [b["type"] for b in yaml.safe_load(open(RI / "data" / PAGES[("other", book, "Wang")][0]))["DATA"]]
        assert types == ["tabulated k"], book  # k only: nothing to load


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
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 8
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == sum(len(fod.parse_file(RI / "data" / a["data_path"])[0]) for _, a in AXES)
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    assert c.execute("SELECT COUNT(*) FROM physical_properties WHERE temperature_c IS NULL").fetchone()[0] == 0  # Cargille densities at 25 degC
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE k < 0 OR n <= 0.001").fetchone()[0] == 0
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
