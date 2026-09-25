"""Tests for the liquids and biomolecules family (match_ri_info_liquids.py, build_liquids_csv.py, load_liquids_db.py), RI.info
formula 9, and the kelvin fix in parse_file.

Every scoping decision is re-derived from the refractiveindex.info files (phases, isomers, D2O, excluded pages), every optical value
and SLD is recomputed independently, and densities are checked against the CIPM water formula and physical consistency rules.
Offline: nothing here calls PubChem or NIST.
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

import build_liquids_csv as builder  # noqa: E402
import liquid_material_list as lst  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_liquids_db as wrap  # noqa: E402
import match_ri_info_liquids as matcher  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
from materials_db.export import modalfit  # noqa: E402
from validate_datasets import validate_optical_material  # noqa: E402

DATA, RIDB = ROOT / "data", ROOT / "refractiveindex_db" / "database"
RI = RIDB / "data"
CAT = pd.read_csv(DATA / "liquids.csv")
GAPS = pd.read_csv(DATA / "liquid_gaps.csv")
SEL = json.loads((DATA / "step1_selections_liquids.json").read_text())
MATCHES = {c["key"]: c for c in json.loads((DATA / "liquid_ri_matches.json").read_text())["candidates"]}
AXES = [(k, a) for k, v in SEL.items() for a in v["axes"]]
ROW = CAT.set_index("selection_key")


def _hand_n(path, lam_um=0.633):
    """n at lam from the YAML, from refractiveindex.info's own formula definitions (doc/Dispersion formulas.pdf)."""
    for b in yaml.safe_load(open(RI / path))["DATA"]:
        t = b["type"]
        if t == "tabulated k":
            continue
        if t.startswith("formula"):
            lo, hi = [float(x) for x in b["wavelength_range"].split()]
            if not lo <= lam_um <= hi:
                continue
            c, L = [float(x) for x in b["coefficients"].split()], lam_um
            c += [0.0] * (17 - len(c))
            if t == "formula 1":
                return (1 + c[0] + sum(c[i] * L ** 2 / (L ** 2 - c[i + 1] ** 2) for i in range(1, 16, 2))) ** 0.5
            if t == "formula 2":
                return (1 + c[0] + sum(c[i] * L ** 2 / (L ** 2 - c[i + 1]) for i in range(1, 16, 2))) ** 0.5
            if t == "formula 3":
                return (c[0] + sum(c[i] * L ** c[i + 1] for i in range(1, 16, 2))) ** 0.5
            if t == "formula 4":
                return (c[0] + c[1] * L ** c[2] / (L ** 2 - c[3] ** c[4]) + c[5] * L ** c[6] / (L ** 2 - c[7] ** c[8])
                        + sum(c[i] * L ** c[i + 1] for i in range(9, 16, 2))) ** 0.5
            if t == "formula 5":
                return c[0] + sum(c[i] * L ** c[i + 1] for i in range(1, 10, 2))
            if t == "formula 9":
                return (c[0] + c[1] / (L ** 2 - c[2]) + c[3] * (L - c[4]) / ((L - c[4]) ** 2 + c[5])) ** 0.5
            raise AssertionError(f"unsupported formula type {t}")
        rows = [[float(x) for x in ln.split()] for ln in b["data"].strip().splitlines()]
        if rows[0][0] <= lam_um <= rows[-1][0]:
            return float(np.interp(lam_um, [r[0] for r in rows], [r[1] for r in rows]))
    return None


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    db = tmp_path_factory.mktemp("liq") / "materials_liquid_test.db"
    rep = fam.run_family("liquid", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE,
                         literature_note=wrap.LITERATURE_NOTE, allow_null_formula=True)
    return db, rep


# ---------------------------------------------------------------- formula 9 and the kelvin fix

def test_formula9_is_the_official_exotic_formula_and_urea_is_positive_uniaxial():
    e = yaml.safe_load(open(next(RI.glob("organic/*urea/nk/Rosker-e.yml"))))["DATA"][0]
    o = yaml.safe_load(open(next(RI.glob("organic/*urea/nk/Rosker-o.yml"))))["DATA"][0]
    assert e["type"] == "formula 9"
    lam = np.linspace(0.3, 1.06, 40)
    ne, no = fod.eval_formula(e, lam)[0], fod.eval_formula(o, lam)[0]
    c = [float(x) for x in e["coefficients"].split()]
    assert ne == pytest.approx(np.sqrt(c[0] + c[1] / (lam ** 2 - c[2]) + c[3] * (lam - c[4]) / ((lam - c[4]) ** 2 + c[5])), rel=1e-12)
    assert (ne - no > 0.1).all()  # urea: positive uniaxial, birefringence ~0.11


