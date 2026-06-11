"""
Populate dataset_validation and spectral_validation for materials_normalized.db.

Scalar comparisons  → dataset_validation (existing table, currently empty)
Spectral comparisons → spectral_validation (new table, created here)
Anomaly flags        → spectral_anomalies  (new table, created here)

Raw measurements are NEVER modified.
"""

import json
import math
import sqlite3
import textwrap
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import NamedTuple

import numpy as np
from scipy import stats, interpolate

DB_PATH = Path(__file__).parent.parent / "data" / "materials_normalized.db"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── Classification thresholds ────────────────────────────────────────────────

def classify_scalar(rel_error_pct: float) -> str:
    """Classify based on percent relative error between two scalar values."""
    a = abs(rel_error_pct)
    if a < 2.0:
        return "excellent"
    if a < 10.0:
        return "warning"
    return "suspicious"


def classify_spectral(pearson_r: float | None, rmse: float,
                      n_points: int, signal_range: float) -> str:
    if n_points < 3:
        # Too few points for r; classify by normalised RMSE only
        nrmse = rmse / signal_range if signal_range > 0 else float("inf")
        if nrmse < 0.01:
            return "excellent"
        if nrmse < 0.05:
            return "warning"
        return "suspicious"
    if pearson_r is None:
        return "suspicious"
    if pearson_r > 0.9999 and rmse / max(signal_range, 1e-12) < 0.01:
        return "excellent"
    if pearson_r > 0.999:
        return "warning"
    return "suspicious"


# ── DB schema helpers ────────────────────────────────────────────────────────

