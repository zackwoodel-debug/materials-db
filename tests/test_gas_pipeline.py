"""Tests for the gas family (gas_material_list.py, build_gases_csv.py via listed_family.py, load_gases_db.py). Independent
checks: the pressure in every label equals the page's stated CONDITIONS; at 633 nm n-1 follows atomic polarizability
(He < Ne < H2 < Ar < Kr < Xe); three independent standard-air formulations agree; condensed rare gases have n far above the gas;
the Martonchik methane exclusion is re-derived from the source."""
import json
import re
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

import gas_material_list as lst  # noqa: E402
import listed_family  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_gases_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
CAT = pd.read_csv(DATA / "gases.csv").set_index("selection_key")
SEL = json.loads((DATA / "step1_selections_gases.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
PAGES = listed_family.catalog_pages()


def n633(key, label):
    return _hand_n(next(a["data_path"] for a in SEL[key]["axes"] if a["dataset_label"] == label))


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("gas") / "materials_gas_test.db"
    rep = fam.run_family("gas", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE,
                         allow_null_formula=True)
    return db, rep


def test_every_page_of_every_book_is_loaded_or_excluded():
    for m in lst.MATERIALS:
        shelf, book = m["pages"][0]["shelf"], m["pages"][0]["book"]
        on_ri = {p for (sh, b, p) in PAGES if (sh, b) == (shelf, book)}
        excluded = {p for (sh, b, p) in lst.EXCLUDED_PAGES if (sh, b) == (shelf, book)}
        assert {a["page"] for a in SEL[m["key"]]["axes"]} | excluded == on_ri, book


def test_pressure_in_every_label_is_the_stated_one():
    for k, a in AXES:
        cond = yaml.safe_load(open(RI / "data" / a["data_path"])).get("CONDITIONS") or {}
        v = a["phase"]
        if v in ("liquid", "solid"):
            assert f"{v} " in PAGES[(a["shelf"], a["book"], a["page"])][1].lower() + " ", (k, a["page"])
        elif v.endswith("101.325 kPa"):
            assert cond.get("pressure") == 101325 or "760" in a["comments"], (k, a["page"])
        elif v.endswith("100 kPa"):
            assert cond.get("pressure") == 100000, (k, a["page"])
        else:
            assert v == "gas" and "pressure" not in cond, (k, a["page"])


def test_primary_is_a_gas_at_stated_conditions():
    for key, v in SEL.items():
        first = v["axes"][0]
        stated = [a for a in v["axes"] if re.search(r"kPa$", a["phase"])]
        if stated:
            assert first["phase"].endswith("kPa"), key


def test_polarizability_ordering_of_n_minus_1():
    order = [(k, n633(k, f"gas, 100 kPa | Borzsonyi2008")) for k in ("He", "Ne", "Ar", "Kr", "Xe")]
    assert all(a[1] < b[1] for a, b in zip(order, order[1:])), order
    assert n633("He", "gas, 100 kPa | Borzsonyi2008") < n633("H2", "gas, 101.325 kPa | Peck1977") < n633("Ar", "gas, 100 kPa | Borzsonyi2008")


def test_three_standard_air_formulations_agree():
    std = [n633("Air", f"dry air (450 ppm CO2), 101.325 kPa | {t}") for t in ("Ciddor1996", "Birch1994", "Peck1972")]
    assert max(std) - min(std) < 1e-7 and std[0] - 1 == pytest.approx(2.765e-4, rel=2e-3)


def test_condensed_rare_gases_are_far_denser_optically():
    for key in ("Ar", "Kr", "Xe"):
        gas = n633(key, "gas, 100 kPa | Borzsonyi2008")
        liquid = [_hand_n(a["data_path"], 0.6) for a in SEL[key]["axes"] if a["phase"] == "liquid"]
        assert liquid and min(liquid) > 1.2 > gas, key


def test_martonchik_methane_exclusion_is_still_true():
    for p in ("Martonchik-liquid-111K", "Martonchik-liquid-90K"):
        path, title = PAGES[("organic", "methane", p)]
        c = yaml.safe_load(open(RI / "data" / path))["COMMENTS"]
        assert "Liquid" in title and "solid methane" in c and "don't rely on interpolated" in c


def test_identity():
    assert {k: int(CAT.at[k, "pubchem_cid"]) for k in ("N2", "Ar", "CO2", "CH4")} == {"N2": 947, "Ar": 23968, "CO2": 280, "CH4": 297}
    assert pd.isna(CAT.at["Air", "formula"]) and pd.isna(CAT.at["D2", "pubchem_cid"])  # PubChem writes D2 as H2: left empty


def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 18
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES)
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    for k, a in AXES:
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
