"""Tests for the halide family (match_ri_info_halides.py, build_halides_csv.py, load_halides_db.py) and RI.info formula 8.

Every optical value and every SLD is recomputed independently at test time (hand evaluation of the RI.info formulas; periodictable directly).
"""
import json
import math
import re
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

import halide_material_list as lst  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_halides_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from validate_datasets import validate_optical_material  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database" / "data"
CAT = pd.read_csv(DATA / "halides.csv")
GAPS = pd.read_csv(DATA / "halide_gaps.csv")
SEL = json.loads((DATA / "step1_selections_halides.json").read_text())
MATCHES = {c["key"]: c for c in json.loads((DATA / "halide_ri_matches.json").read_text())["candidates"]}
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
MULTI = {"KCl": 2, "NaCl": 2, "AgBr": 2, "CsBr": 3, "TlBr": 2, "CsI": 3, "NaI": 2}


def _hand_n(path, lam_um=0.633):
    """n at lam from the YAML, independent of parse_file (RI.info formulas written from their published definitions)."""
    for b in yaml.safe_load(open(RI / path))["DATA"]:
        t = b["type"]
        if t.startswith("formula"):
            lo, hi = [float(x) for x in b["wavelength_range"].split()]
            if not lo <= lam_um <= hi:
                continue
            c, l2 = [float(x) for x in b["coefficients"].split()], lam_um ** 2
            if t == "formula 1":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1] ** 2) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 4":
                n2 = c[0]
                if len(c) >= 5:
                    n2 += c[1] * lam_um ** c[2] / (l2 - c[3] ** c[4])
                if len(c) >= 9:
                    n2 += c[5] * lam_um ** c[6] / (l2 - c[7] ** c[8])
                return (n2 + sum(c[i] * lam_um ** c[i + 1] for i in range(9, len(c) - 1, 2))) ** 0.5
            if t == "formula 8":  # Lorentz-Lorenz form: (n^2-1)/(n^2+2) = c0 + c1 l^2/(l^2-c2) + c3 l^2
                x = c[0] + c[1] * l2 / (l2 - c[2]) + c[3] * l2
                return ((1 + 2 * x) / (1 - x)) ** 0.5
            raise AssertionError(f"unsupported formula type {t}")
        rows = [[float(x) for x in ln.split()] for ln in b["data"].strip().splitlines()]
        if rows[0][0] <= lam_um <= rows[-1][0]:
            return float(np.interp(lam_um, [r[0] for r in rows], [r[1] for r in rows]))
    return None


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("hal") / "materials_halide_test.db"
    rep = fam.run_family("halide", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    return db, rep


# ---------------------------------------------------------------- formula 8 (new evaluator)

def test_formula8_matches_the_published_form_and_an_independent_paper_for_agbr():
    """AgBr has Schroter 1931 (formula 8) and Polyanskiy 2024 (Sellmeier) as separate papers: two independent measurements must agree."""
    lam = np.array([0.5, 0.55, 0.6, 0.633, 0.65])
    by = {a["page"]: a for a in SEL["AgBr"]["axes"]}
    f8 = yaml.safe_load(open(RI / by["Schröter"]["data_path"]))["DATA"][0]
    f1 = yaml.safe_load(open(RI / by["Polyanskiy"]["data_path"]))["DATA"][0]
    assert f8["type"] == "formula 8"
    n8, _ = fod.eval_formula(f8, lam)
    assert n8 == pytest.approx([_hand_n(by["Schröter"]["data_path"], x) for x in lam], rel=1e-12)
    assert n8 == pytest.approx(fod.eval_formula(f1, lam)[0], abs=1e-3)


def test_formula8_tlcl_sodium_d_index_is_the_published_textbook_value():
    b = yaml.safe_load(open(RI / SEL["TlCl"]["axes"][0]["data_path"]))["DATA"][0]
    assert fod.eval_formula(b, np.array([0.5893]))[0][0] == pytest.approx(2.25, abs=0.03)  # TlCl n_D ~2.25


# ---------------------------------------------------------------- catalog, selections, gaps

def test_catalog_is_21_halides_and_out_of_family_stay_out():
    assert len(CAT) == 21 and CAT["formula"].is_unique and CAT["selection_key"].is_unique and set(CAT["materialclass"]) == {"halide"}
    assert not set(lst.OUT_OF_FAMILY) & set(CAT["selection_key"])
    out = GAPS[GAPS["gap_kind"] == "out_of_family"]
    assert set(out["key"]) == {"LiIO3", "MoOCl2"} and out["reason"].notna().all()
    assert len(GAPS) == 2, "every halide has a density, so the only gap rows are the two out-of-family books"


def test_selections_none_null_and_multi_paper_materials_keep_every_paper():
    assert all(v is not None for v in SEL.values()) and len(SEL) == 21 and len(AXES) == 30
    for k, v in SEL.items():
        labels = [a["dataset_label"] for a in v["axes"]]
        assert len(labels) == len(set(labels)) == MULTI.get(k, 1), k
        spans = [a["span_um"][1] - a["span_um"][0] for a in v["axes"]]
        assert spans == sorted(spans, reverse=True), f"{k}: primary must be the widest span"
    assert {k for k, m in MATCHES.items() if m["n_papers"] > 1} == set(MULTI)


def test_every_selected_page_exists_and_has_a_dispersion_type_the_pipeline_supports():
    for _, a in AXES:
        for b in yaml.safe_load(open(RI / a["data_path"]))["DATA"]:
            assert b["type"] in {"tabulated nk", "tabulated n", "formula 1", "formula 4", "formula 8"}, a["page"]


# ---------------------------------------------------------------- density and SLD rules

AMBIENT = {"rock-salt (Fm-3m)": 225, "CsCl-type (Pm-3m)": 221, "zincblende (F-43m)": 216, "CdI2-type 2H (P-3m1)": 164}
# textbook densities (g/cm3, experiment) as a coarse sanity bound on the DFT value: catches a wrong-phase pick (wurtzite Li halides, rock-salt CsI)
TEXTBOOK_RHO = {"AgCl": 5.56, "CsCl": 3.99, "CuCl": 4.14, "KCl": 1.98, "LiCl": 2.07, "NaCl": 2.17, "RbCl": 2.80, "TlCl": 7.0, "AgBr": 6.47,
                "CsBr": 4.44, "KBr": 2.75, "LiBr": 3.46, "NaBr": 3.21, "RbBr": 3.35, "TlBr": 7.56, "CsI": 4.51, "KI": 3.12, "LiI": 4.08,
                "NaI": 3.67, "RbI": 3.55, "PbI2": 6.16}


def test_every_halide_has_a_calculated_mp_density_of_its_ambient_structure_and_it_is_labelled():
    assert CAT["density_g_cm3"].notna().all() and (CAT["density_source"] == "MP_DFT").all() and CAT["mp_id"].notna().all()
    for r in CAT.itertuples():
        assert AMBIENT[r.polymorph] == lst.AMBIENT_STRUCTURE[r.selection_key][1]
        assert f"#{AMBIENT[r.polymorph]}" in r.mp_space_group, r.formula
        assert "calculated, not measured" in r.flags and "not stated on the RI.info page" in r.flags


def test_wrong_phase_picks_are_gone_and_densities_are_within_12pct_of_textbook():
    for r in CAT.itertuples():
        assert abs(r.density_g_cm3 / TEXTBOOK_RHO[r.formula] - 1) < 0.12, (r.formula, r.density_g_cm3)
    assert CAT[CAT.formula == "LiCl"].iloc[0]["density_g_cm3"] == pytest.approx(2.14, abs=0.01)  # not the theoretical wurtzite 1.66
    assert CAT[CAT.formula == "CsI"].iloc[0]["polymorph"].startswith("CsCl-type")                 # not the DFT-lowest rock-salt 3.62


def test_csv_sld_equals_an_independent_periodictable_recompute():
    import periodictable as pt
    for r in CAT.itertuples():
        fm = pt.formula(r.formula)
        xr, xi = pt.xray_sld(fm, density=r.density_g_cm3, energy=8.048)
        nr, ni, _ = pt.neutron_sld(fm, density=r.density_g_cm3)
        assert (r.xray_sld_real, r.xray_sld_imag, r.neutron_sld_real, r.neutron_sld_imag) == pytest.approx((xr, xi, nr, ni), rel=1e-6), r.formula


def test_csv_n633_matches_hand_evaluation_of_the_primary_and_disagreements_are_flagged():
    for r in CAT.itertuples():
        a = SEL[r.selection_key]["axes"][0]
        want = _hand_n(a["data_path"])
        assert (want is None) == pd.isna(r.n_633), r.formula
        if want is not None:
            assert r.n_633 == pytest.approx(want, abs=1e-6), r.formula  # exact formula value, not the sampled grid
        for extra in SEL[r.selection_key]["axes"][1:]:
            assert f"additional source {extra['dataset_label']}" in r.flags
    tlbr = CAT[CAT.formula == "TlBr"].iloc[0]["flags"]
    assert "SOURCES DISAGREE" in tlbr and "Palik1985" in tlbr and "Schroter1931" in tlbr
    assert "SOURCES DISAGREE" not in CAT[CAT.formula == "NaCl"].iloc[0]["flags"]


# ---------------------------------------------------------------- the loaded DB

def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 21
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == 30
    expected = sum(len(fod.parse_file(RI / a["data_path"])[0]) for _, a in AXES)
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == expected
    assert rep.skipped == [] and rep.conflicts == []
    assert c.execute("SELECT COUNT(*) FROM chemical_descriptors").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE dataset_label IS NULL OR dataset_label='' OR source_id IS NULL").fetchone()[0] == 0
    # the ONE repeated wavelength is a byte-identical line in RI.info's KCl Querry file (1.1600 1.490 0.000 twice); kept as in the source, not collapsed
    dups = c.execute("SELECT m.formula, o.dataset_label, o.wavelength_nm, COUNT(*), COUNT(DISTINCT o.n), COUNT(DISTINCT COALESCE(o.k,-1)) FROM optical_dispersion o "
                     "JOIN materials m USING(material_id) GROUP BY o.material_id, o.dataset_label, o.wavelength_nm HAVING COUNT(*)>1").fetchall()
    assert dups == [("KCl", "Querry1987", 1160.0, 2, 1, 1)]
    for n, k, wl in c.execute("SELECT n, k, wavelength_nm FROM optical_dispersion"):
        assert n is not None and math.isfinite(n) and n > 1e-3 and wl > 0 and (k is None or math.isfinite(k))
    c.close()


def test_physical_rows_one_block_per_material_each_citing_a_source(loaded):
    c = sqlite3.connect(str(loaded[0]))
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == 5 * 21
    assert c.execute("SELECT COUNT(*) FROM physical_properties WHERE source_id IS NULL").fetchone()[0] == 0
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("halide", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    assert sum(rep.inserted.values()) == 0 and not rep.conflicts and dump(db) == before


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_every_dataset_is_preserved_row_by_row_and_n633_agrees_three_ways(loaded, key, axis):
    wl, n, *_ = fod.parse_file(RI / axis["data_path"])
    c = sqlite3.connect(str(loaded[0]))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(wl) and all(g[0] == i and g[1] == pytest.approx(float(wl[i]), rel=1e-12) and g[2] == pytest.approx(float(n[i]), rel=1e-12) for i, g in enumerate(got))
    hand = _hand_n(axis["data_path"])
    if wl.min() <= 633 <= wl.max():
        assert hand is not None and float(np.interp(633.0, wl, n)) == pytest.approx(hand, abs=5e-3)  # DB == parse_file == hand, up to the 500-point sampling of wide-range formulas (TlBr Palik 0.57-39 um: 3e-3)
    else:
        assert hand is None


def test_validation_finds_no_self_pairs_and_detects_a_planted_duplicate(loaded, tmp_path):
    db = tmp_path / "v.db"
    shutil.copy(loaded[0], db)
    c = sqlite3.connect(str(db))
    for (mid,) in c.execute("SELECT material_id FROM materials").fetchall():
        validate_optical_material(c, mid)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE pearson_r >= 0.999999").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE rmse < 1e-9").fetchone()[0] == 0
    kb = c.execute("SELECT material_id FROM materials WHERE formula='KBr'").fetchone()[0]
    c.execute("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) "
              "SELECT material_id,wavelength_nm,n,k,'DUP-CONTROL','ctrl/'||raw_record_table,raw_record_id,source_id FROM optical_dispersion WHERE material_id=?", (kb,))
    validate_optical_material(c, kb)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE pearson_r >= 0.999999").fetchone()[0] >= 1
    c.close()