def setup_new_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS spectral_validation (
            sv_id            INTEGER PRIMARY KEY,
            material_id      INTEGER NOT NULL REFERENCES materials(material_id),
            property         TEXT    NOT NULL,
            dataset_a        TEXT    NOT NULL,
            dataset_b        TEXT    NOT NULL,
            overlap_wl_min   REAL,
            overlap_wl_max   REAL,
            n_overlap_points INTEGER,
            pearson_r        REAL,
            rmse             REAL,
            mae              REAL,
            max_deviation    REAL,
            classification   TEXT,
            notes            TEXT,
            UNIQUE(material_id, property, dataset_a, dataset_b)
        );

        CREATE TABLE IF NOT EXISTS spectral_anomalies (
            anomaly_id    INTEGER PRIMARY KEY,
            material_id   INTEGER NOT NULL REFERENCES materials(material_id),
            dataset_label TEXT    NOT NULL,
            property      TEXT    NOT NULL,
            anomaly_type  TEXT    NOT NULL,
            severity      TEXT    NOT NULL,
            details       TEXT,
            UNIQUE(material_id, dataset_label, property, anomaly_type)
        );
    """)
    # Purge stale rows so re-runs are idempotent
    con.execute("DELETE FROM dataset_validation")
    con.execute("DELETE FROM spectral_validation")
    con.execute("DELETE FROM spectral_anomalies")
    con.commit()


# ── Maths helpers ────────────────────────────────────────────────────────────

def rel_error_pct(a: float, b: float) -> float:
    """Percent relative error, mid-point normalised. Returns NaN if both zero."""
    mid = (abs(a) + abs(b)) / 2.0
    if mid == 0:
        return 0.0
    return (a - b) / mid * 100.0


def pairwise_spectral(
    wl_a: np.ndarray, vals_a: np.ndarray,
    wl_b: np.ndarray, vals_b: np.ndarray,
    min_overlap_nm: float = 0.0,
) -> dict:
    """
    Interpolate both arrays onto a common wavelength grid and compute
    spectral agreement metrics.

    Returns dict with keys:
        overlap_wl_min, overlap_wl_max, n_overlap_points,
        pearson_r, rmse, mae, max_deviation, signal_range
    or empty dict if no overlap.
    """
    lo = max(wl_a.min(), wl_b.min())
    hi = min(wl_a.max(), wl_b.max())
    if hi - lo < min_overlap_nm:
        return {}

    # Build common grid: union of both grids, clipped to overlap, then sorted + unique
    grid = np.unique(np.concatenate([
        wl_a[(wl_a >= lo) & (wl_a <= hi)],
        wl_b[(wl_b >= lo) & (wl_b <= hi)],
    ]))
    if len(grid) < 1:
        return {}

    # Linear interpolation (linear is safest for n/k; spectra are smooth)
    def interp_safe(wl_src, vals_src, grid_out):
        if len(wl_src) == 1:
            # single-point: constant extrapolation
            return np.full(len(grid_out), vals_src[0])
        f = interpolate.interp1d(wl_src, vals_src, kind="linear",
                                 bounds_error=False, fill_value="extrapolate")
        return f(grid_out)

    va = interp_safe(wl_a, vals_a, grid)
    vb = interp_safe(wl_b, vals_b, grid)

    diff = va - vb
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    mae = float(np.mean(np.abs(diff)))
    max_dev = float(np.max(np.abs(diff)))
    signal_range = float(max(np.ptp(va), np.ptp(vb), abs(np.mean(va)), 1e-12))

    pearson_r = None
    if len(grid) >= 3 and np.std(va) > 0 and np.std(vb) > 0:
        r, _ = stats.pearsonr(va, vb)
        pearson_r = float(r)

    return {
        "overlap_wl_min": float(lo),
        "overlap_wl_max": float(hi),
        "n_overlap_points": int(len(grid)),
        "pearson_r": pearson_r,
        "rmse": rmse,
        "mae": mae,
        "max_deviation": max_dev,
        "signal_range": signal_range,
    }


# ── Scalar validation ────────────────────────────────────────────────────────

def run_scalar_validation(con: sqlite3.Connection) -> int:
    """
    Compare scalar property values across dataset_labels in physical_properties.
    Returns number of rows inserted into dataset_validation.
    """
    n_inserted = 0
    mat_name = dict(con.execute("SELECT material_id, name FROM materials").fetchall())

    # Properties to compare across dataset_labels
    scalar_props = [
        ("xray_sld",           "xray_sld"),
        ("neutron_sld",        "neutron_sld"),
        ("dielectric_constant","dielectric_constant"),
        ("density_g_cm3",      "density_g_cm3"),
    ]

    for col, prop_name in scalar_props:
        # Aggregate to one representative value per (material, dataset_label).
        # For SLD-type columns the value is constant across wavelengths; for dielectric
        # we take the first distinct (value, temp, freq) tuple per label.
        agg_rows = con.execute(f"""
            SELECT material_id, dataset_label,
                   {col}, temperature_c, frequency_hz
            FROM physical_properties
            WHERE {col} IS NOT NULL
            GROUP BY material_id, dataset_label, {col}, temperature_c, frequency_hz
            ORDER BY material_id, dataset_label
        """).fetchall()

        # Build: { material_id: [ {label, value, temp, freq}, ... ] }
        # Keep only one entry per (material, label, value) — use the first.
        seen: set[tuple] = set()
        by_mat: dict[int, list] = {}
        for mid, dlabel, val, temp, freq in agg_rows:
            key = (mid, dlabel, val)
            if key in seen:
                continue
            seen.add(key)
            by_mat.setdefault(mid, []).append(
                {"label": dlabel or "(unlabelled)",
                 "value": val, "temp": temp, "freq": freq}
            )

        for mid, entries in by_mat.items():
            # Only compare DIFFERENT dataset labels
            distinct_labels = {}
            for e in entries:
                distinct_labels.setdefault(e["label"], []).append(e)

            label_list = list(distinct_labels.keys())
            if len(label_list) < 2:
                continue

            for la, lb in combinations(label_list, 2):
                # Use the first representative entry per label
                e_a = distinct_labels[la][0]
                e_b = distinct_labels[lb][0]

                # Condition mismatch notes
                cond_notes = []
                if e_a["temp"] != e_b["temp"] and None not in (e_a["temp"], e_b["temp"]):
                    cond_notes.append(f"temp: {e_a['temp']}°C vs {e_b['temp']}°C")
                if e_a["freq"] != e_b["freq"] and None not in (e_a["freq"], e_b["freq"]):
                    cond_notes.append(
                        f"freq: {e_a['freq']:.3g} vs {e_b['freq']:.3g} Hz"
                    )

                re_pct = rel_error_pct(e_a["value"], e_b["value"])
                cls = classify_scalar(re_pct)
                if cond_notes and cls == "excellent" and abs(re_pct) < 2.0:
                    cls = "warning"

                notes_parts = [f"rel_err={re_pct:+.2f}%"]
                if cond_notes:
                    notes_parts.append("conditions differ: " + "; ".join(cond_notes))

                rmse = abs(e_a["value"] - e_b["value"])

                try:
                    con.execute("""
                        INSERT OR IGNORE INTO dataset_validation
                          (material_id, property_name, dataset_a, dataset_b,
                           pearson_r, rmse, mean_relative_error, classification, notes)
                        VALUES (?,?,?,?,NULL,?,?,?,?)
                    """, (mid, prop_name, la, lb,
                          rmse, re_pct, cls, "; ".join(notes_parts)))
                    n_inserted += 1
                except sqlite3.IntegrityError:
                    pass

    con.commit()
    return n_inserted


# ── Spectral validation ──────────────────────────────────────────────────────

def _short_label(raw_label: str | None, max_len: int = 80) -> str:
    """Truncate long HTML-laden dataset labels to first line."""
    if not raw_label:
        return "(unlabelled)"
    first_line = raw_label.strip().split("\n")[0].strip()
    return first_line[:max_len] + ("…" if len(first_line) > max_len else "")


def run_spectral_validation(con: sqlite3.Connection) -> int:
    """
    Compare n and k spectra across dataset pairs for each material.
    Returns number of rows inserted into spectral_validation.
    """
    n_inserted = 0

    # Materials with ≥2 distinct dataset_labels (NULL counts as its own label)
    multi_mat = con.execute("""
        SELECT material_id,
               COUNT(DISTINCT COALESCE(dataset_label, '__NULL__')) as nd
        FROM optical_dispersion
        GROUP BY material_id HAVING nd >= 2
    """).fetchall()

    for mid, _ in multi_mat:
        # Fetch all datasets for this material; coerce NULL label to sentinel
        datasets: dict[str, dict] = {}
        rows = con.execute("""
            SELECT COALESCE(dataset_label, '(unlabelled)'),
                   wavelength_nm, n, k
            FROM optical_dispersion
            WHERE material_id = ?
            ORDER BY COALESCE(dataset_label, '(unlabelled)'), wavelength_nm
        """, (mid,)).fetchall()

        for label, wl, n_val, k_val in rows:
            ds = datasets.setdefault(label, {"wl": [], "n": [], "k": []})
            ds["wl"].append(wl)
            ds["n"].append(n_val)
            ds["k"].append(k_val)

        label_list = list(datasets.keys())

        for la, lb in combinations(label_list, 2):
            ds_a = datasets[la]
            ds_b = datasets[lb]
            wl_a = np.array(ds_a["wl"], dtype=float)
            wl_b = np.array(ds_b["wl"], dtype=float)

            short_a = _short_label(la)
            short_b = _short_label(lb)

            for prop in ("n", "k"):
                vals_a_raw = ds_a[prop]
                vals_b_raw = ds_b[prop]

                # Skip if either dataset has no values for this property
                has_a = any(v is not None for v in vals_a_raw)
                has_b = any(v is not None for v in vals_b_raw)
                if not has_a or not has_b:
                    continue

                # Filter to non-null pairs
                mask_a = np.array([v is not None for v in vals_a_raw])
                mask_b = np.array([v is not None for v in vals_b_raw])
                wl_a_f = wl_a[mask_a]
                wl_b_f = wl_b[mask_b]
                va = np.array([v for v in vals_a_raw if v is not None], dtype=float)
                vb = np.array([v for v in vals_b_raw if v is not None], dtype=float)

                metrics = pairwise_spectral(wl_a_f, va, wl_b_f, vb)

                if not metrics:
                    notes = "no overlapping wavelength range"
                    cls = None
                    try:
                        con.execute("""
                            INSERT OR IGNORE INTO spectral_validation
                              (material_id, property, dataset_a, dataset_b,
                               overlap_wl_min, overlap_wl_max, n_overlap_points,
                               pearson_r, rmse, mae, max_deviation, classification, notes)
                            VALUES (?,?,?,?,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,?)
                        """, (mid, prop, short_a, short_b, notes))
                        n_inserted += 1
                    except sqlite3.IntegrityError:
                        pass
                    continue

                sig_range = metrics.pop("signal_range")
                cls = classify_spectral(
                    metrics["pearson_r"], metrics["rmse"],
                    metrics["n_overlap_points"], sig_range
                )

                notes_parts = [
                    f"{metrics['n_overlap_points']} overlap points "
                    f"[{metrics['overlap_wl_min']:.1f}–{metrics['overlap_wl_max']:.1f} nm]"
                ]
                if metrics["pearson_r"] is not None:
                    notes_parts.append(f"r={metrics['pearson_r']:.6f}")

                try:
                    con.execute("""
                        INSERT OR IGNORE INTO spectral_validation
                          (material_id, property, dataset_a, dataset_b,
                           overlap_wl_min, overlap_wl_max, n_overlap_points,
                           pearson_r, rmse, mae, max_deviation, classification, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        mid, prop, short_a, short_b,
                        metrics["overlap_wl_min"], metrics["overlap_wl_max"],
                        metrics["n_overlap_points"],
                        metrics["pearson_r"], metrics["rmse"],
                        metrics["mae"], metrics["max_deviation"],
                        cls, "; ".join(notes_parts)
                    ))
                    n_inserted += 1
                except sqlite3.IntegrityError:
                    pass

    con.commit()
    return n_inserted