def test_conditions_temperature_is_kelvin_even_when_cryogenic():
    wl, n, k, refs, t = fod.parse_file(RI / "main/H2O/nk/Kofman-10K.yml")
    assert t == pytest.approx(10 - 273.15)          # was +10 degC under the old "<= 200 means Celsius" guess
    assert fod.parse_file(RI / "main/Si/nk/Franta-25C.yml")[4] == pytest.approx(25.0)  # a "-25C" file name still wins


# ---------------------------------------------------------------- scope, completeness, identity

def test_scope_is_complete_and_classes_add_up():
    assert len(CAT) == len(lst.CANDIDATES) == 75 and CAT.name.is_unique
    assert CAT.materialclass.value_counts().to_dict() == {"liquid": 67, "biomacromolecule": 5, "biomolecule": 3}
    cat = yaml.safe_load(open(RIDB / "catalog-nk.yml"))
    in_scope = set()
    for shelf in cat:
        div = None
        for item in shelf.get("content", []):
            if "DIVIDER" in item:
                div = matcher.strip(item["DIVIDER"])
            elif "BOOK" in item and shelf.get("SHELF") in matcher.SCANNED and matcher.SCANNED[shelf["SHELF"]](div) and \
                    (shelf["SHELF"] != "main" or item["BOOK"] in matcher.MAIN_BOOKS_IN_SCOPE):
                in_scope.add(f"{shelf['SHELF']}/{item['BOOK']}")
    claimed = {f"{c['shelf']}/{c['book']}" for c in lst.CANDIDATES} | set(lst.OUT_OF_FAMILY)
    assert in_scope <= claimed  # nothing in the scanned areas is silently skipped
    assert set(GAPS[GAPS.gap_kind == "out_of_family"].key) == set(lst.OUT_OF_FAMILY)


def test_water_pages_carry_the_phase_their_own_text_states_and_d2o_is_its_own_compound():
    words = {"liquid": r"^(?!.*(supercooled|ice)).*liquid|distilled water|HPLC", "supercooled liquid": r"supercooled", "ice": r"water ice \(solid",
             "amorphous ice": r"amorphous water ice", "crystalline ice": r"crystalline water ice"}
    for a in SEL["H2O"]["axes"]:
        comment = yaml.safe_load(open(RI / a["data_path"]))["COMMENTS"]
        assert re.search(words[a["phase"]], comment, re.I | re.S), (a["page"], a["phase"], comment)
        assert "D2O" not in a["page"] and "heavy" not in comment.lower()
    for a in SEL["D2O"]["axes"]:
        assert "D2O" in a["page"]
    assert ROW.loc["D2O", "inchikey"] != ROW.loc["H2O", "inchikey"] and ROW.loc["D2O", "smiles"] == "[2H]O[2H]"


@pytest.mark.parametrize("key,word", [("n-C5H12", r"n-Pentane"), ("i-C5H12", r"iso-Pentane"), ("n-C8H18", r"n-Octane"), ("i-C8H18", r"iso-Octane"),
                                      ("2-C3H7OH", r"iso-?propanol"), ("1-C3H7OH", r"1-Propanol"), ("1-C4H9OH", r"n-Butanol|1-Butanol"),
                                      ("i-C4H9OH", r"iso-?Butanol"), ("1-C5H11OH", r"Normal amyl"), ("i-C5H11OH", r"Isoamyl"),
                                      ("C5H10O2-ipac", r"isopropyl acetate")])
def test_every_page_of_a_split_book_names_the_isomer_it_was_assigned_to(key, word):
    for a in SEL[key]["axes"]:
        text = a["comments"] + " " + next(d["title"] for d in MATCHES[key]["datasets"] if d["page"] == a["page"])
        assert re.search(word, text, re.I), (key, a["page"], text)


ISOMER_SMILES = {"n-C5H12": "CCCCC", "i-C5H12": "CCC(C)C", "n-C8H18": "CCCCCCCC", "i-C8H18": "CC(C)CC(C)(C)C", "2-C3H7OH": "CC(C)O",
                 "1-C3H7OH": "CCCO", "1-C4H9OH": "CCCCO", "i-C4H9OH": "CC(C)CO", "1-C5H11OH": "CCCCCO", "i-C5H11OH": "CC(C)CCO",
                 "C5H10O2-ipac": "CC(=O)OC(C)C", "C4H8O2-etac": "CCOC(C)=O", "C4H8O2-dioxane": "C1COCCO1", "p-C8H10": "Cc1ccc(C)cc1",
                 "C6H3Cl3": "Clc1ccc(Cl)c(Cl)c1", "D2O": "[2H]O[2H]"}


