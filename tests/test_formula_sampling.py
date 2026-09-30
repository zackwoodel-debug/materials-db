"""fetch_optical_data.sample_formula (adaptive sampling of dispersion formulas) and scripts/resample_formula_data.py (moving the
tracked base DB and CSVs onto it). Interpolating the stored samples must reproduce the formula within the tolerance away from
poles, the tabulated k exactly at its own points, never produce a non-physical sample near a pole, and the tracked data must
already be on the new sampling."""
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import resample_formula_data as rs  # noqa: E402

RI = ROOT / "refractiveindex_db" / "database" / "data"
pytestmark = pytest.mark.skipif(not RI.exists(), reason="refractiveindex.info clone not present")


def _block(path):
    return next(b for b in yaml.safe_load(open(RI / path))["DATA"] if str(b["type"]).startswith("formula"))


def _range(block):
    return tuple(float(x) for x in str(block["wavelength_range"]).split())


@pytest.mark.parametrize("path", ["main/ZnTe/nk/Li.yml", "main/TlBr/nk/Palik.yml", "main/KBr/nk/Li.yml", "main/NaI/nk/Li.yml",
                                  "main/CsI/nk/Li.yml", "main/GaN/nk/Barker-o.yml", "main/SiO2/nk/Malitson.yml"])
def test_interpolation_between_samples_is_within_tolerance(path):
    b = _block(path)
    lo, hi = _range(b)
    lam, n, _ = fod.sample_formula(b, lo, hi)
    assert len(lam) >= fod.N_FORMULA and np.all(np.diff(lam) > 0) and lam[0] == pytest.approx(lo) and lam[-1] == pytest.approx(hi)
    chk = np.geomspace(lo, hi, 50_000)
    truth, _ = fod.eval_formula(b, chk)
    assert np.max(np.abs(np.interp(chk, lam, n) - truth)) <= 1.01 * fod.FORMULA_TOL


def test_633_nm_was_the_reason():
    """ZnTe Li1984: the old 500-point linear grid was 4e-3 off at 633 nm; now within the tolerance."""
    b = _block("main/ZnTe/nk/Li.yml")
    lo, hi = _range(b)
    exact = fod.eval_formula(b, np.array([0.633]))[0][0]
    old = np.linspace(lo, hi, 500)
    assert abs(np.interp(0.633, old, fod.eval_formula(b, old)[0]) - exact) > 1e-3
    lam, n, _ = fod.sample_formula(b, lo, hi)
    assert abs(np.interp(0.633, lam, n) - exact) < fod.FORMULA_TOL


def test_gas_refractivity_gets_a_relative_tolerance():
    for path in ["main/Ar/nk/Bideau-Mehu.yml", "main/He/nk/Mansfield.yml"]:
        b = _block(path)
        lo, hi = _range(b)
        lam, n, _ = fod.sample_formula(b, lo, hi)
        chk = np.geomspace(lo, hi, 20_000)
        truth, _ = fod.eval_formula(b, chk)
        rel = np.abs(np.interp(chk, lam, n) - truth) / np.abs(truth - 1)
        assert rel.max() <= 1.01 * fod.FORMULA_TOL_REL_NM1, path


@pytest.mark.parametrize("path", ["main/Xe/nk/Bideau-Mehu.yml", "main/GaSe/nk/Kato-o.yml", "main/GaSe/nk/Chen-n-o.yml"])
def test_poles_are_not_refined_into(path):
    """Next to a Sellmeier pole the formula diverges or gives n^2 <= 0: no sample there is refined, none is negative, and the
    sample count stays far from the cap."""
    b = _block(path)
    lo, hi = _range(b)
    with warnings.catch_warnings():
        warnings.simplefilter("error", fod.FormulaSamplingWarning)  # hitting the cap would raise
        lam, n, _ = fod.sample_formula(b, lo, hi)
    assert np.nanmin(n) > 0 and len(lam) < fod.FORMULA_MAX_POINTS / 2