# ── Anomaly detection ────────────────────────────────────────────────────────

def detect_spectral_anomalies(con: sqlite3.Connection) -> int:
    """
    Scan optical_dispersion per (material_id, dataset_label) for anomalies.
    Returns number of rows inserted into spectral_anomalies.
    """
    n_inserted = 0

    # Fetch per-dataset data using individual queries to avoid GROUP_CONCAT NULL issues
    mat_datasets = con.execute("""
        SELECT DISTINCT material_id, dataset_label
        FROM optical_dispersion
        ORDER BY material_id, dataset_label
    """).fetchall()

    def _insert(mid, dlabel, prop, atype, severity, details):
        nonlocal n_inserted
        short = _short_label(dlabel)
        try:
            con.execute("""
                INSERT OR IGNORE INTO spectral_anomalies
                  (material_id, dataset_label, property, anomaly_type, severity, details)
                VALUES (?,?,?,?,?,?)
            """, (mid, short, prop, atype, severity, details))
            n_inserted += 1
        except sqlite3.IntegrityError:
            pass

    for mid, dlabel in mat_datasets:
        rows = con.execute(
            "SELECT wavelength_nm, n, k FROM optical_dispersion "
            "WHERE material_id=? AND dataset_label=? ORDER BY wavelength_nm",
            (mid, dlabel)
        ).fetchall()
        if not rows:
            continue
        wls = np.array([r[0] for r in rows], dtype=float)
        ns_raw = [r[1] for r in rows]
        ks_raw = [r[2] for r in rows]

        # 1. Duplicate wavelengths (within this dataset/material)
        unique_wls, counts = np.unique(wls, return_counts=True)
        dups = unique_wls[counts > 1]
        if len(dups):
            _insert(mid, dlabel, "wavelength", "duplicate_wavelength", "critical",
                    f"Duplicate wavelengths: {dups.tolist()}")

        # 2. Non-monotonic wavelength grid
        if not np.all(np.diff(wls) > 0):
            bad_idx = np.where(np.diff(wls) <= 0)[0]
            _insert(mid, dlabel, "wavelength", "non_monotonic_grid", "warning",
                    f"Non-monotonic at indices {bad_idx.tolist()} "
                    f"(wl={wls[bad_idx].tolist()})")

        # 3. Sparse wavelength coverage (< 5 points)
        if len(wls) < 5:
            _insert(mid, dlabel, "wavelength", "sparse_coverage", "warning",
                    f"Only {len(wls)} wavelength point(s)")

        # 4. Discontinuities (gap > 10× median step)
        if len(wls) >= 3:
            steps = np.diff(wls)
            med_step = float(np.median(steps))
            if med_step > 0:
                big_gaps = np.where(steps > 10 * med_step)[0]
                if len(big_gaps):
                    _insert(mid, dlabel, "wavelength", "discontinuity", "warning",
                            f"Large gap(s) at indices {big_gaps.tolist()}: "
                            f"{steps[big_gaps].tolist()} nm "
                            f"(median step={med_step:.1f} nm)")

        # Per-property checks
        for prop, vals_raw in (("n", ns_raw), ("k", ks_raw)):
            vals = [v for v in vals_raw if v is not None]
            if not vals:
                continue

            arr = np.array(vals, dtype=float)

            # 5. Zero-variance spectrum (all identical values)
            if np.ptp(arr) == 0 and len(arr) > 2:
                _insert(mid, dlabel, prop, "zero_variance", "warning",
                        f"All {prop} values identical: {arr[0]:.6g} "
                        f"across {len(arr)} points")

            # 6. Physical range check: n must be > 0; k ≥ 0
            if prop == "n" and np.any(arr <= 0):
                bad = arr[arr <= 0].tolist()
                _insert(mid, dlabel, prop, "unphysical_value", "critical",
                        f"n ≤ 0: {bad}")
            if prop == "k" and np.any(arr < 0):
                bad = arr[arr < 0].tolist()
                _insert(mid, dlabel, prop, "unphysical_value", "critical",
                        f"k < 0: {bad}")

    # 7. Duplicate spectrum pairs (different labels, same material, very close values)
    mat_ids = [r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM optical_dispersion"
    ).fetchall()]

    for mid in mat_ids:
        labels = [r[0] for r in con.execute(
            "SELECT DISTINCT dataset_label FROM optical_dispersion WHERE material_id=?",
            (mid,)
        ).fetchall()]
        if len(labels) < 2:
            continue
        # Collect full (wavelength, n) fingerprints per label
        spectra: dict[str, np.ndarray] = {}
        for lab in labels:
            pts = con.execute(
                "SELECT wavelength_nm, n FROM optical_dispersion "
                "WHERE material_id=? AND dataset_label=? "
                "AND n IS NOT NULL ORDER BY wavelength_nm",
                (mid, lab)
            ).fetchall()
            if pts:
                spectra[lab] = np.array(pts, dtype=float)

        for la, lb in combinations(spectra.keys(), 2):
            sa, sb = spectra[la], spectra[lb]
            # Only compare if they share the exact same wavelength grid
            if sa.shape == sb.shape and np.allclose(sa[:, 0], sb[:, 0], rtol=0, atol=0.01):
                if np.allclose(sa[:, 1], sb[:, 1], rtol=1e-4, atol=1e-6):
                    short_a = _short_label(la)
                    short_b = _short_label(lb)
                    _insert(mid, la, "n", "duplicate_spectrum", "warning",
                            f"Nearly identical n spectrum with: {short_b[:60]}")

    con.commit()
    return n_inserted


