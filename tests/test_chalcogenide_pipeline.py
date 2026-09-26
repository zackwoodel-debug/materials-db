"""Tests for the sulfide/selenide family (match_ri_info_chalcogenides.py, build_chalcogenides_csv.py, load_chalcogenides_db.py).

Every optical value and every SLD is recomputed independently at test time (hand evaluation of the RI.info formulas; periodictable directly).
The GaSe deferral and the SnSe alpha-axis exclusion are re-derived from the RI.info files, so they fail if the source changes.
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
sys.path.insert(0, str(ROOT / "migration_scripts"))

import chalcogenide_material_list as lst  # noqa: E402
import load_chalcogenides_db as wrap  # noqa: E402
import load_family_db as fam  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from materials_db.export import modalfit  # noqa: E402
from validate_datasets import validate_optical_material  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database" / "data"
CAT = pd.read_csv(DATA / "chalcogenides.csv")
GAPS = pd.read_csv(DATA / "chalcogenide_gaps.csv")
SEL = json.loads((DATA / "step1_selections_chalcogenides.json").read_text())
MATCHES = {c["key"]: c for c in json.loads((DATA / "chalcogenide_ri_matches.json").read_text())["candidates"]}
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
MULTI_PAPER = {"AgGaS2": 3, "BaGa4S7": 2, "AgGaSe2": 3, "As2Se3": 2, "BaGa4Se7": 2, "CdSe": 3, "PbSe": 2, "ZnSe": 5}
NO_DENSITY = {"BaGa2GeSe6"}


def _hand_n(path, lam_um=0.633):
    """n at lam from the YAML, independent of parse_file (RI.info formulas written from their published definitions)."""
    for b in yaml.safe_load(open(RI / path))["DATA"]:
        t = b["type"]
        if t == "tabulated k":
            continue
        if t.startswith("formula"):
            lo, hi = [float(x) for x in b["wavelength_range"].split()]
            if not lo <= lam_um <= hi:
                continue
            c, l2 = [float(x) for x in b["coefficients"].split()], lam_um ** 2
            if t == "formula 1":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1] ** 2) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 2":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1]) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 4":
                n2 = c[0]
                if len(c) >= 5:
                    n2 += c[1] * lam_um ** c[2] / (l2 - c[3] ** c[4])
                if len(c) >= 9:
                    n2 += c[5] * lam_um ** c[6] / (l2 - c[7] ** c[8])
                return (n2 + sum(c[i] * lam_um ** c[i + 1] for i in range(9, len(c) - 1, 2))) ** 0.5
            if t == "formula 5":  # Cauchy: n = C1 + C2 lam^C3 + C4 lam^C5 + ...
                return c[0] + sum(c[i] * lam_um ** c[i + 1] for i in range(1, len(c) - 1, 2))
            raise AssertionError(f"unsupported formula type {t}")
        rows = [[float(x) for x in ln.split()] for ln in b["data"].strip().splitlines()]
        if rows[0][0] <= lam_um <= rows[-1][0]:
            return float(np.interp(lam_um, [r[0] for r in rows], [r[1] for r in rows]))
    return None


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("chalc") / "materials_chalcogenide_test.db"
    rep = fam.run_family("chalcogenide", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    return db, rep


# ---------------------------------------------------------------- scope: catalog, deferral, exclusion

def test_catalog_is_16_bulk_sulfides_and_selenides_and_nothing_2d_or_deferred_leaks_in():
    assert len(CAT) == 16 and CAT["formula"].is_unique and CAT["selection_key"].is_unique
    assert CAT["materialclass"].value_counts().to_dict() == {"selenide": 9, "sulfide": 7}
    assert not (set(lst.OUT_OF_FAMILY) | set(lst.DEFERRED) | set(lst.ALREADY_LOADED)) & set(CAT["formula"])
    assert set(GAPS[GAPS.gap_kind == "out_of_family"].key) == set(lst.OUT_OF_FAMILY)
    assert set(GAPS[GAPS.gap_kind == "deferred_decision"].key) == {"GaSe"}
    assert set(GAPS[GAPS.gap_kind == "excluded_page"].key) == {"SnSe"}
    assert set(GAPS[GAPS.gap_kind == "density"].key) == NO_DENSITY and GAPS["reason"].notna().all()


def test_none_of_the_already_loaded_sulfides_is_duplicated_here():
    c = sqlite3.connect(f"{(DATA / 'materials_oxide_test.db').as_uri()}?mode=ro", uri=True)
    have = {r[0] for r in c.execute("SELECT formula FROM materials")}
    c.close()
    assert set(lst.ALREADY_LOADED) <= have and not have & set(CAT["formula"])


def test_gase_deferral_reason_is_still_true_in_the_source():
    """Every GaSe formula page goes non-physical (n^2 <= 0) inside its own stated range, and Kato's title/file ranges disagree."""
    book = MATCHES.get("GaSe")
    assert book is None  # not a candidate this run
    pages = sorted((RI / "main" / "GaSe" / "nk").glob("*.yml"))
    formula_pages = 0
    for p in pages:
        for b in yaml.safe_load(open(p))["DATA"]:
            if b["type"].startswith("formula"):
                formula_pages += 1
                lo, hi = (float(x) for x in b["wavelength_range"].split())
                lam = np.geomspace(lo, hi, 50000)
                c = [float(x) for x in b["coefficients"].split()]
                n2 = c[0] + c[1] * lam ** c[2] / (lam ** 2 - c[3] ** c[4]) + (c[5] * lam ** c[6] / (lam ** 2 - c[7] ** c[8]) if len(c) >= 9 else 0)
                n2 = n2 + sum(c[i] * lam ** c[i + 1] for i in range(9, len(c) - 1, 2))
                assert (n2 <= 0).any(), p.name
    assert formula_pages == 4
    kato = yaml.safe_load(open(RI / "main" / "GaSe" / "nk" / "Kato-o.yml"))["DATA"][0]["wavelength_range"]
    assert kato.split()[1] == "1620.0" or float(kato.split()[1]) == 1620.0
    assert "162 um" in lst.DEFERRED["GaSe"].replace("0.8-162 um", "162 um")