def test_pubchem_identity_is_the_right_isomer_and_every_formula_matches_its_smiles():
    from rdkit import Chem
    canon = lambda s: Chem.MolToSmiles(Chem.MolFromSmiles(s))
    for key, want in ISOMER_SMILES.items():
        assert canon(ROW.loc[key, "smiles"]) == canon(want), key
    for key, r in ROW.iterrows():
        if pd.isna(r.formula):
            assert pd.isna(r.pubchem_cid) and r.materialclass == "biomacromolecule"
            continue
        assert pd.notna(r.pubchem_cid) and pd.notna(r.inchikey), key
        assert builder.isotope_formula_ok(r.smiles, r.formula), key


def test_source_metadata_errors_are_recorded_not_trusted():
    assert {k for k, m in MATCHES.items() if m.get("about_yml_formula_matches") is False} == {"CBrCl3", "C6H12", "C2H4(OH)2", "C8H19NO"}
    for k in ("CBrCl3", "C6H12", "C2H4(OH)2", "C8H19NO"):
        assert "about.yml for this book lists the formula" in ROW.loc[k, "flags"]
    for k in ("n-C8H18", "C7H8", "C8H8", "C6H5NO2"):  # Myers pages whose COMMENTS say "Isopropanol"
        assert "the page's COMMENTS say 'Isopropanol'" in ROW.loc[k, "flags"], k


def test_excluded_pages_are_not_loaded_and_the_cs2_pole_is_why():
    loaded_pages = {(k, a["page"]) for k, a in AXES}
    assert ("CS2", "Chemnitz") not in loaded_pages and ("n-C6H14", "Chang") not in loaded_pages and ("1-C4H9OH", "El-Kashef") not in loaded_pages
    b = yaml.safe_load(open(RI / "main/CS2/nk/Chemnitz.yml"))["DATA"][0]
    n, _ = fod.eval_formula(b, np.geomspace(6.3, 6.8, 5000))
    assert (n <= 1e-3).any() and (n > 5).any()  # the reason recorded for the exclusion is still true
    assert {a["tag"] for a in SEL["CS2"]["axes"]} == {"Kedenburg2012", "Chang2024", "Ghosal1993"}


# ---------------------------------------------------------------- density

def test_water_density_is_the_cipm_formula_at_the_primary_datasets_temperature():
    t = SEL["H2O"]["axes"][0]["temperature_c"]
    assert ROW.loc["H2O", "density_temperature_c"] == t == pytest.approx(24.85)          # Segelstein's CONDITIONS: 298 K
    assert ROW.loc["H2O", "density_g_cm3"] == pytest.approx(builder.tanaka_water_density(t), abs=1e-6)
    assert builder.tanaka_water_density(25.0) == pytest.approx(0.997047, abs=1e-6)     # Tanaka et al. 2001 at 25 degC
    assert builder.tanaka_water_density(20.0) == pytest.approx(0.998207, abs=1e-6)     # the textbook anchor
    assert builder.tanaka_water_density(3.983035) == pytest.approx(0.999975, abs=1e-6)  # maximum density at 3.98 degC
    assert ROW.loc["H2O", "density_citation_doi"] == "10.1088/0026-1394/38/4/3"


def test_every_density_is_cited_and_carries_its_temperature():
    have = CAT[CAT.density_g_cm3.notna()]
    assert len(have) == 50
    assert have.density_temperature_c.notna().all() and have.density_citation_title.notna().all()
    for r in have.itertuples():
        t_opt = SEL[r.selection_key]["axes"][0]["temperature_c"] or builder.ROOM_T_C
        assert abs(r.density_temperature_c - t_opt) <= builder.T_WINDOW_C, r.name
    nist = have[have["flags"].str.contains("NIST SRD 69", regex=False)]
    assert set(nist.selection_key) == {"D2O", "n-C5H12", "i-C5H12", "n-C6H14", "n-C7H16", "n-C8H18", "C6H6", "C6H12", "C7H8", "CH3OH"}
    assert (nist.density_citation_doi == "10.18434/T4D303").all()


def test_nist_values_agree_with_every_consistent_pubchem_cross_check():
    for r in CAT[CAT["flags"].str.contains("PubChem cross-check: 0", regex=False) | CAT["flags"].str.contains("PubChem cross-check: 1", regex=False)].itertuples():
        m = re.search(r"PubChem cross-check: ([\d.]+) g/cm3 at ([\d.-]+) degC", r.flags)
        pv, pt = float(m.group(1)), float(m.group(2))
        a, b = (pv, pt), (r.density_g_cm3, r.density_temperature_c)
        rec = lambda v, t, raw: (v, t, "x", 5, raw, True)
        assert builder.consistent(rec(*a, f"{pv} at"), rec(*b, f"{r.density_g_cm3:.6f} at")), r.name


