"""Tests for the compound-semiconductor family (match_ri_info_semiconductors.py, build_semiconductors_csv.py, load_semiconductors_db.py).

Optical values are recomputed independently (hand evaluation of the RI.info files, shared with the chalcogenide tests) and SLDs with
periodictable directly. The film exclusions are re-derived from the RI.info page text, so they fail if the source changes.
"""
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
sys.path.insert(0, str(ROOT / "tests"))

import load_family_db as fam  # noqa: E402
import load_semiconductors_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import semiconductor_material_list as lst  # noqa: E402
from match_ri_info_semiconductors import AMBIENT_C, ambient  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database" / "data"
CAT = pd.read_csv(DATA / "semiconductors.csv")
GAPS = pd.read_csv(DATA / "semiconductor_gaps.csv")
SEL = json.loads((DATA / "step1_selections_semiconductors.json").read_text())
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
MATCHES = {c["key"]: c for c in json.loads((DATA / "semiconductor_ri_matches.json").read_text())["candidates"]}
# handbook densities (g/cm3, 300 K); MP's PBE densities run a few percent low (lattice constants overestimated)
TEXTBOOK_RHO = {"AlAs": 3.76, "AlSb": 4.26, "BP": 2.97, "GaAs": 5.32, "GaP": 4.14, "GaSb": 5.61, "InAs": 5.67, "InP": 4.81, "InSb": 5.78,
                "CdTe": 5.85, "ZnTe": 5.64, "PbTe": 8.16, "CdGeAs2": 5.60, "CdGeP2": 4.55, "ZnGeP2": 4.17, "ZnSiAs2": 4.70}


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("semi") / "materials_semiconductor_test.db"
    rep = fam.run_family("semiconductor", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    return db, rep


# ---------------------------------------------------------------- scope

def test_catalog_is_the_16_candidates_and_nothing_deferred_or_out_of_family_leaks_in():
    assert list(CAT.selection_key) == [c["key"] for c in lst.CANDIDATES] and len(CAT) == 16
    assert set(CAT.selection_key).isdisjoint(set(lst.DEFERRED) | set(lst.OUT_OF_FAMILY))
    assert set(GAPS.key) == set(lst.DEFERRED) | {k for k, _ in lst.EXCLUDED_PAGES} | set(lst.OUT_OF_FAMILY)


def test_none_is_already_in_an_earlier_family():
    earlier = set()
    for stem in ["oxides_50", "batch2_31", "batch3b_4", "pure_elements_50", "nitrides", "inorganic3", "halides", "chalcogenides", "liquids"]:
        earlier |= set(pd.read_csv(DATA / f"{stem}.csv").formula.dropna())
    assert set(CAT.formula).isdisjoint(earlier)


def test_excluded_film_pages_still_describe_films_in_the_source_and_are_not_loaded():
    for (key, page), _why in lst.EXCLUDED_PAGES.items():
        path = next(d["data_path"] for d in MATCHES[key]["datasets"] if d["page"] == page)
        comments = yaml.safe_load(open(RI / path)).get("COMMENTS", "")
        assert "film" in comments.lower(), (key, page)
        assert page not in {a["page"] for a in SEL[key]["axes"]}


def test_selections_complete_labels_unique_and_every_listed_page_loaded():
    for c in lst.CANDIDATES:
        axes = SEL[c["key"]]["axes"]
        labels = [a["dataset_label"] for a in axes]
        assert len(labels) == len(set(labels)), c["key"]
        if c["page_polymorph"]:
            assert {a["page"] for a in axes} == set(c["page_polymorph"]), c["key"]


# ---------------------------------------------------------------- temperature and the primary dataset

def test_primary_is_ambient_measured_then_widest_covering_633_nm():
    from dataset_kind import is_model_fit
    for k, v in SEL.items():
        first, axes = v["axes"][0], v["axes"]
        assert ambient(first), k
        pool = [a for a in axes if ambient(a) and not is_model_fit(a["data_path"])] or [a for a in axes if ambient(a)]
        assert first in pool, k
        covering = [a for a in pool if a["span_um"][0] <= 0.633 <= a["span_um"][1]] or pool
        assert first in covering and (first["span_um"][1] - first["span_um"][0]) == max(a["span_um"][1] - a["span_um"][0] for a in covering), k
    # the III-V primaries are the Aspnes & Studna ellipsometry, not Adachi's model (NOTES #10)
    assert {k: SEL[k]["axes"][0]["tag"] for k in ("GaSb", "InAs", "InP", "InSb")} == dict.fromkeys(("GaSb", "InAs", "InP", "InSb"), "Aspnes1983")


def test_temperature_series_carry_their_stated_temperature():
    t = {(k, a["page"]): a["temperature_c"] for k, a in AXES}
    assert t[("GaAs", "Gadras")] == pytest.approx(600, abs=0.2) and t[("AlAs", "Gadras")] == pytest.approx(600, abs=0.2)
    assert [t[("GaAs", f"Franta-{x}K")] for x in (300, 370, 440)] == pytest.approx([26.85, 96.85, 166.85])
    assert [t[("CdTe", f"DeBell-{x}K")] for x in (300, 80, 20)] == pytest.approx([26.85, -193.15, -253.15])
    assert [t[("ZnGeP2", f"Ghosh-{x}K-o")] for x in (100, 500)] == pytest.approx([-173.15, 226.85])
    assert not ambient(dict(temperature_c=AMBIENT_C[1] + 1)) and ambient(dict(temperature_c=None))


def test_different_temperatures_are_never_reported_as_source_disagreement():
    import build_oxides_csv as base
    hot_or_cold = {a["dataset_label"] for _, a in AXES if not ambient(a)}
    disagree = [f for r in CAT.itertuples() for f in r.flags.split(base.FLAG_JOIN) if f.startswith("SOURCES DISAGREE")]
    assert disagree and not [f for f in disagree for lab in hot_or_cold if f" vs {lab} " in f]
    gadras = next(f for f in CAT.set_index("formula").at["GaAs", "flags"].split(base.FLAG_JOIN) if "Gadras2025" in f)
    assert "not compared: different temperature" in gadras


def test_every_selected_page_has_a_supported_type_and_no_nonphysical_formula_value_in_range():
    for k, a in AXES:
        for b in yaml.safe_load(open(RI / a["data_path"]))["DATA"]:
            assert b["type"] in {"tabulated nk", "tabulated n", "tabulated k", "formula 1", "formula 2", "formula 4"}, a["page"]
            if b["type"].startswith("formula"):
                lo, hi = (float(x) for x in b["wavelength_range"].split())
                n, _ = fod.eval_formula(b, np.geomspace(lo, hi, 20000))
                assert n.min() > 1e-3, (k, a["page"])


# ---------------------------------------------------------------- density and SLD

def test_density_is_the_mp_entry_of_the_ambient_structure_and_near_the_handbook_value():
    for r in CAT.itertuples():
        _, sg, _ = lst.AMBIENT_STRUCTURE[r.selection_key]
        assert r.density_source == "MP_DFT" and f"(#{sg})" in r.mp_space_group, r.formula
        assert -0.08 < (r.density_g_cm3 - TEXTBOOK_RHO[r.formula]) / TEXTBOOK_RHO[r.formula] < 0.02, r.formula


def test_csv_sld_equals_an_independent_periodictable_recompute():
    import periodictable as pt
    for r in CAT.itertuples():
        fm = pt.formula(r.formula)
        xr, xi = pt.xray_sld(fm, density=r.density_g_cm3, energy=8.048)
        nr, ni, _ = pt.neutron_sld(fm, density=r.density_g_cm3)
        assert (r.xray_sld_real, r.xray_sld_imag, r.neutron_sld_real, r.neutron_sld_imag) == pytest.approx((xr, xi, nr, ni), rel=1e-6), r.formula


# ---------------------------------------------------------------- n(633 nm)

def test_csv_n633_is_the_hand_evaluated_primary_page():
    for r in CAT.itertuples():
        want = _hand_n(SEL[r.selection_key]["axes"][0]["data_path"])
        assert (want is None) == pd.isna(r.n_633), r.formula
        if want is not None:
            assert r.n_633 == pytest.approx(want, abs=1e-6), r.formula


def test_ellipsometry_references_are_loaded_next_to_the_primary_model_fits():
    """Aspnes & Studna 1983 (ellipsometry) is the reference n at 633 nm for the III-Vs; it must be loaded as its own dataset."""
    for key, n_ref in {"GaAs": 3.857, "InP": 3.536, "GaP": 3.318, "InSb": 4.290, "GaSb": 5.164, "InAs": 3.964}.items():
        asp = next(a for a in SEL[key]["axes"] if a["page"] == "Aspnes")
        assert _hand_n(asp["data_path"]) == pytest.approx(n_ref, abs=2e-3), key


# ---------------------------------------------------------------- loaded database

def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 16
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES)
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == sum(len(fod.parse_file(RI / a["data_path"])[0]) for _, a in AXES)
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == 5 * 16
    neg = c.execute("SELECT DISTINCT m.name, o.dataset_label FROM optical_dispersion o JOIN materials m USING(material_id) WHERE o.k < 0").fetchall()
    assert neg == [("Gallium phosphide", "Jellison1992")]  # noise around k = 0, allow-listed in build_release and the sanity test
    c.close()