def test_snse_alpha_axis_is_excluded_for_the_stated_reason_and_beta_gamma_are_loaded():
    alpha = next(d for d in MATCHES["SnSe"]["datasets"] if d["page"] == "Guo-α")["data_path"]  # the file itself is Guo-alpha.yml
    rows = np.array([[float(x) for x in ln.split()] for ln in yaml.safe_load(open(RI / alpha))["DATA"][0]["data"].strip().splitlines()])
    assert (rows[:, 2] == 0).all() and rows[:, 1].max() < 1.5  # k exactly 0 everywhere and n < 1.5: the evidence in the exclusion reason
    assert [a["axis"] for a in SEL["SnSe"]["axes"]] == ["beta-axis", "gamma-axis"]
    assert MATCHES["SnSe"]["excluded_pages"] == ["Guo-α"]
    assert "NOT loaded" in CAT[CAT.formula == "SnSe"].iloc[0]["flags"]


# ---------------------------------------------------------------- selections and labels

def test_selections_none_null_labels_unique_and_multi_paper_materials_keep_every_paper():
    assert all(v is not None for v in SEL.values()) and len(SEL) == 16 and len(AXES) == 59
    for k, v in SEL.items():
        labels = [a["dataset_label"] for a in v["axes"]]
        assert len(labels) == len(set(labels)), k
        papers = {a["tag"].split("-")[0] for a in v["axes"]}  # CdSe hexagonal + cubic Ninomiya pages are ONE paper; CuGaS2 20/120 degC too
        assert len(papers) == MULTI_PAPER.get(k, 1), (k, papers)
    for k in MULTI_PAPER:
        assert MATCHES[k]["status"] == "SELECTED_BY_USER"


