#!/usr/bin/env python3
"""
scripts/generate_ml_spectra.py
==============================
Spectral ML dataset from a release: one row per optical DATASET (material, variant/phase, axis, source, temperature) with its n and
k on one common wavelength grid, for models that predict or use whole spectra rather than n at 633 nm.

    python3 scripts/generate_ml_spectra.py [--release release/materials-db-vX.Y.Z]
    -> data/ML_release_spectra.parquet, data/ML_release_spectra_metadata.json

Grid: GRID_POINTS wavelengths log-spaced from GRID_MIN_NM to GRID_MAX_NM (in the metadata). Per dataset:
  * n, k are interpolated linearly in log-wavelength from the dataset's own points, only INSIDE its own range; repeated
    wavelengths are averaged; nothing is extrapolated or filled.
  * n_mask / k_mask say where a value is real. A grid point is masked where the dataset has no data, or where the two source
    points around it are more than MAX_GAP_RATIO apart in wavelength (no invented resolution between sparse points). Masked
    values are NaN. k is masked everywhere when the source gives no k.
  * Datasets with no unmasked n on the grid (entirely outside it) are not rows; they are listed in the metadata.
Context columns: stable key and permanent material_id, variant/phase, axis and source tag (from dataset_label), temperature,
measured vs model fit (dataset_kind.py), whether it is the material's primary dataset (as in the release's family tables), its
own wavelength range and point count. Groups for splitting: use material_id / key, never dataset rows, so axes, phases and
temperature series of one material stay together.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))
from dataset_kind import model_fit_reason  # noqa: E402
from generate_ml_release_set import latest_release, primary_pages  # noqa: E402
from release_validation import parse_label  # noqa: E402

OUT_PARQUET = _ROOT / "data" / "ML_release_spectra.parquet"
OUT_METADATA = _ROOT / "data" / "ML_release_spectra_metadata.json"
GRID_MIN_NM, GRID_MAX_NM, GRID_POINTS = 200.0, 25_000.0, 128
MAX_GAP_RATIO = 1.5
GRID = np.geomspace(GRID_MIN_NM, GRID_MAX_NM, GRID_POINTS)


def on_grid(wl, v, grid=GRID):
    """(values, mask) of one series on the grid: log-wavelength interpolation inside its own range, masked across gaps."""
    ok = ~np.isnan(v)
    wl, v = wl[ok], v[ok]
    out = np.full(grid.shape, np.nan)
    if len(wl) < 2:
        return out, np.zeros(grid.shape, bool)
    order = np.argsort(wl)
    wl, v = wl[order], v[order]
    uw, inv = np.unique(wl, return_inverse=True)  # repeated wavelengths (as some sources repeat them) are averaged
    uv = np.bincount(inv, weights=v) / np.bincount(inv)
    if len(uw) < 2:
        return out, np.zeros(grid.shape, bool)
    lw, lg = np.log(uw), np.log(grid)
    inside = (grid >= uw[0]) & (grid <= uw[-1])
    hi = np.clip(np.searchsorted(uw, grid), 1, len(uw) - 1)
    gap_ok = (uw[hi] / uw[hi - 1]) <= MAX_GAP_RATIO
    mask = inside & gap_ok
    out[mask] = np.interp(lg[mask], lw, uv)
    return out, mask


def build(release_dir):
    release_dir = Path(release_dir)
    db = next(release_dir.glob("materials-db-v*.sqlite"))
    con = sqlite3.connect(str(db))
    opt = pd.read_sql("SELECT material_id, dataset_label, raw_record_table, wavelength_nm, n, k, temperature_c FROM optical_dispersion", con)
    names = dict(con.execute("SELECT material_id, name FROM materials"))
    con.close()
    reg_csv = release_dir / "material_registry.csv"
    key_of = dict(pd.read_csv(reg_csv)[["material_id", "key"]].values) if reg_csv.exists() else {}
    primary = {name: path for name, (_, path) in primary_pages(release_dir).items()}
    rows, outside = [], []
    for (mid, label), g in opt.groupby(["material_id", "dataset_label"], sort=True):
        wl = g.wavelength_nm.to_numpy(float)
        n_vals, n_mask = on_grid(wl, g.n.to_numpy(float))
        k_vals, k_mask = on_grid(wl, g.k.to_numpy(float))
        tables = sorted(g.raw_record_table.unique())
        if not n_mask.any():
            outside.append(dict(material_id=int(mid), dataset_label=label, wl_min_nm=float(wl.min()), wl_max_nm=float(wl.max())))
            continue
        variant, tag, axis = parse_label(label)
        temps = g.temperature_c.dropna().unique()
        rows.append(dict(
            material_id=int(mid), key=key_of.get(mid), name=names[mid], dataset_label=label, variant_or_phase=variant, source_tag=tag,
            axis=axis, temperature_c=float(temps[0]) if len(temps) == 1 else np.nan, is_model_fit=model_fit_reason(tables[0]) is not None,
            is_primary=primary.get(names[mid]) in tables, source_file=tables[0], wl_min_nm=float(wl.min()), wl_max_nm=float(wl.max()),
            n_points=int(len(g)), n_grid_points=int(n_mask.sum()), k_grid_points=int(k_mask.sum()),
            n=n_vals.astype(np.float32), n_mask=n_mask, k=k_vals.astype(np.float32), k_mask=k_mask))
    return pd.DataFrame(rows), outside, db


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--release", type=Path, default=None)
    a = ap.parse_args(argv)
    rel = Path(a.release or latest_release())
    df, outside, db = build(rel)
    table = pa.Table.from_pandas(df.assign(n=df.n.map(list), k=df.k.map(list), n_mask=df.n_mask.map(list), k_mask=df.k_mask.map(list)),
                                 preserve_index=False)
    pq.write_table(table, str(OUT_PARQUET), compression="zstd")
    manifest = json.loads((rel / "MANIFEST.json").read_text())
    meta = dict(
        source_release=manifest["version"], source_release_git_commit=manifest["git_commit"], source_sqlite=db.name,
        source_sqlite_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
        grid=dict(unit="nm", spacing="log", min=GRID_MIN_NM, max=GRID_MAX_NM, points=GRID_POINTS, wavelengths_nm=GRID.round(6).tolist()),
        max_gap_ratio=MAX_GAP_RATIO, datasets=len(df), materials=int(df.material_id.nunique()),
        primary_datasets=int(df.is_primary.sum()), model_fit_datasets=int(df.is_model_fit.sum()),
        datasets_with_k=int((df.k_grid_points > 0).sum()), datasets_outside_grid=outside,
        notes=["One row per dataset; group by material_id (or key) when splitting.",
               "n / k are NaN where the mask is False: outside the dataset's own range or across a gap wider than max_gap_ratio.",
               "Interpolation is linear in log-wavelength between the source's own points; nothing is extrapolated."])
    OUT_METADATA.write_text(json.dumps(meta, indent=1) + "\n")
    print(f"{len(df)} datasets of {meta['materials']} materials on a {GRID_POINTS}-point grid ({GRID_MIN_NM:g}-{GRID_MAX_NM:g} nm); "
          f"{meta['datasets_with_k']} with k; {len(outside)} datasets entirely outside the grid; "
          f"-> {OUT_PARQUET.relative_to(_ROOT)} ({OUT_PARQUET.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
