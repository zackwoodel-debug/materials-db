"""Tests for the alloy and perovskite families (alloy_material_list.py, perovskite_material_list.py, their builders via
listed_family.py, and loaders). Independent checks: every page of every book is loaded or excluded; every formula is re-derived
from the page's own text (x in the comment or CONDITIONS, mol% converted); the recorded source conflicts are re-derived; n(633 nm)
falls monotonically with composition within each paper's series and lies between the end members; the o/e call of the doped
LiNbO3 / LiTaO3 pages follows their birefringence; the loaders reproduce parse_file and are idempotent."""
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

import alloy_material_list as alloys  # noqa: E402
import listed_family  # noqa: E402
import load_alloys_db as aw  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_perovskites_db as pw  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import perovskite_material_list as perov  # noqa: E402
from test_chalcogenide_pipeline import _hand_n  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database"
PAGES = listed_family.catalog_pages()
SEL = {**json.loads((DATA / "step1_selections_alloys.json").read_text()), **json.loads((DATA / "step1_selections_perovskites.json").read_text())}
LISTS = (alloys, perov)


def _yaml(path):
    return yaml.safe_load(open(RI / "data" / path))


def _text(s):
    return re.sub(r"<[^>]+>", "", str(s or "")).replace("−", "-")


def _amounts(formula):
    from pymatgen.core import Composition
    return {el.symbol: float(v) for el, v in Composition(formula).items()}


def test_every_page_of_every_book_is_loaded_or_excluded():
    for lst in LISTS:
        books = {(p["shelf"], p["book"]) for m in lst.MATERIALS for p in m["pages"]}
        loaded = {(p["shelf"], p["book"], p["page"]) for m in lst.MATERIALS for p in m["pages"]}
        for shelf, book in books:
            on_ri = {p for (sh, b, p) in PAGES if (sh, b) == (shelf, book)}
            got = {p for (sh, b, p) in loaded if (sh, b) == (shelf, book)} | {p for (sh, b, p) in lst.EXCLUDED_PAGES if (sh, b) == (shelf, book)}
            assert got == on_ri, (book, on_ri - got)