def test_multi_paper_primary_is_measured_then_the_widest_page_covering_633nm():
    """Single-paper materials keep the source's page order (o before e). Between PAPERS: measured data before model fits
    (dataset_kind.py), then the widest page covering 633 nm, else the widest."""
    from dataset_kind import is_model_fit
    for k in MULTI_PAPER:
        v = SEL[k]
        first = v["axes"][0]
        measured = [a for a in v["axes"] if not is_model_fit(a["data_path"])]
        pool = measured or v["axes"]
        assert first in pool, k
        covering = [a for a in pool if a["span_um"][0] <= 0.633 <= a["span_um"][1]] or pool
        assert first in covering and (first["span_um"][1] - first["span_um"][0]) == max(a["span_um"][1] - a["span_um"][0] for a in covering), k
    assert [SEL[k]["axes"][0]["tag"] for k in ("CdSe", "PbSe")] == ["Lisitsa1969", "Zemel1965"]  # measured, not the Adachi-group fits


def test_cugas2_temperature_series_and_cdse_phases_are_labelled_from_the_source():
    assert [a["dataset_label"] for a in SEL["CuGaS2"]["axes"]] == ["Boyd1971-20C | o-ray", "Boyd1971-20C | e-ray", "Boyd1971-120C | o-ray", "Boyd1971-120C | e-ray"]
    for a in SEL["CuGaS2"]["axes"]:
        assert ("20 °C" if "-20C" in a["dataset_label"] else "120 °C") in a["comments"]
    phases = {a["dataset_label"]: a["phase"] for a in SEL["CdSe"]["axes"]}
    assert phases["hexagonal | Ninomiya1995 | o-ray"] == "hexagonal" and phases["cubic | Ninomiya1995"] == "cubic"
    for a in SEL["CdSe"]["axes"]:  # a phase label only where the page itself states the phase
        comment = yaml.safe_load(open(RI / a["data_path"]))["COMMENTS"] or ""
        assert (a["phase"] is None) == ("Hexagonal" not in comment and "Cubic" not in comment), a["dataset_label"]


def test_every_selected_page_has_a_supported_type_and_no_nonphysical_formula_value_in_range():
    for k, a in AXES:
        for b in yaml.safe_load(open(RI / a["data_path"]))["DATA"]:
            assert b["type"] in {"tabulated nk", "tabulated n", "tabulated k", "formula 1", "formula 2", "formula 4"}, a["page"]
            if b["type"].startswith("formula"):
                lo, hi = (float(x) for x in b["wavelength_range"].split())
                n, _ = fod.eval_formula(b, np.geomspace(lo, hi, 20000))
                assert n.min() > 1e-3, (k, a["page"])


# ---------------------------------------------------------------- density and SLD

TEXTBOOK_RHO = {"Ag3AsS3": 5.57, "AgGaS2": 4.70, "CuGaS2": 4.37, "LiGaS2": 2.94, "AgGaSe2": 5.70, "As2Se3": 4.62, "CdSe": 5.81, "PbSe": 8.10,
                "SnSe": 6.18, "ZnSe": 5.27, "Tl3AsSe3": 7.83}


def test_ambient_structure_materials_use_that_space_group_and_others_a_non_theoretical_entry():
    for r in CAT[CAT.density_g_cm3.notna()].itertuples():
        if r.selection_key in lst.AMBIENT_STRUCTURE:
            assert f"#{lst.AMBIENT_STRUCTURE[r.selection_key][1]}" in r.mp_space_group, r.formula
        else:
            assert "polymorph NOT verified" in r.flags and "non-theoretical" in r.flags, r.formula
        assert r.density_source in ("MP_DFT", "bulk_elemental_approximation") and pd.notna(r.mp_id)
    assert "C2/c" in CAT[CAT.formula == "Ag3AsS3"].iloc[0]["flags"]  # the DFT-lowest xanthoconite, deliberately not used for proustite