def test_non_ambient_rows_carry_their_temperature(loaded):
    c = sqlite3.connect(str(loaded[0]))
    for k, a in AXES:
        if not ambient(a):
            temps = {t for (t,) in c.execute("SELECT DISTINCT temperature_c FROM optical_dispersion WHERE raw_record_table=?", (a["data_path"],))}
            assert len(temps) == 1 and next(iter(temps)) == pytest.approx(a["temperature_c"], abs=0.2), (k, a["page"], temps)
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("semiconductor", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    assert sum(rep.inserted.values()) == 0 and not rep.conflicts and dump(db) == before


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_every_dataset_is_preserved_row_by_row_and_n633_agrees_with_hand_evaluation(loaded, key, axis):
    wl, n, *_ = fod.parse_file(RI / axis["data_path"])
    c = sqlite3.connect(str(loaded[0]))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(wl) and all(g[0] == i and g[1] == pytest.approx(float(wl[i]), rel=1e-12) and g[2] == pytest.approx(float(n[i]), rel=1e-12) for i, g in enumerate(got))
    hand = _hand_n(axis["data_path"])
    if wl.min() <= 633 <= wl.max():
        assert hand is not None and float(np.interp(633.0, wl, n)) == pytest.approx(hand, abs=5e-3)
    else:
        assert hand is None or not math.isfinite(hand) or wl.min() > 633 or wl.max() < 633
