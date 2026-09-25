#!/usr/bin/env python3
"""
scripts/release_validation.py
=============================
Cross-source validation and consensus for the release database (build stage 3b, after dedupe). Raw rows are never modified.

What is comparable: two optical datasets of ONE material with the same phase and optical axis (parsed from dataset_label
"phase | source | axis") at the same temperature (both ambient, or stated temperatures within 1 degC). Different phases, axes or
temperatures are different physical quantities and are never compared or combined.

dataset_validation  one row per comparable pair and property (n; k when both give it) over the wavelengths where BOTH have data,
                    evaluated at the union of their own wavelengths (no extrapolation, no invented resolution):
                      mean_relative_error  n: mean |a-b| / mean(a,b);  k: mean |a-b| / max k in the overlap (relative error of
                                           k is meaningless near 0; if max k < 0.01 the absolute mean difference is used)
                      rmse, pearson_r      (pearson_r NULL when either side is constant)
                      classification       excellent < 2%, warning < 10%, suspicious >= 10% (materials_normalized.db's scale);
                                           k in transparent regions: excellent < 0.002, warning < 0.01 absolute
                      notes                overlap range, point count, each side measured / model fit (dataset_kind.py), temperature
consensus_properties n and k at 633 nm per material, phase and axis ("n_633nm", "n_633nm | wurtzite | o-ray"), from MEASURED
                    ambient-temperature datasets covering 633 nm only (model fits never vote):
                      consensus_value  median;  std_dev  sample std (0 for one source);  num_sources  datasets that voted
                      spread           (max - min) / median  (k: absolute max - min when the median k < 0.01)
                      classification   single_source, else excellent / warning / suspicious on the spread with the thresholds above
                      confidence_score (1 - 0.5^num_sources) * (1 - min(spread, 10%) / 10%): one source 0.5 (as the legacy DB),
                                       two agreeing sources 0.75, three 0.875; a 5% spread halves it
"""
import math
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_kind import is_model_fit  # noqa: E402

AXES = {"o-ray", "e-ray", "a-axis", "b-axis", "c-axis", "alpha-axis", "beta-axis", "gamma-axis"}
AMBIENT_C = (15.0, 30.0)
REF_WL_NM = 633.0
EXCELLENT, WARNING = 0.02, 0.10          # relative
K_TRANSPARENT = 0.01                     # below this max k, k is compared in absolute terms
K_ABS_EXCELLENT, K_ABS_WARNING = 0.002, 0.01


def parse_label(label):
    """(phase, source tag, axis) from 'phase | tag | axis' with the phase and axis segments optional."""
    seg = [s.strip() for s in (label or "").split(" | ")]
    axis = seg.pop() if len(seg) > 1 and seg[-1] in AXES else None
    phase = seg[0] if len(seg) == 2 else None
    return phase, seg[-1], axis


def ambient(t):
    return t is None or AMBIENT_C[0] <= t <= AMBIENT_C[1]


def classify(err, rel=True):
    if rel:
        return "excellent" if err < EXCELLENT else "warning" if err < WARNING else "suspicious"
    return "excellent" if err < K_ABS_EXCELLENT else "warning" if err < K_ABS_WARNING else "suspicious"


def _series(rows, col):
    """wavelength -> value, repeated wavelengths (as the source repeats them) averaged; None values dropped."""
    acc = defaultdict(list)
    for wl, n, k in rows:
        v = n if col == "n" else k
        if v is not None:
            acc[wl].append(v)
    wl = np.array(sorted(acc))
    return wl, np.array([np.mean(acc[w]) for w in wl])


def compare(rows_a, rows_b, col):
    """Metrics over the shared range, or None when the datasets do not overlap on at least 3 of each one's own points."""
    wa, va = _series(rows_a, col)
    wb, vb = _series(rows_b, col)
    if len(wa) < 2 or len(wb) < 2:
        return None
    lo, hi = max(wa[0], wb[0]), min(wa[-1], wb[-1])
    if hi <= lo or ((wa >= lo) & (wa <= hi)).sum() < 3 or ((wb >= lo) & (wb <= hi)).sum() < 3:
        return None
    grid = np.union1d(wa[(wa >= lo) & (wa <= hi)], wb[(wb >= lo) & (wb <= hi)])
    a, b = np.interp(grid, wa, va), np.interp(grid, wb, vb)
    diff = np.abs(a - b)
    if col == "n":
        err, rel = float(np.mean(diff / ((a + b) / 2))), True
    else:
        kmax = float(max(np.abs(a).max(), np.abs(b).max()))
        err, rel = (float(np.mean(diff) / kmax), True) if kmax >= K_TRANSPARENT else (float(np.mean(diff)), False)
    r = float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else None
    return dict(err=err, rel=rel, rmse=float(np.sqrt(np.mean((a - b) ** 2))), r=r, lo=float(lo), hi=float(hi), npts=len(grid))