def test_film_density_is_a_labelled_bulk_approximation_and_densities_are_near_textbook():
    a = CAT[CAT.formula == "As2Se3"].iloc[0]
    assert a["density_source"] == "bulk_elemental_approximation" and "film" in a["flags"]
    assert (CAT[CAT.formula != "As2Se3"].dropna(subset=["density_g_cm3"])["density_source"] == "MP_DFT").all()
    for r in CAT.dropna(subset=["density_g_cm3"]).itertuples():
        if r.formula in TEXTBOOK_RHO:
            assert abs(r.density_g_cm3 / TEXTBOOK_RHO[r.formula] - 1) < 0.12, (r.formula, r.density_g_cm3)


def test_no_density_means_no_sld_and_the_gap_is_recorded():
    for f in NO_DENSITY:
        r = CAT[CAT.formula == f].iloc[0]
        assert pd.isna(r["density_g_cm3"]) and pd.isna(r["xray_sld_real"]) and pd.isna(r["neutron_sld_real"]) and "left NULL" in r["flags"]


def test_csv_sld_equals_an_independent_periodictable_recompute():
    import periodictable as pt
    for r in CAT.dropna(subset=["density_g_cm3"]).itertuples():
        fm = pt.formula(r.formula)
        xr, xi = pt.xray_sld(fm, density=r.density_g_cm3, energy=8.048)
        nr, ni, _ = pt.neutron_sld(fm, density=r.density_g_cm3)
        assert (r.xray_sld_real, r.xray_sld_imag, r.neutron_sld_real, r.neutron_sld_imag) == pytest.approx((xr, xi, nr, ni), rel=1e-6), r.formula


# ---------------------------------------------------------------- n(633 nm)

def test_csv_n633_columns_match_hand_evaluation_of_the_primary_papers_axes():
    for r in CAT.itertuples():
        first = SEL[r.selection_key]["axes"][0]
        same_paper = [a for a in SEL[r.selection_key]["axes"] if (a["phase"], a["tag"]) == (first["phase"], first["tag"])][:3]
        for col, a in zip(("n_633", "n_633_axis2", "n_633_axis3"), same_paper):
            want, got = _hand_n(a["data_path"]), getattr(r, col)
            assert (want is None) == pd.isna(got), (r.formula, a["page"])
            if want is not None:
                assert got == pytest.approx(want, abs=1e-6), (r.formula, a["page"])


def test_zinc_selenide_sources_are_all_recorded_and_the_querry_disagreement_is_flagged():
    flags = CAT[CAT.formula == "ZnSe"].iloc[0]["flags"]
    for tag in ("Connolly1979", "Amotchkina2020", "Marple1964", "Adachi1991"):
        assert f"additional source {tag}" in flags
    assert "SOURCES DISAGREE" in flags and "Querry1987" in flags
    assert _hand_n(next(a for a in SEL["ZnSe"]["axes"] if a["tag"] == "Connolly1979")["data_path"]) == pytest.approx(2.591, abs=2e-3)  # textbook ~2.59


# ---------------------------------------------------------------- the loaded DB

def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 16
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == 59
    expected = sum(len(fod.parse_file(RI / a["data_path"])[0]) for _, a in AXES)
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == expected
    assert rep.skipped == [] and rep.conflicts == []
    assert c.execute("SELECT COUNT(*) FROM chemical_descriptors").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE dataset_label IS NULL OR dataset_label='' OR source_id IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label, wavelength_nm HAVING COUNT(*)>1)").fetchone()[0] == 0
    for n, k, wl in c.execute("SELECT n, k, wavelength_nm FROM optical_dispersion"):
        assert n is not None and math.isfinite(n) and n > 1e-3 and wl > 0 and (k is None or (math.isfinite(k) and k >= 0))
    c.close()


