"""Tests for the glass-catalog family (glass_catalog_list.py, build_glass_catalogs_csv.py via listed_family.py,
load_glass_catalogs_db.py) and its ML split classes. Independent checks: the manufacturer's Sellmeier formula reproduces the
datasheet's own nd and Vd (two separately stated numbers); every catalog page is loaded, skipped as another family's, or a
duplicate listing; the popular_glass pages are the catalog's own files; densities equal the datasheet's; negative k only where
the catalog's own table has it; optical equivalents share an ML split group across makers."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import generate_ml_splits as gs  # noqa: E402
import glass_catalog_list as gl  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database" / "data"
SEL = json.loads((DATA / "step1_selections_glass_catalogs.json").read_text())
CAT = pd.read_csv(DATA / "glass_catalogs.csv", dtype={"glass_code": str, "glass_code_from_nd": str}).set_index("selection_key")
GAPS = pd.read_csv(DATA / "glass_catalog_gaps.csv")
LINES = np.array([0.4861327, 0.5875618, 0.6562725])  # F, d, C (um)


def _page(key):
    return yaml.safe_load(open(RI / SEL[key]["axes"][0]["data_path"]))


def test_every_catalog_page_is_loaded_skipped_or_a_duplicate_listing():
    loaded = {a["data_path"] for v in SEL.values() for a in v["axes"]}
    skipped = set(GAPS[GAPS.gap_kind == "already_loaded"].key)
    for book in gl.BOOKS:
        for p in gl.catalog()[("specs", book)]:
            assert p["data"] in loaded or f"specs/{book}/{p['PAGE']}" in skipped, (book, p["PAGE"])
    assert len(SEL) == len(loaded) == 1675  # 17 pages are listed twice in the catalog (same file): loaded once


def test_popular_glass_pages_are_catalog_pages():
    catalog_files = {p["data"] for book in gl.BOOKS for p in gl.catalog()[("specs", book)]}
    for book, paths in gl.popular_equivalents().items():
        assert set(paths) <= catalog_files, book


def test_formula_reproduces_the_datasheet_nd_and_vd():
    """The Sellmeier coefficients and the datasheet's nd / Vd are separately stated: they agree to the datasheet's rounding
    (v0.20.0: 1622 glasses, |dnd| <= 3.8e-5, |dVd| <= 0.23)."""
    checked = 0
    for key in SEL:
        blk = [b for b in _page(key)["DATA"] if str(b["type"]).startswith("formula")]
        nd, vd = CAT.loc[key, "nd"], CAT.loc[key, "vd"]
        if not blk or pd.isna(nd):
            continue
        nF, n_d, nC = fod.eval_formula(blk[0], LINES)[0]
        assert abs(n_d - nd) < 1e-4 and abs((n_d - 1) / (nF - nC) - vd) < 0.5, key
        checked += 1
    assert checked >= 1600


def test_density_is_the_datasheet_value():
    n = 0
    for key in SEL:
        rho = (_page(key).get("PROPERTIES") or {}).get("density")
        if rho:
            assert CAT.loc[key, "density_g_cm3"] == pytest.approx(float(rho[0]["value"]) / 1000.0), key
            n += 1
        else:
            assert pd.isna(CAT.loc[key, "density_g_cm3"]), key
    assert n > 1500


def test_negative_k_only_where_the_catalog_table_has_it():
    import build_release as br
    negative = set()
    for key in SEL:
        for b in _page(key)["DATA"]:
            if b["type"] == "tabulated k" and (fod._parse_table(b["data"], 2)[:, 1] < 0).any():
                negative.add(CAT.loc[key, "name"])
    allowed = {name for name, _ in br.NEGATIVE_K_ALLOWED if name in set(CAT.name)}
    assert negative == allowed == {"HIKARI SK2", "HIKARI LAK09"}


def test_glass_code_is_the_datasheet_code():
    for key in SEL:
        props = _page(key).get("PROPERTIES") or {}
        c = CAT.loc[key, "glass_code"]
        if props.get("nd") is not None and props.get("Vd") is not None:
            assert c == gl.glass_code(props) and len(c) == 6, key
            own = gl.code_from_nd(props)
            agrees = abs(int(c[:3]) - int(own[:3])) <= 1 and abs(int(c[3:]) - int(own[3:])) <= 1
            moulding = CAT.loc[key, "name"].endswith("(M)") or key.startswith("OHARA-optical/L-") and key.endswith("P")
            assert agrees or moulding, key  # only moulding grades carry the base glass's code with post-moulding nd / Vd
            if not agrees:
                assert CAT.loc[key, "glass_code_from_nd"] == own, key


def test_equivalents_share_a_split_class_across_makers():
    classes = gs.glass_classes({f"glass_catalogs:{k}" for k in SEL})
    bk7 = {k for k, v in classes.items() if v == ("anchor", "glasses:N-BK7")}
    assert {"glass_catalogs:OHARA-optical/S-BSL7", "glass_catalogs:CDGM-optical/H-K9L", "glass_catalogs:HOYA-optical/BSC7",
            "glass_catalogs:SUMITA-optical/K-BK7", "glass_catalogs:HIKARI-optical/J-BK7A", "glass_catalogs:LZOS-optical/K8"} <= bk7
    by_code = {}
    for key, v in classes.items():
        c = CAT.loc[key.split(":", 1)[1], "glass_code"]
        if isinstance(c, str):
            by_code.setdefault(c, set()).add(v)
    assert all(len(v) == 1 for v in by_code.values())  # one glass code never spans two classes