def value_at(rows, col, wl=REF_WL_NM):
    w, v = _series(rows, col)
    return float(np.interp(wl, w, v)) if len(w) >= 2 and w[0] <= wl <= w[-1] else None


def populate(conn):
    """Fill dataset_validation and consensus_properties. Returns counts for the manifest."""
    conn.execute("DELETE FROM dataset_validation")
    conn.execute("DELETE FROM consensus_properties")
    data = defaultdict(lambda: defaultdict(list))
    meta = {}
    for mid, label, table, wl, n, k, t in conn.execute(
            "SELECT material_id, dataset_label, raw_record_table, wavelength_nm, n, k, temperature_c FROM optical_dispersion"):
        data[mid][label].append((wl, n, k))
        meta.setdefault((mid, label), dict(table=table, temps=set()))["temps"].add(t)
    counts = dict(pairs=defaultdict(int), consensus=defaultdict(int), materials_compared=0)
    for mid, sets in data.items():
        info = {}
        for label in sets:
            temps = meta[(mid, label)]["temps"]
            if len(temps) != 1:  # a dataset is one temperature; anything else is not comparable as a whole
                continue
            phase, tag, axis = parse_label(label)
            info[label] = dict(phase=phase, axis=axis, temp=next(iter(temps)), model=is_model_fit(meta[(mid, label)]["table"]))
        groups = defaultdict(list)
        for label, d in info.items():
            groups[(d["phase"], d["axis"])].append(label)
        compared = False
        for (phase, axis), labels in groups.items():
            for la, lb in combinations(sorted(labels), 2):
                ta, tb = info[la]["temp"], info[lb]["temp"]
                if not ((ambient(ta) and ambient(tb)) or (ta is not None and tb is not None and abs(ta - tb) <= 1.0)):
                    continue
                for col in ("n", "k"):
                    m = compare(sets[la], sets[lb], col)
                    if m is None:
                        continue
                    cls = classify(m["err"], m["rel"])
                    kind = lambda x: "model fit" if info[x]["model"] else "measured"
                    temp = "ambient" if ambient(ta) and ambient(tb) else f"{ta:g} degC"
                    conn.execute("INSERT INTO dataset_validation(material_id, property_name, dataset_a, dataset_b, pearson_r, rmse, "
                                 "mean_relative_error, classification, notes) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (mid, col, la, lb, m["r"], m["rmse"], m["err"], cls,
                                  f"overlap {m['lo']:g}-{m['hi']:g} nm, {m['npts']} points; {kind(la)} vs {kind(lb)}; {temp}"
                                  + ("" if m["rel"] else "; k < 0.01 throughout: absolute mean difference")))
                    counts["pairs"][cls] += 1
                    compared = True
            # consensus at 633 nm: measured, ambient datasets of this phase/axis that cover 633 nm
            for col in ("n", "k"):
                votes = [v for lab in labels if not info[lab]["model"] and ambient(info[lab]["temp"])
                         if (v := value_at(sets[lab], col)) is not None]
                if not votes:
                    continue
                med = float(np.median(votes))
                absolute = col == "k" and abs(med) < K_TRANSPARENT
                spread = (max(votes) - min(votes)) if absolute else (max(votes) - min(votes)) / abs(med) if med else math.inf
                cls = "single_source" if len(votes) == 1 else classify(spread, not absolute)
                norm = spread / (K_ABS_WARNING if absolute else WARNING)
                conf = (1 - 0.5 ** len(votes)) * (1 - min(norm, 1.0))
                name = " | ".join(x for x in (f"{col}_633nm", phase, axis) if x)
                conn.execute("INSERT INTO consensus_properties(material_id, property_name, consensus_value, std_dev, num_sources, "
                             "confidence_score, classification) VALUES (?,?,?,?,?,?,?)",
                             (mid, name, med, float(np.std(votes, ddof=1)) if len(votes) > 1 else 0.0, len(votes), round(conf, 4), cls))
                counts["consensus"][cls] += 1
        counts["materials_compared"] += compared
    return dict(pairs=dict(counts["pairs"]), consensus=dict(counts["consensus"]), materials_compared=counts["materials_compared"])