def test_consistency_rule_rejects_mislabelled_temperatures_and_accepts_real_expansion():
    rec = lambda v, t, raw, src="S": (v, t, src, len(raw.replace(".", "").lstrip("0")), f"{raw} at {t} C", True)
    # n-hexane in PubChem: HSDB/PAC 0.6606 "at 25 degC" vs CAMEO 0.659 at 20 degC -> the liquid would get denser when warmed
    assert not builder.consistent(rec(0.659, 20, "0.659"), rec(0.6606, 25, "0.6606"))
    # toluene: two records at 20 degC 0.54% apart
    assert not builder.consistent(rec(0.867, 20, "0.867"), rec(0.8623, 20, "0.8623"))
    # chloroform: 1.4832 at 20 and 1.4788 at 25 -> 0.06%/degC of expansion, fine
    assert builder.consistent(rec(1.4832, 20, "1.4832"), rec(1.4788, 25, "1.4788"))
    v, *_ = builder.choose_density([rec(0.659, 20, "0.659", "A"), rec(0.6606, 25, "0.6606", "B")], 22)
    assert v is None
    v, t, *_ = builder.choose_density([rec(1.4832, 20, "1.4832", "A"), rec(1.4788, 25, "1.4788", "B")], 21.75)
    assert (v, t) == (1.4832, 20)


def test_density_parser_reads_only_values_with_a_stated_temperature():
    pv = {"Record": {"Reference": [{"ReferenceNumber": 1, "SourceName": "HSDB"}],
                     "Section": [{"Information": [{"ReferenceNumber": 1, "Value": {"StringWithMarkup": [{"String": s}]}} for s in (
                         "0.7893 g/cu cm at 20 °C", "1.100 at 20 °C/4 °C", "13.534 @ 25 °C", "Relative density (water = 1): 0.79",
                         "1.087-1.092", "0.79", "0.79 at 68 °F (USCG, 1999)")]}]}}
    recs = builder.parse_density_records(pv)
    assert [(round(r[0], 5), r[1], r[5]) for r in recs] == [(0.7893, 20.0, True), (round(1.100 * 0.999975, 5), 20.0, True), (13.534, 25.0, True),
                                                            (0.79, 20.0, False)]


# ---------------------------------------------------------------- SLD and n(633 nm)

def test_sld_matches_periodictable_and_the_textbook_water_values():
    import periodictable as pt
    for r in CAT[CAT.density_g_cm3.notna()].itertuples():
        f = pt.formula(r.formula)
        xr, xi = pt.xray_sld(f, density=r.density_g_cm3, energy=8.048)
        nr, ni, _ = pt.neutron_sld(f, density=r.density_g_cm3)
        assert (r.xray_sld_real, r.xray_sld_imag, r.neutron_sld_real, r.neutron_sld_imag) == pytest.approx((xr, xi, nr, ni), rel=1e-6), r.name
    assert ROW.loc["H2O", "neutron_sld_real"] == pytest.approx(-0.56, abs=0.01)  # the contrast-variation classic
    assert ROW.loc["D2O", "neutron_sld_real"] == pytest.approx(6.37, abs=0.03)


def test_csv_n633_is_the_exact_formula_value_of_the_primary_dataset():
    for r in CAT.itertuples():
        first = SEL[r.selection_key]["axes"][0]
        want = _hand_n(first["data_path"])
        assert (want is None) == pd.isna(r.n_633), r.name
        if want is not None:
            assert r.n_633 == pytest.approx(want, abs=1e-6), r.name
    assert ROW.loc["H2O", "n_633"] == pytest.approx(1.332, abs=2e-3) and ROW.loc["C2H5OH", "n_633"] == pytest.approx(1.361, abs=3e-3)


# ---------------------------------------------------------------- the loaded DB

def test_loaded_db_facts(loaded):
    db, rep = loaded
    c = sqlite3.connect(str(db))
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 75
    assert c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0] == len(AXES) == 182
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == sum(len(fod.parse_file(RI / a["data_path"])[0]) for _, a in AXES)
    assert rep.skipped == [] and rep.conflicts == [] and rep.warnings == []
    for n, k, wl in c.execute("SELECT n, k, wavelength_nm FROM optical_dispersion"):
        assert n is not None and math.isfinite(n) and n > 1e-3 and wl > 0 and (k is None or (math.isfinite(k) and k >= 0))
    assert c.execute("SELECT COUNT(*) FROM physical_properties WHERE temperature_c IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM physical_properties").fetchone()[0] == 5 * 50
    assert c.execute("SELECT COUNT(*) FROM materials WHERE formula IS NULL").fetchone()[0] == 5
    c.close()


