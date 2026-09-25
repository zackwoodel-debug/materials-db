"""Regression tests for two shared-pipeline bugs found by independent cross-checks (not by the existing suite).

1. fetch_optical_data.eval_formula, RI.info "formula 4": the resonance denominator is (lambda^2 - C^q), not (lambda^q - C). The old form
   under-estimated n by up to ~0.5 (and mis-evaluated poles) in 37 datasets already stored in materials_oxide_test.db. Ground truth used here is
   physics, not the code: BBO's published indices (Eimerl 1987) and rutile TiO2 / ZnO / MgO at 633 nm.
2. scripts/build_oxides_csv.compute_sld stripped parentheses from the formula: CaMg(CO3)2 became CaMgCO32 (1 C, 32 O) and produced wrong SLDs.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_oxides_csv as pipeline  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402

RI = ROOT / "refractiveindex_db" / "database" / "data"


def official_formula4(c, lam):
    """n from the published formula 4; NaN where n^2 < 0 (no real index exists there)."""
    with np.errstate(invalid="ignore"):
        return np.sqrt(official_formula4_n2(c, lam))


def official_formula4_n2(c, lam):
    """n^2 of RefractiveIndex.INFO formula 4, written straight from its published definition (independent of the parser)."""
    l2 = lam * lam

    def group(B, p, C, q):  # B == 0 contributes exactly 0 (LuAG's all-zero second group has a 0/0 at 1.000 um)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(B == 0.0, 0.0, B * lam ** p / (l2 - C ** q))

    n2 = np.full_like(lam, c[0])
    if len(c) >= 5:
        n2 = n2 + group(*c[1:5])
    if len(c) >= 9:
        n2 = n2 + group(*c[5:9])
    for i in range(9, len(c) - 1, 2):
        n2 = n2 + c[i] * lam ** c[i + 1]
    return n2


def _block(rel):
    return next(b for b in yaml.safe_load(open(RI / rel))["DATA"] if b["type"] == "formula 4")


@pytest.mark.parametrize("axis,lam_um,expected", [("o", 0.5321, 1.6749), ("o", 1.0642, 1.6551), ("e", 0.5321, 1.5555), ("e", 1.0642, 1.5425)])
def test_formula4_reproduces_published_bbo_indices(axis, lam_um, expected):
    n = fod.eval_formula(_block(f"main/BaB2O4/nk/Eimerl-{axis}.yml"), np.array([lam_um]))[0][0]
    assert n == pytest.approx(expected, abs=5e-4)  # the old denominator gave 1.6649 / 1.5481 at 532 nm


@pytest.mark.parametrize("rel,expected,tol", [
    ("main/TiO2/nk/Devore-o.yml", 2.58, 0.01), ("main/TiO2/nk/Devore-e.yml", 2.87, 0.01),      # rutile n_o, n_e at 633 nm (old: 2.52 / 2.79)
    ("main/ZnO/nk/Bond-o.yml", 1.99, 0.02), ("main/ZnO/nk/Bond-e.yml", 2.00, 0.02),            # wurtzite (old: 2.53 / 2.55)
    ("main/MgO/nk/Stephens.yml", 1.7366, 0.01),                                                  # MgO, very well known (old: 1.722)
])
def test_formula4_reproduces_textbook_indices_at_633nm(rel, expected, tol):
    n = fod.eval_formula(_block(rel), np.array([0.633]))[0][0]
    assert n == pytest.approx(expected, abs=tol)


def _all_formula4_files():
    out = []
    for p in sorted(RI.rglob("*.yml")):
        if "formula 4" in p.read_text(errors="ignore"):
            out.append(p)
    return out


def test_formula4_equals_the_published_definition_for_every_local_file():
    files = _all_formula4_files()
    assert len(files) > 30, "expected many formula-4 files in the local RI.info clone"
    checked = floored = 0
    for p in files:
        for b in yaml.safe_load(open(p))["DATA"]:
            if b["type"] != "formula 4":
                continue
            lo, hi = [float(x) for x in b["wavelength_range"].split()]
            lam = np.linspace(lo, hi, 40)
            c = [float(x) for x in b["coefficients"].split()]
            n2 = official_formula4_n2(c, lam)
            got = fod.eval_formula(b, lam)[0]
            assert np.isfinite(n2).all() and np.isfinite(got).all(), f"{p.relative_to(RI)}: non-finite values must never pass a comparison"
            neg = n2 < 0  # e.g. GaSe near its ~41 um phonon band: no real index exists; the parser floors n to ~0 (documented, not hidden)
            floored += int(neg.sum())
            assert (got[neg] <= 1e-10).all(), p.relative_to(RI)
            assert np.allclose(got[~neg], np.sqrt(n2[~neg]), rtol=1e-9, atol=1e-12), p.relative_to(RI)
            checked += 1
    assert checked >= len(files)
    assert floored > 0, "expected the GaSe far-IR points where n^2 < 0 (a floored n is not a physical index: loaders should flag it)"


def test_compute_sld_keeps_parentheses_so_dolomite_is_not_CaMgCO32():
    a = pipeline.compute_sld("CaMg(CO3)2", 2.87)
    b = pipeline.compute_sld("CaMgC2O6", 2.87)  # the same compound written flat
    for k in ("xray_sld_real", "xray_sld_imag", "neutron_sld_real", "neutron_sld_imag"):
        assert a[k] == pytest.approx(b[k], rel=1e-12)
    assert a["xray_sld_real"] == pytest.approx(24.54, abs=0.02)  # the buggy CaMgCO32 gave 24.52 / neutron 5.947 (vs the correct 5.454)
    assert a["neutron_sld_real"] == pytest.approx(5.454, abs=0.01)
    c = pipeline.compute_sld("LuAl3(BO3)4", 3.0)
    d = pipeline.compute_sld("LuAl3B4O12", 3.0)
    assert c["neutron_sld_real"] == pytest.approx(d["neutron_sld_real"], rel=1e-12)
