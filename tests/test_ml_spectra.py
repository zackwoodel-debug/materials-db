"""scripts/generate_ml_spectra.py: the spectral ML dataset. Synthetic series check the grid rules (log interpolation inside the
dataset's own range only, gaps masked, repeated wavelengths averaged); the committed parquet is checked for shape, mask/NaN
consistency and one primary per material, and, when the release it was built from is present, recomputed independently."""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_ml_spectra as sp  # noqa: E402

DF = pd.read_parquet(sp.OUT_PARQUET)
META = json.loads(sp.OUT_METADATA.read_text())
RELEASE = ROOT / "release" / f"materials-db-v{META['source_release']}"
needs_release = pytest.mark.skipif(not RELEASE.exists(), reason=f"{RELEASE.name} not built locally")


def test_interpolation_is_logarithmic_and_only_inside_the_own_range():
    grid = np.array([100.0, 400.0, 800.0, 1600.0, 3200.0])
    v, m = sp.on_grid(np.array([400.0, 1600.0]), np.array([1.0, 3.0]), grid)
    assert not m.any()  # the only two points are 4x apart: no invented values between them
    v, m = sp.on_grid(np.array([400.0, 500.0, 640.0, 800.0]), np.array([1.0, 1.2, 1.4, 1.6]), grid)
    assert m.tolist() == [False, True, True, False, False] and np.isnan(v[0]) and np.isnan(v[3])
    assert v[1] == pytest.approx(1.0) and v[2] == pytest.approx(1.6)  # source points on the grid are kept exactly


def test_log_interpolation_value_and_repeated_wavelengths_averaged():
    grid = np.array([500.0])
    v, m = sp.on_grid(np.array([400.0, 400.0, 560.0]), np.array([1.0, 1.2, 2.1]), grid)  # 400 nm repeated: averaged to 1.1
    t = (np.log(500) - np.log(400)) / (np.log(560) - np.log(400))
    assert m[0] and v[0] == pytest.approx(1.1 + t * (2.1 - 1.1))


def test_missing_k_is_masked_not_zero():
    v, m = sp.on_grid(np.array([400.0, 500.0]), np.array([np.nan, np.nan]), np.array([450.0]))
    assert not m.any() and np.isnan(v).all()


def test_parquet_shape_masks_and_grid():
    assert np.allclose(META["grid"]["wavelengths_nm"], sp.GRID.round(6)) and META["datasets"] == len(DF)
    for col in ("n", "k", "n_mask", "k_mask"):
        assert DF[col].map(len).eq(sp.GRID_POINTS).all(), col
    for vals, mask in ((DF.n, DF.n_mask), (DF.k, DF.k_mask)):
        for v, m in zip(vals, mask):
            v, m = np.asarray(v, float), np.asarray(m, bool)
            assert np.isnan(v[~m]).all() and not np.isnan(v[m]).any()
    assert DF.n_mask.map(lambda m: np.asarray(m).any()).all()  # every row has data on the grid


def test_one_primary_per_material_and_keys_from_the_registry():
    prim = DF[DF.is_primary].groupby("material_id").size()
    assert prim.eq(1).all() and set(prim.index) == set(DF.material_id)
    reg = json.loads((ROOT / "data" / "material_registry.json").read_text())["materials"]
    ids = {v["id"]: k for k, v in reg.items()}
    assert (DF.key == DF.material_id.map(ids)).all()


@needs_release
def test_values_recomputed_independently_from_the_release():
    c = sqlite3.connect(str(next(RELEASE.glob("*.sqlite"))))
    sample = DF.sample(40, random_state=0)
    lg = np.log(sp.GRID)
    for r in sample.itertuples():
        pts = c.execute("SELECT wavelength_nm, n FROM optical_dispersion WHERE material_id=? AND dataset_label=? AND n IS NOT NULL",
                        (r.material_id, r.dataset_label)).fetchall()
        s = pd.DataFrame(pts, columns=["w", "n"]).groupby("w").n.mean().sort_index()
        m = np.asarray(r.n_mask)
        want = np.interp(lg[m], np.log(s.index.to_numpy()), s.to_numpy())
        assert np.allclose(np.asarray(r.n, float)[m], want, rtol=1e-5, atol=1e-6), r.dataset_label


@needs_release
def test_regenerates_identically():
    df, _, _ = sp.build(RELEASE)
    pd.testing.assert_frame_equal(df.drop(columns=["n", "k", "n_mask", "k_mask"]).reset_index(drop=True),
                                  DF.drop(columns=["n", "k", "n_mask", "k_mask"]).reset_index(drop=True), check_dtype=False)
    assert all(np.allclose(np.asarray(a, float), np.asarray(b, float), equal_nan=True) for a, b in zip(df.n, DF.n))