def _stated_x(axis):
    """The composition fraction the page itself states (its CONDITIONS x, else 'x = ...' / 'x=...' in its comment)."""
    d = _yaml(axis["data_path"])
    if (d.get("CONDITIONS") or {}).get("x") is not None:
        return float(d["CONDITIONS"]["x"])
    text = _text(d.get("COMMENTS"))
    m = re.search(r"\bx\s*=\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    f = _stated_formula(text)  # e.g. Perner: "Al0.929Ga0.071As"
    return _amounts(f)["Al"] if f and "Al" in f else None


FORMULA = re.compile(r"(?:[A-Z][a-z]?\d*(?:\.\d+)?)+")


def _stated_formula(text):
    """The first formula token with a fractional amount in the text (subscript tags already stripped)."""
    for tok in FORMULA.findall(text.replace(" ", "")):
        if re.search(r"\d\.\d", tok):
            return tok
    return None


@pytest.mark.parametrize("series,el", [("AlGaAs", "Al"), ("AlGaSb", "Al"), ("SiGe", "Si")])
def test_binary_alloy_formula_is_the_page_x(series, el):
    for key, v in SEL.items():
        if key.startswith(series + "@"):
            amounts = _amounts(v["formula"])
            for a in v["axes"]:
                x = _stated_x(a)
                assert x is not None and amounts[el] == pytest.approx(x, abs=1e-9), (key, a["page"], x)


def test_formula_written_on_the_page_is_the_formula():
    """ZnCdO, SiOx, GaInP, AgGaInS2, CsPb(Br,Cl)3: the page's comment writes the formula (subscripts); InGaAs gives x of Ga."""
    for key, v in SEL.items():
        if not re.match(r"(ZnCdO|SiOx|GaInP|AgGaInS2|CsPbX3@CsPbBr\d\.\d)", key):
            continue
        for a in v["axes"]:
            stated = _stated_formula(_text(_yaml(a["data_path"]).get("COMMENTS"))) or re.sub(r".*-SiO", "SiO", a["page"])
            assert _amounts(stated) == pytest.approx(_amounts(v["formula"])), (key, stated)
    for key, ga in (("InGaAs@x0.48", 0.48), ("InGaAs@x0.47", 0.47)):
        assert _amounts(SEL[key]["formula"])["Ga"] == ga == _stated_x(SEL[key]["axes"][0])


@pytest.mark.parametrize("key,oxide,y", [("YSZ@12mol", "Zr", 0.12), ("YSH@9.8mol", "Hf", 0.098)])
def test_stabilized_oxide_formula_is_the_stated_mol_percent(key, oxide, y):
    comment = _text(_yaml(SEL[key]["axes"][0]["data_path"]).get("COMMENTS"))
    assert f"{y * 100:.1f} mol" in comment
    assert _amounts(SEL[key]["formula"]) == pytest.approx({oxide: 1 - y, "Y": 2 * y, "O": 2 * (1 - y) + 3 * y})


def test_krs5_formula_is_the_stated_mol_percent():
    comment = _text(_yaml(SEL["KRS@KRS-5"]["axes"][0]["data_path"]).get("COMMENTS"))
    assert "45.7 M% of TlBr and 54.3 M% of TlI" in comment
    assert _amounts(SEL["KRS@KRS-5"]["formula"]) == pytest.approx({"Tl": 1.0, "Br": 0.457, "I": 0.543})


def test_recorded_source_conflicts_are_real():
    g90 = PAGES[("other", "AlAs-GaAs", "Gadras-90")][0]
    assert "90% Al" in PAGES[("other", "AlAs-GaAs", "Gadras-90")][1] and "x=0.92" in _text(_yaml(g90).get("COMMENTS")).replace(" ", "")
    j48 = next(a for a in SEL["SiGe@x0.48"]["axes"])
    d = _yaml(j48["data_path"])
    assert d["CONDITIONS"]["x"] == 0.48 and "x = 0.28" in _text(d["COMMENTS"])
    assert "(GaAs)" in _text(_yaml(PAGES[("other", "AlSb-GaSb", "Ferrini-0")][0]).get("COMMENTS"))


def test_end_members_are_excluded_and_exist_elsewhere():
    reg = json.loads((DATA / "material_registry.json").read_text())["materials"]
    for lst in LISTS:
        for ends in lst.SERIES_END_MEMBERS.values():
            assert all(k in reg for k in ends), ends
    ends_excluded = [k for k, why in alloys.EXCLUDED_PAGES.items() if why.startswith("end member")]
    assert len(ends_excluded) == 7


def _n633(axis):
    wl, n, *_ = fod.parse_file(RI / "data" / axis["data_path"])
    return float(np.interp(633.0, wl, n)) if wl.min() <= 633 <= wl.max() else None


@pytest.mark.parametrize("series,el,tag", [("AlGaAs", "Al", "Aspnes1986"), ("AlGaAs", "Al", "Papatryfonos2021"),
                                          ("AlGaSb", "Al", "Ferrini1998"), ("SiGe", "Si", "Jellison1993")])
def test_n633_falls_monotonically_with_composition_within_one_paper(series, el, tag):
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    pts = sorted((_amounts(v["formula"])[el], _n633(a)) for k, v in SEL.items() if k.startswith(series + "@")
                 for a in v["axes"] if a["tag"] == tag)
    ns = [n for _, n in pts if n is not None]
    assert len(ns) >= 3 and all(b < a for a, b in zip(ns, ns[1:])), pts


def test_alloys_lie_between_their_end_members():
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    gaas, alas = _hand_n("main/GaAs/nk/Aspnes.yml"), None
    for k, v in SEL.items():
        if k.startswith("AlGaAs@"):
            for a in v["axes"]:
                n = _n633(a)
                if n is not None and a["temperature_c"] is None:
                    assert 3.0 < n < gaas + 0.02, (k, a["page"], n)  # AlAs ~3.1 .. GaAs 3.86


def test_o_e_calls_follow_the_birefringence():
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    lt = {a["axis"]: a for a in SEL["Mg-LiTaO3@CLT-8mol"]["axes"]}
    for lam in (0.5, 1.0, 1.5):
        no = fod.eval_formula(next(b for b in _yaml(lt["o-ray"]["data_path"])["DATA"]), np.array([lam]))[0][0]
        ne = fod.eval_formula(next(b for b in _yaml(lt["e-ray"]["data_path"])["DATA"]), np.array([lam]))[0][0]
        assert no < ne  # LiTaO3: positive birefringence
    ln = {a["dataset_label"]: _n633(a) for a in SEL["MgO-LiNbO3@CLN-5mol"]["axes"]}
    assert ln["Zelmon1997 | o-ray"] > ln["Zelmon1997 | e-ray"] and ln["Gayer2008 | o-ray"] > ln["Gayer2008 | e-ray"]  # LiNbO3: negative


def test_formula_null_only_where_the_page_gives_no_exact_composition():
    for lst in LISTS:
        for m in lst.MATERIALS:
            if m["formula"] is None:
                assert m["note"] and "formula NULL" in m["note"] or m["series"] in ("ITO",), m["key"]


@pytest.fixture(scope="module", params=["alloy", "perovskite"])
def loaded(request, tmp_path_factory):
    wrap = aw if request.param == "alloy" else pw
    db = tmp_path_factory.mktemp(request.param) / "x.db"
    kw = dict(fresh=True, load_physical_fn=fam.load_physical_properties, literature_title=wrap.LITERATURE_TITLE,
              literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE, allow_null_formula=True)
    rep = fam.run_family(request.param, wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, **kw)
    return request.param, wrap, db, rep, kw


def test_loader_reproduces_parse_file_and_is_idempotent(loaded):
    name, wrap, db, rep, kw = loaded
    assert not rep.conflicts
    sel = json.loads(wrap.SELECTIONS_PATH.read_text())
    c = sqlite3.connect(str(db))
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    for v in sel.values():
        for a in v["axes"]:
            wl, n, *_ = fod.parse_file(RI / "data" / a["data_path"])
            got = c.execute("SELECT wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id",
                            (a["data_path"],)).fetchall()
            assert len(got) == len(wl) and np.allclose([g[1] for g in got], n, rtol=1e-12), a["data_path"]
    c.close()
    kw = dict(kw, fresh=False)
    again = fam.run_family(name, wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, **kw)
    assert sum(again.inserted.values()) == 0 and not again.conflicts


@pytest.mark.parametrize("key,a,b,pct", [("CuZn@Cu90", "Cu", "Zn", 90), ("CuZn@Cu85", "Cu", "Zn", 85), ("CuZn@Cu70", "Cu", "Zn", 70),
                                         ("NiFe@Ni80Fe20", "Ni", "Fe", 80)])
def test_metal_alloy_formula_and_the_atomic_vs_weight_bound(key, a, b, pct):
    """The page says '% Cu' / '% Ni' without atomic or weight; the formula is within 1 at.% of BOTH readings (that is why these
    alloys are loaded and Au-Ag, where the readings differ by up to 15 at.%, is not)."""
    from pymatgen.core import Element
    comment = _text(_yaml(SEL[key]["axes"][0]["data_path"]).get("COMMENTS"))
    assert f"{pct}% " in comment and f"{100 - pct}% " in comment
    na, nb = pct / Element(a).atomic_mass, (100 - pct) / Element(b).atomic_mass
    by_weight, by_atom = na / (na + nb), pct / 100
    x = _amounts(SEL[key]["formula"])[a]
    assert abs(x - by_weight) < 0.01 and abs(x - by_atom) < 0.01, (key, x, by_weight, by_atom)
    assert sum(_amounts(SEL[key]["formula"]).values()) == pytest.approx(1.0)


def test_au_ag_stays_deferred_because_the_readings_differ():
    from pymatgen.core import Element
    na, nb = 50 / Element("Au").atomic_mass, 50 / Element("Ag").atomic_mass
    assert abs(na / (na + nb) - 0.5) > 0.1 and not any(k.startswith("AuAg") for k in SEL)