def test_physical_rows_one_block_per_material_with_a_density(loaded):
    c = sqlite3.connect(str(loaded[0]))
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == 5 * (16 - len(NO_DENSITY))
    assert c.execute("SELECT COUNT(*) FROM physical_properties WHERE source_id IS NULL").fetchone()[0] == 0
    film = c.execute("SELECT s.technique FROM physical_properties p JOIN materials m USING(material_id) JOIN sources s USING(source_id) "
                     "WHERE m.formula='As2Se3' AND p.density_g_cm3 IS NOT NULL").fetchone()[0]
    assert film.startswith("MP bulk DFT density used as film approximation")
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("chalcogenide", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
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
        assert hand is not None and float(np.interp(633.0, wl, n)) == pytest.approx(hand, abs=5e-3)
    else:
        assert hand is None


def test_validation_finds_no_self_pairs_and_detects_a_planted_duplicate(loaded, tmp_path):
    db = tmp_path / "v.db"
    shutil.copy(loaded[0], db)
    c = sqlite3.connect(str(db))
    for (mid,) in c.execute("SELECT material_id FROM materials").fetchall():
        validate_optical_material(c, mid)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE rmse < 1e-9").fetchone()[0] == 0  # no dataset is a copy of another
    # near-perfect correlation WITHOUT equality: two axes of a weakly birefringent crystal (same shape, offset ~0.02). Pinned, not a duplicate.
    high = c.execute("SELECT m.formula, v.dataset_a, v.dataset_b, v.rmse FROM dataset_validation v JOIN materials m USING(material_id) "
                     "WHERE v.pearson_r >= 0.999999").fetchall()
    assert [(f, a, b) for f, a, b, _ in high] == [("BaGa4S7", "Badikov2010 | beta-axis", "Badikov2010 | gamma-axis")] and high[0][3] > 0.01
    zn = c.execute("SELECT material_id FROM materials WHERE formula='ZnSe'").fetchone()[0]
    c.execute("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) "
              "SELECT material_id,wavelength_nm,n,k,'DUP-CONTROL','ctrl/'||raw_record_table,raw_record_id,source_id FROM optical_dispersion "
              "WHERE material_id=? AND dataset_label='Connolly1979'", (zn,))
    validate_optical_material(c, zn)
    assert c.execute("SELECT COUNT(*) FROM dataset_validation WHERE rmse < 1e-9").fetchone()[0] == 1  # negative control: the planted copy is caught
    c.close()


# ---------------------------------------------------------------- ModalFit export (the halide lesson: labels must pair)

def test_exporter_reads_a_page_qualified_source_tag_as_a_source_not_a_polymorph():
    assert modalfit._polymorph_prefix("Boyd1971-20C | o-ray") is None and modalfit._polymorph_prefix("Chen2009-nk | e-ray") is None
    assert modalfit._polymorph_prefix("Devore1951 | o-ray") is None and modalfit._polymorph_prefix("density_MP_DFT") is None
    for real in ("rutile", "K2NiF4-type", "4H", "3C (beta, zincblende)", "hexagonal", "alpha (hexagonal, polytype not stated)"):
        assert modalfit._polymorph_prefix(f"{real} | X") == real


def test_every_material_with_a_density_exports_and_the_choices_are_the_room_temperature_and_stated_phase(loaded, tmp_path, capsys):
    ok = {}
    for r in CAT.itertuples():
        try:
            layer = modalfit.export_layer(str(loaded[0]), r.name, nk_csv_dir=tmp_path / r.selection_key, label=r.name)
            ok[r.formula] = layer["materials_db"]["optical_dataset_label"]
        except modalfit.ExportError:
            assert r.formula in NO_DENSITY, r.formula
    assert len(ok) == 16 - len(NO_DENSITY)
    assert ok["CuGaS2"] == "Boyd1971-20C | o-ray"             # room temperature, not the 120 degC series
    assert ok["CdSe"].startswith("hexagonal | Ninomiya1995")   # density is hexagonal, so is the paired optical data
