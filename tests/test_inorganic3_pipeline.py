"""Tests for the inorganic batch-3 family (match_ri_info_inorganic3.py, build_inorganic3_csv.py, load_inorganic3_db.py).

Catalog/selection/gap tests need no DB; the loaded-DB tests build a throwaway DB with the standard loader (no special flags).
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

import inorganic3_material_list as lst  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_inorganic3_db as wrap  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from validate_datasets import validate_optical_material  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database" / "data"
CAT = pd.read_csv(DATA / "inorganic3.csv")
GAPS = pd.read_csv(DATA / "inorganic3_gaps.csv")
SEL = json.loads((DATA / "step1_selections_inorganic3.json").read_text())
MATCHES = {c["key"]: c for c in json.loads((DATA / "inorganic3_ri_matches.json").read_text())["candidates"]}
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
NO_DENSITY = {"VC", "ScAlMgO4", "Bi4Ti3O12", "CaWO4"}


def _hand_n(path, lam_um=0.633):
    """n at lam from the YAML, independent of parse_file (RI.info formulas 1-5 written from their published definitions)."""
    for b in yaml.safe_load(open(RI / path))["DATA"]:
        t = b["type"]
        if t.startswith("formula"):
            lo, hi = [float(x) for x in b["wavelength_range"].split()]
            if not lo <= lam_um <= hi:
                continue
            c, l2 = [float(x) for x in b["coefficients"].split()], lam_um ** 2
            if t == "formula 1":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1] ** 2) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 2":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1]) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 3":
                return (c[0] + sum(c[i] * lam_um ** c[i + 1] for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 4":  # exactly two resonance groups, then 2-coefficient polynomial pairs
                n2 = c[0]
                if len(c) >= 5:
                    n2 += c[1] * lam_um ** c[2] / (l2 - c[3] ** c[4])
                if len(c) >= 9:
                    n2 += c[5] * lam_um ** c[6] / (l2 - c[7] ** c[8])
                return (n2 + sum(c[i] * lam_um ** c[i + 1] for i in range(9, len(c) - 1, 2))) ** 0.5
            if t == "formula 5":
                return c[0] + sum(c[i] * lam_um ** c[i + 1] for i in range(1, len(c) - 1, 2))
            raise AssertionError(f"unsupported formula type {t}")
        rows = [[float(x) for x in ln.split()] for ln in b["data"].strip().splitlines()]
        if rows[0][0] <= lam_um <= rows[-1][0]:
            return float(np.interp(lam_um, [r[0] for r in rows], [r[1] for r in rows]))
    return None


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("i3") / "materials_inorganic3_test.db"
    rep = fam.run_family("inorganic3", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    return db, rep


# ---------------------------------------------------------------- catalog, selections, gaps

def test_catalog_is_16_solids_in_three_classes_and_nothing_out_of_family_leaks_in():
    assert len(CAT) == 16 and CAT["formula"].is_unique and CAT["selection_key"].is_unique
    assert CAT["materialclass"].value_counts().to_dict() == {"oxide": 11, "carbide": 4, "carbonate": 1}
    assert not set(lst.OUT_OF_FAMILY) & set(CAT["selection_key"]) and "Ti3C2" not in set(CAT["formula"])
    out = GAPS[GAPS["gap_kind"] == "out_of_family"]
    assert set(out["key"]) == set(lst.OUT_OF_FAMILY) and out["reason"].notna().all()
    assert "MXene" in out[out["key"] == "Ti3C2"].iloc[0]["reason"] and "2D" in out[out["key"] == "Ti3C2"].iloc[0]["reason"]


def test_every_material_is_one_paper_except_sic_and_no_selection_is_null():
    assert all(v is not None for v in SEL.values()) and len(SEL) == 16 and len(AXES) == 33
    for k, m in MATCHES.items():
        if k != "SiC":
            assert m["status"] == "FOUND" and m["n_papers"] == 1, k
    assert MATCHES["SiC"]["status"] == "SELECTED_BY_USER" and MATCHES["SiC"]["n_papers"] == 6


def test_axes_are_labelled_from_the_page_and_labels_are_distinct_within_a_material():
    for k, v in SEL.items():
        labels = [a["dataset_label"] for a in v["axes"]]
        assert len(labels) == len(set(labels)), k
    assert [a["dataset_label"] for a in SEL["ZnWO4"]["axes"]] == ["Bond1965 | alpha-axis", "Bond1965 | beta-axis", "Bond1965 | gamma-axis"]
    assert [a["dataset_label"] for a in SEL["Bi4Ti3O12"]["axes"]] == ["Simon1997 | a-axis", "Simon1997 | b-axis"]
    assert [a["axis"] for a in SEL["CaWO4"]["axes"]] == ["o-ray", "e-ray"]


def test_sic_keeps_every_phase_as_its_own_labelled_dataset_and_never_merges_them():
    labels = [a["dataset_label"] for a in SEL["SiC"]["axes"]]
    assert len(labels) == len(set(labels)) == 10
    phases = {lab.split(" | ")[0] for lab in labels}
    assert phases == {"4H", "6H", "3C (beta, zincblende)", "alpha (hexagonal, polytype not stated)", "thin film"}
    for a in SEL["SiC"]["axes"]:  # the phase printed in the label must be the phase the SOURCE file states
        comment = yaml.safe_load(open(RI / a["data_path"]))["COMMENTS"]
        stated = {"4H": "4H-SiC", "6H": "6H-SiC", "3C (beta, zincblende)": "zincblende", "alpha (hexagonal, polytype not stated)": "α-SiC", "thin film": "Film deposited"}
        assert stated[a["phase"]] in comment, (a["dataset_label"], comment)


def test_sic_4h_combines_two_papers_whose_ranges_do_not_overlap():
    spans = {a["dataset_label"].split(" | ")[1]: a["span_um"] for a in SEL["SiC"]["axes"] if a["phase"] == "4H"}
    (lo1, hi1), (lo2, hi2) = spans["Wang2013"], spans["Fischer2017"]
    assert hi1 < lo2, "Wang (0.405-5 um) and Fischer (17-150 um) must be disjoint, else two 4H datasets would contradict each other"


# ---------------------------------------------------------------- density and SLD rules

def test_source_stated_densities_are_re_read_from_the_selected_pages():
    stated = CAT[CAT["density_source"].astype(str).str.startswith("literature")]
    assert set(stated["formula"]) == {"B4C", "SiC"}
    for r in stated.itertuples():
        txt = re.sub(r"<[^>]+>", "", " ".join(yaml.safe_load(open(RI / a["data_path"]))["COMMENTS"] or "" for a in SEL[r.selection_key]["axes"]))
        assert float(re.search(r"Density:\s*([\d.]+)\s*g/cm3", txt).group(1)) == r.density_g_cm3
    assert CAT[CAT.formula == "SiC"].iloc[0]["polymorph"] == "thin film" and pd.isna(CAT[CAT.formula == "SiC"].iloc[0]["mp_id"])


def test_mp_densities_are_calculated_labelled_and_only_from_entries_near_the_hull():
    mp = CAT[CAT["density_source"].isin(["MP_DFT", "bulk_elemental_approximation"])]
    assert len(mp) == 10 and (mp["mp_energy_above_hull_ev"] <= 0.025).all() and mp["mp_id"].notna().all()
    assert all("polymorph NOT verified against the sample" in f for f in mp["flags"])
    film = CAT[CAT.formula == "BiFeO3"].iloc[0]
    assert film["density_source"] == "bulk_elemental_approximation" and "film" in yaml.safe_load(open(RI / SEL["BiFeO3"]["axes"][0]["data_path"]))["COMMENTS"]
    assert (CAT[~CAT.formula.isin(["BiFeO3", "B4C", "SiC"]) & CAT.density_g_cm3.notna()]["density_source"] == "MP_DFT").all()


def test_density_gaps_are_exactly_the_four_with_reasons_and_no_sld_is_invented_for_them():
    assert set(CAT[CAT.density_g_cm3.isna()].formula) == NO_DENSITY and set(GAPS[GAPS.gap_kind == "density"].key) == NO_DENSITY
    for f in NO_DENSITY:
        r = CAT[CAT.formula == f].iloc[0]
        assert pd.isna(r["xray_sld_real"]) and pd.isna(r["neutron_sld_real"]) and pd.isna(r["mp_id"])
    assert "88 meV" in CAT[CAT.formula == "VC"].iloc[0]["flags"] and "theoretical" in CAT[CAT.formula == "ScAlMgO4"].iloc[0]["flags"]
    assert "2 MP entries" in CAT[CAT.formula == "CaWO4"].iloc[0]["flags"] and "2 MP entries" in CAT[CAT.formula == "Bi4Ti3O12"].iloc[0]["flags"]


def test_csv_sld_equals_an_independent_periodictable_recompute_including_parenthesised_dolomite():
    import periodictable as pt
    for r in CAT[CAT.density_g_cm3.notna()].itertuples():
        fm = pt.formula(r.formula)
        xr, xi = pt.xray_sld(fm, density=r.density_g_cm3, energy=8.048)
        nr, ni, _ = pt.neutron_sld(fm, density=r.density_g_cm3)
        assert (r.xray_sld_real, r.xray_sld_imag, r.neutron_sld_real, r.neutron_sld_imag) == pytest.approx((xr, xi, nr, ni), rel=1e-6), r.formula
    dol = CAT[CAT.formula == "CaMg(CO3)2"].iloc[0]
    assert dol["neutron_sld_real"] == pytest.approx(5.454, abs=0.01)  # the paren-stripping bug gave 5.947


def test_csv_n633_matches_hand_evaluation_for_every_axis_it_reports():
    for r in CAT.itertuples():
        axes = SEL[r.selection_key]["axes"][:3]
        for col, a in zip(("n_633", "n_633_axis2", "n_633_axis3"), axes):
            want, got = _hand_n(a["data_path"]), getattr(r, col)
            assert (want is None) == pd.isna(got), (r.formula, a["page"])
            if want is not None:
                assert got == pytest.approx(want, abs=1e-4), (r.formula, a["page"])


# ---------------------------------------------------------------- the loaded DB

def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 16
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == 33
    expected = sum(len(fod.parse_file(RI / a["data_path"])[0]) for _, a in AXES)
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == expected
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    assert c.execute("SELECT COUNT(*) FROM materials WHERE formula='SiC'").fetchone()[0] == 1  # one InChIKey: phases are datasets, not rows
    assert c.execute("SELECT COUNT(*) FROM chemical_descriptors").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE dataset_label IS NULL OR dataset_label='' OR source_id IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label, wavelength_nm HAVING COUNT(*)>1)").fetchone()[0] == 0
    for n, k, wl in c.execute("SELECT n, k, wavelength_nm FROM optical_dispersion"):
        assert n is not None and math.isfinite(n) and n >= 0 and wl > 0 and (k is None or math.isfinite(k))
    c.close()


def test_physical_rows_exist_only_for_materials_with_a_density_and_each_cites_a_source(loaded):
    c = sqlite3.connect(str(loaded[0]))
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == 5 * 12
    assert c.execute("SELECT COUNT(*) FROM physical_properties WHERE source_id IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM physical_properties p JOIN materials m USING(material_id) WHERE m.formula IN ('VC','ScAlMgO4','Bi4Ti3O12','CaWO4')").fetchone()[0] == 0
    src = lambda f, like: c.execute("SELECT s.technique, s.title FROM physical_properties p JOIN materials m USING(material_id) JOIN sources s USING(source_id) "
                                    "WHERE m.formula=? AND p.density_g_cm3 IS NOT NULL AND p.dataset_label LIKE ?", (f, like)).fetchone()
    assert "Materials Project" in src("TiC", "%MP_DFT%")[1]                       # calculated, cites MP
    assert src("BiFeO3", "%bulk_elemental_approximation%")[0].startswith("MP bulk DFT density used as film approximation")
    assert src("B4C", "%literature%")[1] != src("TiC", "%MP_DFT%")[1]               # source-stated density cites the paper, not MP
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("inorganic3", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    assert sum(rep.inserted.values()) == 0 and not rep.conflicts and dump(db) == before


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_every_dataset_is_preserved_row_by_row_and_n633_agrees_three_ways(loaded, key, axis):
    wl, n, *_ = fod.parse_file(RI / axis["data_path"])
    c = sqlite3.connect(str(loaded[0]))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(wl) and all(g[0] == i and g[1] == pytest.approx(float(wl[i]), rel=1e-12) and g[2] == pytest.approx(float(n[i]), rel=1e-12) for i, g in enumerate(got))
    assert got[-1][1] < 2_000_000.0  # the loader window is unchanged
    hand = _hand_n(axis["data_path"])
    if wl.min() <= 633 <= wl.max():
        assert hand is not None and float(np.interp(633.0, wl, n)) == pytest.approx(hand, abs=1e-4)  # DB == parse_file == hand
    else:
        assert hand is None  # no coverage of 633 nm: no value, nothing extrapolated


def test_selfpairs_none_are_identical_and_the_detector_detects_a_real_duplicate(loaded, tmp_path):
    db = tmp_path / "v.db"
    shutil.copy(loaded[0], db)
    c = sqlite3.connect(str(db))
    for (mid,) in c.execute("SELECT material_id FROM materials").fetchall():
        validate_optical_material(c, mid)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation").fetchone()[0] == 40  # o/e, a/b and alpha/beta/gamma axes, and SiC's phases
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE pearson_r >= 0.999999").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE rmse < 1e-9").fetchone()[0] == 0
    kt = c.execute("SELECT material_id FROM materials WHERE formula='KTaO3'").fetchone()[0]
    c.execute("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) "
              "SELECT material_id,wavelength_nm,n,k,'DUP-CONTROL','ctrl/'||raw_record_table,raw_record_id,source_id FROM optical_dispersion WHERE material_id=?", (kt,))
    validate_optical_material(c, kt)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE pearson_r >= 0.999999").fetchone()[0] == 1  # negative control
    c.close()