def test_tabulated_k_is_reproduced_exactly_at_its_own_points():
    """A page with a formula n and a tabulated k stores k on the n samples; the table's own wavelengths are samples, so the
    stored k interpolates the table exactly (it used to be an interpolation of an interpolation: CCl4 k(633) 2.8% off)."""
    path = "organic/CCl4 - carbon tetrachloride/nk/Kedenburg.yml"
    raw = yaml.safe_load(open(RI / path))
    tab = fod._parse_table(next(b for b in raw["DATA"] if b["type"] == "tabulated k")["data"], 2)
    fod_window = fod.WL_MIN_NM, fod.WL_MAX_NM
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    try:
        wl, n, k, *_ = fod.parse_file(RI / path)
    finally:
        fod.WL_MIN_NM, fod.WL_MAX_NM = fod_window
    inside = (tab[:, 0] * 1000 >= wl[0]) & (tab[:, 0] * 1000 <= wl[-1])
    got = np.interp(tab[inside, 0] * 1000, wl, k)
    assert np.allclose(got, tab[inside, 1], rtol=1e-12, atol=0)


def test_include_um_only_adds_points():
    b = _block("main/SiO2/nk/Malitson.yml")
    lo, hi = _range(b)
    base = fod.sample_formula(b, lo, hi)[0]
    extra = np.array([0.5, 0.633, 1.55, hi * 2])  # the last is outside the range: ignored
    lam = fod.sample_formula(b, lo, hi, include_um=extra)[0]
    assert set(np.round(base, 12)) <= set(np.round(lam, 12)) and {0.5, 0.633, 1.55} <= set(lam) and lam.max() == pytest.approx(hi)


def test_tracked_data_is_on_the_new_sampling():
    """Nothing left to resample: the tracked base DB and every family CSV already match (the tool is idempotent).
    Exact on the reference platform (macOS arm64, docs/versioning.md); Linux differs in the last place for 62 CSV values."""
    db = rs.resample_db(rs.DEFAULT_DBS[0], apply=False)
    assert db["datasets"] == [] and len(db["already_new"]) == 98
    pages = rs.rf4._catalog_pages()
    for p in rs.DEFAULT_CSVS:
        assert rs.resample_csv(p, apply=False, pages=pages)["cells_updated"] == []
    for f, sel in rs.FAMILY_CSVS.items():
        out = rs.refresh_family_csv(ROOT / "data" / f"{f}.csv", ROOT / "data" / sel, apply=False)
        assert out["cells_updated"] == [] and out["flags_updated"] == [], f


def test_resample_db_replaces_only_old_grid_rows_and_refuses_the_unknown(tmp_path):
    src = sqlite3.connect(str(rs.DEFAULT_DBS[0]))
    schema = [r[0] for r in src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")]
    path = "main/ZnTe/nk/Li.yml"
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    with rs.old_sampling():
        wl, n, *_ = fod.parse_file(RI / path)

    def make(db, bump):
        con = sqlite3.connect(str(db))
        for s in schema:
            con.execute(s)
        con.execute("INSERT INTO materials(material_id, name, formula) VALUES(1, 'ZnTe', 'ZnTe')")
        con.execute("INSERT INTO sources(source_id, title) VALUES(1, 'Li1984')")
        con.executemany("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,temperature_c,dataset_label,raw_record_table,raw_record_id,source_id) "
                        "VALUES(1,?,?,NULL,NULL,'Li1984',?,?,1)", [(float(wl[i]), float(n[i]) + bump, path, i) for i in range(len(wl))])
        con.commit()
        con.close()

    good = tmp_path / "good.db"
    make(good, 0.0)
    dry = rs.resample_db(good, apply=False)
    assert len(dry["datasets"]) == 1 and sqlite3.connect(str(good)).execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == 500
    done = rs.resample_db(good, apply=True)
    new_wl = fod.parse_file(RI / path)[0]
    c = sqlite3.connect(str(good))
    assert c.execute("SELECT COUNT(*), MIN(dataset_label), MAX(dataset_label), MIN(source_id) FROM optical_dispersion").fetchone() == (len(new_wl), "Li1984", "Li1984", 1)
    c.close()
    assert done["datasets"][0]["rows_after"] == len(new_wl) and rs.resample_db(good, apply=True)["datasets"] == []  # idempotent

    stale = tmp_path / "stale.db"
    make(stale, 1e-3)  # rows that are neither the old grid nor the new sampling
    with pytest.raises(rs.ResampleError):
        rs.resample_db(stale, apply=True)