def test_optical_temperatures_agree_with_each_pages_own_text_except_three_flagged_source_conflicts(loaded):
    c = sqlite3.connect(str(loaded[0]))
    conflicts = set()
    for table, t in c.execute("SELECT raw_record_table, MIN(temperature_c) FROM optical_dispersion GROUP BY raw_record_table").fetchall():
        stated = matcher.temperature_c(yaml.safe_load(open(RI / table)).get("COMMENTS"))
        if stated is not None and t is not None and abs(t - stated) > 1.0:
            conflicts.add(table.split("/")[1].split(" - ")[1] + "/" + Path(table).stem)
    # Kozma 2005: these three pages say 22 degC in their text but 293 K in CONDITIONS; the paper's other pages say 295 K
    assert conflicts == {"ethanol/Kozma", "acetonitrile/Kozma", "dimethyl sulfoxide/Kozma"}
    for k in ("C2H5OH", "C2H3N", "C2H6OS"):
        assert "the page text says 22 degC but its CONDITIONS field says 19.85 degC" in ROW.loc[k, "flags"]
    t = dict(c.execute("SELECT dataset_label, MIN(temperature_c) FROM optical_dispersion o JOIN materials m USING(material_id) WHERE m.name='Water' GROUP BY 1"))
    assert t["amorphous ice | Kofman2019-10K"] == pytest.approx(-263.15) and t["supercooled liquid | Rowe2020-240K"] == pytest.approx(-33.15)
    c.close()


def test_reload_adds_zero_rows_and_changes_nothing(loaded, tmp_path):
    db = tmp_path / "copy.db"
    shutil.copy(loaded[0], db)
    dump = lambda p: {t: sqlite3.connect(str(p)).execute(f"SELECT * FROM {t} ORDER BY 1,2,3").fetchall() for t in ("materials", "sources", "optical_dispersion", "physical_properties")}
    before = dump(db)
    rep = fam.run_family("liquid", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties,
                         literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE,
                         literature_note=wrap.LITERATURE_NOTE, allow_null_formula=True)
    assert sum(rep.inserted.values()) == 0 and not rep.conflicts and dump(db) == before


@pytest.mark.parametrize("key,axis", AXES, ids=[f"{k}:{a['page']}" for k, a in AXES])
def test_every_dataset_is_preserved_row_by_row(loaded, key, axis):
    wl, n, *_ = fod.parse_file(RI / axis["data_path"])
    c = sqlite3.connect(str(loaded[0]))
    got = c.execute("SELECT raw_record_id, wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (axis["data_path"],)).fetchall()
    c.close()
    assert len(got) == len(wl) and all(g[0] == i and g[1] == pytest.approx(float(wl[i]), rel=1e-12) and g[2] == pytest.approx(float(n[i]), rel=1e-12) for i, g in enumerate(got))


def test_validation_finds_no_copied_dataset_except_segelsteins_compilation_of_hale_and_querry(loaded, tmp_path):
    db = tmp_path / "v.db"
    shutil.copy(loaded[0], db)
    c = sqlite3.connect(str(db))
    for (mid,) in c.execute("SELECT material_id FROM materials").fetchall():
        validate_optical_material(c, mid)
    same = c.execute("SELECT m.name, v.dataset_a, v.dataset_b FROM dataset_validation v JOIN materials m USING(material_id) WHERE v.rmse < 1e-9").fetchall()
    # Segelstein 1981's page says "(from Hale and Querry 1973)": over their common range it IS that data; both are published datasets
    assert {tuple(sorted(x[1:])) for x in same} <= {("liquid | Hale1973", "liquid | Segelstein1981")}
    c.close()


def test_every_material_with_a_density_exports_and_water_pairs_liquid_with_liquid(loaded, tmp_path):
    ok = {}
    for r in CAT.itertuples():
        try:
            ok[r.selection_key] = modalfit.export_layer(str(loaded[0]), r.name, nk_csv_dir=tmp_path / r.selection_key, label=r.name)
        except modalfit.ExportError:
            assert pd.isna(r.density_g_cm3), r.name
    assert len(ok) == 50
    assert ok["H2O"]["materials_db"]["optical_dataset_label"].startswith("liquid | ")
    assert ok["D2O"]["materials_db"]["optical_dataset_label"].startswith("liquid | ")