# ── Report generation ────────────────────────────────────────────────────────

def _fmt(v, digits=4):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}g}"
    return str(v)


def generate_reports(con: sqlite3.Connection) -> None:
    mat_name = dict(con.execute("SELECT material_id, name FROM materials").fetchall())

    # ── dataset_validation.csv ──────────────────────────────────────────
    dv_rows = con.execute("""
        SELECT validation_id, material_id, property_name, dataset_a, dataset_b,
               pearson_r, rmse, mean_relative_error, classification, notes
        FROM dataset_validation ORDER BY material_id, property_name
    """).fetchall()

    lines = ["validation_id,material_id,material_name,property_name,dataset_a,dataset_b,"
             "pearson_r,rmse,mean_relative_error,classification,notes"]
    for r in dv_rows:
        vid, mid, pname, da, db, pr, rmse, mre, cls, notes = r
        lines.append(",".join([
            str(vid), str(mid), _csv(mat_name.get(mid, "")),
            _csv(pname), _csv(da), _csv(db),
            _fmt(pr), _fmt(rmse), _fmt(mre), _csv(cls or ""), _csv(notes or "")
        ]))
    (REPORTS_DIR / "dataset_validation.csv").write_text("\n".join(lines) + "\n")

    # ── spectral_validation.csv ─────────────────────────────────────────
    sv_rows = con.execute("""
        SELECT sv_id, material_id, property, dataset_a, dataset_b,
               overlap_wl_min, overlap_wl_max, n_overlap_points,
               pearson_r, rmse, mae, max_deviation, classification, notes
        FROM spectral_validation ORDER BY material_id, property
    """).fetchall()

    lines = ["sv_id,material_id,material_name,property,dataset_a,dataset_b,"
             "overlap_wl_min,overlap_wl_max,n_overlap_points,"
             "pearson_r,rmse,mae,max_deviation,classification,notes"]
    for r in sv_rows:
        svid, mid, prop, da, db, wlo, whi, np_, pr, rmse, mae, mxd, cls, notes = r
        lines.append(",".join([
            str(svid), str(mid), _csv(mat_name.get(mid, "")),
            _csv(prop), _csv(da), _csv(db),
            _fmt(wlo), _fmt(whi), str(np_ or 0),
            _fmt(pr), _fmt(rmse), _fmt(mae), _fmt(mxd),
            _csv(cls or ""), _csv(notes or "")
        ]))
    (REPORTS_DIR / "spectral_validation.csv").write_text("\n".join(lines) + "\n")

    # ── dataset_similarity_report.md ────────────────────────────────────
    lines = [
        "# Dataset Similarity Report",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "Scalar property comparisons across measurement sources.",
        "",
        "## Classification key",
        "| Class | Criterion |",
        "|-------|-----------|",
        "| excellent | \\|rel_error\\| < 2% |",
        "| warning   | \\|rel_error\\| < 10% |",
        "| suspicious | \\|rel_error\\| ≥ 10% |",
        "",
        "## Summary",
    ]

    cls_counts: dict[str, int] = {}
    for r in dv_rows:
        c = r[8] or "unknown"
        cls_counts[c] = cls_counts.get(c, 0) + 1
    lines += [
        f"| Class | Count |",
        f"|-------|-------|",
        *[f"| {k} | {v} |" for k, v in sorted(cls_counts.items())],
        "",
        "## Per-Property Results",
        "",
    ]

    # Group by property
    by_prop: dict[str, list] = {}
    for r in dv_rows:
        by_prop.setdefault(r[2], []).append(r)

    for prop, rows in sorted(by_prop.items()):
        lines.append(f"### `{prop}`")
        lines.append("")
        lines.append("| Material | Dataset A | Dataset B | Rel Error % | RMSE | Class | Notes |")
        lines.append("|----------|-----------|-----------|-------------|------|-------|-------|")
        for r in rows:
            vid, mid, pname, da, db, pr, rmse, mre, cls, notes = r
            lines.append(
                f"| {mat_name.get(mid, mid)} "
                f"| {da[:50]} | {db[:50]} "
                f"| {_fmt(mre, 3)} | {_fmt(rmse)} "
                f"| {cls or '—'} | {(notes or '')[:80]} |"
            )
        lines.append("")

    (REPORTS_DIR / "dataset_similarity_report.md").write_text("\n".join(lines) + "\n")
    print(f"  Wrote reports/dataset_similarity_report.md")
    print(f"  Wrote reports/dataset_validation.csv ({len(dv_rows)} rows)")

    # ── spectral_validation_report.md ──────────────────────────────────
    an_rows = con.execute("""
        SELECT anomaly_id, material_id, dataset_label, property,
               anomaly_type, severity, details
        FROM spectral_anomalies ORDER BY material_id, severity DESC
    """).fetchall()

    lines = [
        "# Spectral Validation Report",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "Inter-dataset spectral comparisons and per-dataset quality flags.",
        "",
        "## Classification key",
        "| Class | Criterion |",
        "|-------|-----------|",
        "| excellent | Pearson r > 0.9999 AND nRMSE < 1% (or nRMSE < 1% for sparse) |",
        "| warning   | r > 0.999 (or nRMSE < 5%) |",
        "| suspicious | otherwise |",
        "",
        "## Inter-Dataset Comparisons",
        "",
    ]

    # Group by material
    by_mat_sv: dict[int, list] = {}
    for r in sv_rows:
        by_mat_sv.setdefault(r[1], []).append(r)

    for mid in sorted(by_mat_sv.keys()):
        lines.append(f"### {mat_name.get(mid, mid)} (material_id={mid})")
        lines.append("")
        lines.append(
            "| Property | Dataset A | Dataset B "
            "| WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |"
        )
        lines.append(
            "|----------|-----------|-----------|"
            "---------------|--------|-----------|------|-----|---------|-------|"
        )
        for r in by_mat_sv[mid]:
            svid, mid_, prop, da, db, wlo, whi, np_, pr, rmse, mae, mxd, cls, notes = r
            wlrange = f"{_fmt(wlo)}–{_fmt(whi)}" if wlo is not None else "—"
            lines.append(
                f"| {prop} | {da[:45]} | {db[:45]} "
                f"| {wlrange} | {np_ or 0} "
                f"| {_fmt(pr, 6)} | {_fmt(rmse)} | {_fmt(mae)} | {_fmt(mxd)} "
                f"| {cls or '—'} |"
            )
        lines.append("")

    # Anomaly section
    lines += [
        "## Per-Dataset Anomaly Flags",
        "",
    ]

    cls_an: dict[str, int] = {}
    for r in an_rows:
        c = r[5]
        cls_an[c] = cls_an.get(c, 0) + 1

    lines += [
        f"Total anomalies: {len(an_rows)} "
        f"({cls_an.get('critical', 0)} critical, {cls_an.get('warning', 0)} warning)",
        "",
        "| Material | Dataset (truncated) | Property | Type | Severity | Details |",
        "|----------|---------------------|----------|------|----------|---------|",
    ]
    for r in an_rows:
        aid, mid, dlabel, prop, atype, severity, details = r
        lines.append(
            f"| {mat_name.get(mid, mid)} | {dlabel[:40]} "
            f"| {prop} | {atype} | **{severity}** "
            f"| {(details or '')[:80]} |"
        )
    lines.append("")

    # Overall DB statistics section
    n_dv = len(dv_rows)
    n_sv = len(sv_rows)
    n_excellent_dv = sum(1 for r in dv_rows if r[8] == "excellent")
    n_excellent_sv = sum(1 for r in sv_rows if r[12] == "excellent")
    n_no_overlap = sum(1 for r in sv_rows if r[7] == 0 or r[7] is None)
    n_mats_compared = len(by_mat_sv)

    lines += [
        "## Overall Database Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Scalar property comparison pairs | {n_dv} |",
        f"| Spectral comparison pairs | {n_sv} |",
        f"| Spectral pairs with overlap | {n_sv - n_no_overlap} |",
        f"| Spectral pairs — no overlap | {n_no_overlap} |",
        f"| Materials with spectral comparisons | {n_mats_compared} |",
        f"| Scalar excellent | {n_excellent_dv} |",
        f"| Spectral excellent | {n_excellent_sv} |",
        f"| Anomalies detected | {len(an_rows)} |",
        f"| Critical anomalies | {cls_an.get('critical', 0)} |",
        "",
    ]

    (REPORTS_DIR / "spectral_validation_report.md").write_text("\n".join(lines) + "\n")
    print(f"  Wrote reports/spectral_validation_report.md")
    print(f"  Wrote reports/spectral_validation.csv ({len(sv_rows)} rows)")


def _csv(v: str) -> str:
    v = str(v)
    if any(c in v for c in (',', '"', '\n')):
        return '"' + v.replace('"', '""') + '"'
    return v


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    print(f"Connecting to {DB_PATH}")
    con = sqlite3.connect(DB_PATH)

    print("Setting up tables…")
    setup_new_tables(con)

    print("Running scalar validation…")
    n_scalar = run_scalar_validation(con)
    print(f"  {n_scalar} rows → dataset_validation")

    print("Running spectral validation…")
    n_spectral = run_spectral_validation(con)
    print(f"  {n_spectral} rows → spectral_validation")

    print("Detecting spectral anomalies…")
    n_anomalies = detect_spectral_anomalies(con)
    print(f"  {n_anomalies} rows → spectral_anomalies")

    print("Generating reports…")
    generate_reports(con)

    con.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
