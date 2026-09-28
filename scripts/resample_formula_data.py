#!/usr/bin/env python3
"""
scripts/resample_formula_data.py
================================
Re-samples the stored rows of every dispersion-FORMULA dataset in the tracked base database from the old fixed grid (500 linear
points over the formula's range) to fetch_optical_data.sample_formula (adaptive: linear interpolation between stored samples
within FORMULA_TOL = 1e-6 of the formula), and updates the n_633 / k_633 cells of the base-family CSVs that were read off the
old grid. The families loaded at build time need nothing: they call parse_file, which samples the new way.

Why: interpolating the old grid missed the formula by up to 4e-3 in n at 633 nm (ZnTe, TlBr, halides near their absorption
edges) and up to ~1e2 near a pole, so every consumer of the stored rows (validation, consensus, ML sets, access layer) disagreed
with the exact formula value the later family tables publish (NOTES item 30).

DRY-RUN by default; --apply writes. Safety, per dataset: the stored rows must be EXACTLY the old grid (row count, raw_record_id
0..N-1, wavelength and n to 1e-12, k, one material, label, source and temperature) or the run stops; the new rows keep the
material, label, source and temperature. CSVs: round-trip identity is asserted first; a cell of a dataset WITHOUT a formula
block must already equal a recomputation (proves the row -> dataset mapping) or the run stops. Idempotent: a second run finds
the datasets already on the new sampling and changes nothing.
"""
import argparse
import contextlib
import csv
import io
import json
import math
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import remediate_formula4_data as rf4  # noqa: E402  (sets the loaders' wavelength window, catalog lookups)

RI_DATA = rf4.RI_DATA
DEFAULT_DBS = rf4.DEFAULT_DBS
DEFAULT_CSVS = rf4.DEFAULT_CSVS
OLD_N = 500


class ResampleError(RuntimeError):
    pass


def has_formula(rel):
    try:
        return any(str(b.get("type", "")).startswith("formula") for b in yaml.safe_load(open(RI_DATA / rel))["DATA"])
    except Exception:
        return False


def _old_sample(block, lo, hi, **_):
    lam = np.linspace(lo, hi, OLD_N)
    n, k = fod.eval_formula(block, lam)
    return lam, n, k


@contextlib.contextmanager
def old_sampling():
    new = fod.sample_formula
    fod.sample_formula = _old_sample
    try:
        yield
    finally:
        fod.sample_formula = new


def _close(a, b, tol=1e-12):
    if a is None or b is None:
        return a is None and b is None
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tol * max(1.0, abs(a))


def _matches(rows, wl, n, k):
    if len(rows) != len(wl) or [r[1] for r in rows] != list(range(len(wl))):
        return False
    for i, r in enumerate(rows):
        k_i = None if k is None or np.isnan(k[i]) else float(k[i])
        if not (math.isclose(r[2], float(wl[i]), rel_tol=1e-12) and _close(r[3], float(n[i])) and _close(r[4], k_i)):
            return False
    return True


def resample_db(db_path, apply):
    conn = sqlite3.connect(str(db_path))
    paths = [p for (p,) in conn.execute("SELECT DISTINCT raw_record_table FROM optical_dispersion WHERE raw_record_table LIKE '%/%/%'")]
    out = dict(db=Path(db_path).name, datasets=[], already_new=[], rows_before=0, rows_after=0)
    try:
        for p in sorted(paths):
            if not has_formula(p):
                continue
            rows = conn.execute("SELECT record_id, raw_record_id, wavelength_nm, n, k, material_id, dataset_label, source_id, temperature_c "
                                "FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (p,)).fetchall()
            wl, n, k, _, temp = fod.parse_file(RI_DATA / p)
            if _matches(rows, wl, n, k):
                out["already_new"].append(p)
                continue
            with old_sampling():
                owl, on, ok, _, otemp = fod.parse_file(RI_DATA / p)
            if not _matches(rows, owl, on, ok):
                raise ResampleError(f"{p}: stored rows are neither the old grid nor the new sampling ({len(rows)} rows); refusing")
            ident = {(r[5], r[6], r[7], r[8]) for r in rows}
            if len(ident) != 1:
                raise ResampleError(f"{p}: rows of one data file carry several material/label/source/temperature values: {ident}")
            mid, label, source_id, t_c = ident.pop()
            if not _close(t_c, otemp) or not _close(temp, otemp):
                raise ResampleError(f"{p}: temperature {t_c} differs from parse_file's {otemp}")
            conn.execute("DELETE FROM optical_dispersion WHERE raw_record_table=?", (p,))
            conn.executemany(
                "INSERT INTO optical_dispersion (material_id, wavelength_nm, n, k, temperature_c, dataset_label, raw_record_table, "
                "raw_record_id, source_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(mid, float(wl[i]), float(n[i]), None if k is None or np.isnan(k[i]) else float(k[i]), t_c, label, p, i, source_id)
                 for i in range(len(wl))])
            n633_old = float(np.interp(633.0, owl, on)) if owl[0] <= 633.0 <= owl[-1] else None
            n633_new = float(np.interp(633.0, wl, n)) if wl[0] <= 633.0 <= wl[-1] else None
            out["datasets"].append(dict(data_path=p, material_id=mid, dataset_label=label, rows_before=len(rows), rows_after=len(wl),
                                        n_633_before=n633_old, n_633_after=n633_new))
            out["rows_before"] += len(rows)
            out["rows_after"] += len(wl)
        if apply:
            conn.commit()
            conn.execute("VACUUM")
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return out


def resample_csv(path, apply, pages):
    raw = open(path, newline="").read()
    rows = list(csv.reader(io.StringIO(raw, newline="")))
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    if buf.getvalue() != raw:
        raise ResampleError(f"{path.name}: csv round-trip is not byte-identical; refusing to rewrite")
    head, body = rows[0], rows[1:]
    ix = {c: i for i, c in enumerate(head)}
    out = dict(csv=path.name, rows=len(body), cells_updated=[], unexplained=[], unresolved=[])
    for r in body:
        label = r[ix["formula"]] if "formula" in ix else r[ix["name"]]
        for ncol, kcol, pcol in rf4.N_COLS:
            if pcol not in ix or not r[ix[pcol]]:
                continue
            key = (r[ix["ri_shelf"]], r[ix["ri_book"]])
            cand = (pages.get(key, {}).get(r[ix[pcol]], []) or pages.get((key[0], "~" + rf4._norm(key[1])), {}).get(r[ix[pcol]], []))
            cand = list(dict.fromkeys(cand))
            if len(cand) != 1:
                out["unresolved"].append(dict(row=label, page=r[ix[pcol]], candidates=len(cand)))
                continue
            new = rf4.base.interpolate_axis(cand[0])
            formula = has_formula(cand[0])
            for col, val in ((ncol, new["n_633"]), (kcol, new["k_633"])):
                if col not in ix:
                    continue
                old = float(r[ix[col]]) if r[ix[col]] not in ("", None) else None
                if rf4._same(old, val):
                    continue
                if formula:
                    out["cells_updated"].append(dict(row=label, column=col, old=old, new=val, data_path=cand[0]))
                    r[ix[col]] = "" if val is None else repr(val)
                else:
                    out["unexplained"].append(dict(row=label, column=col, old=old, new=val, data_path=cand[0]))
    if out["unexplained"] or out["unresolved"]:
        raise ResampleError(f"{path.name}: {len(out['unexplained'])} unexplained cell differences, {len(out['unresolved'])} unresolved pages: "
                            f"{(out['unexplained'] + out['unresolved'])[:3]}")
    if apply and out["cells_updated"]:
        with open(path, "w", newline="") as fh:
            csv.writer(fh, lineterminator="\n").writerows([head] + body)
    return out


FAMILY_CSVS = {  # family CSV -> its selections (dataset_label -> data_path); built at family time from parse_file output
    f: f"step1_selections_{sel}.json" for f, sel in (
        ("nitrides", "nitrides"), ("inorganic3", "inorganic3"), ("halides", "halides"), ("chalcogenides", "chalcogenides"),
        ("semiconductors", "semiconductors"), ("inorganic4", "inorganic4"), ("liquids", "liquids"), ("glasses", "glasses"),
        ("optical_media", "optical_media"), ("liquid_crystals", "liquid_crystals"), ("bio_media", "bio_media"), ("gases", "gases"),
        ("alloys", "alloys"), ("perovskites", "perovskites"))}
FLAG_VALUE = re.compile(r"(additional (?:source|dataset) )([^:;]+?)(: n\(633 nm\)=)([-\d.eE+]+|None)((?:, k=)([-\d.eE+]+))?")


def _exact_n633(data_path):
    for b in yaml.safe_load(open(RI_DATA / data_path))["DATA"]:
        if str(b.get("type", "")).startswith("formula"):
            lo, hi = (float(x) for x in str(b["wavelength_range"]).split())
            if lo <= 0.633 <= hi:
                return float(fod.eval_formula(b, np.array([0.633]))[0][0])
    return None


def _values(data_path):
    """(n candidates, k) at 633 nm the family builders can have written: interpolated from parse_file's samples, or (formula
    pages) the formula evaluated exactly."""
    v = rf4.base.interpolate_axis(data_path)
    return dict(interp=v["n_633"], exact=_exact_n633(data_path)), v["k_633"]


def _fmt(v):
    return "None" if v is None else repr(v)


def refresh_family_csv(path, selections_path, apply):
    """n_633 / k_633 cells (+ axis 2/3) and the 'additional dataset X: n(633 nm)=.., k=..' flag values of a family CSV. Each
    published number must equal what the builder computed from the OLD sampling (interpolated or exact, whichever it is), which
    proves the number -> dataset mapping; it is then replaced by the same computation on the new sampling. An exact-formula n
    does not change. Anything unexplained stops the run."""
    raw = open(path, newline="").read()
    rows = list(csv.reader(io.StringIO(raw, newline="")))
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    if buf.getvalue() != raw:
        raise ResampleError(f"{path.name}: csv round-trip is not byte-identical; refusing to rewrite")
    sel = json.loads(Path(selections_path).read_text())
    by_name = {v["name"]: v for v in sel.values()} if isinstance(sel, dict) else {}
    head, body = rows[0], rows[1:]
    ix = {c: i for i, c in enumerate(head)}
    out = dict(csv=path.name, cells_updated=[], flags_updated=[], unexplained=[])
    cache = {}

    def old_new(dp):
        if dp not in cache:
            with old_sampling():
                o = _values(dp)
            cache[dp] = (o, _values(dp))
        return cache[dp]

    def resolve(old_text, cands_old, cands_new):
        """new text for an n value: whichever computation reproduces the published text (already new: unchanged)."""
        for kind in ("exact", "interp"):
            if _fmt(cands_new[kind]) == old_text:
                return old_text
            if _fmt(cands_old[kind]) == old_text:
                return _fmt(cands_new[kind])
        return None

    def resolve_k(old_text, k_old, k_new):
        return old_text if old_text == _fmt(k_new) else _fmt(k_new) if old_text == _fmt(k_old) else None

    for r in body:
        name = r[ix["name"]]
        axes = {a["dataset_label"]: a for a in by_name.get(name, {}).get("axes", [])}
        by_page = {a["page"]: a for a in axes.values()}
        for ncol, kcol, pcol in rf4.N_COLS:
            if pcol not in ix or not r[ix[pcol]] or ncol not in ix:
                continue
            a = by_page.get(r[ix[pcol]])
            if a is None:
                out["unexplained"].append(dict(row=name, page=r[ix[pcol]], why="page not in selections"))
                continue
            (on, ok), (nn, nk) = old_new(a["data_path"])
            txt = r[ix[ncol]]
            cell_old = _fmt(float(txt)) if txt else "None"
            new_n = resolve(cell_old, on, nn)
            if new_n is None:
                out["unexplained"].append(dict(row=name, column=ncol, published=txt, old_interp=on["interp"], old_exact=on["exact"]))
                continue
            if new_n != cell_old:
                out["cells_updated"].append(dict(row=name, column=ncol, old=txt, new=new_n))
                r[ix[ncol]] = "" if new_n == "None" else new_n
            if kcol in ix:
                ktxt = r[ix[kcol]]
                k_cell = _fmt(float(ktxt)) if ktxt else "None"
                new_k = resolve_k(k_cell, ok, nk)
                if new_k is None:
                    out["unexplained"].append(dict(row=name, column=kcol, published=ktxt, old=ok, new=nk))
                elif new_k != k_cell:
                    out["cells_updated"].append(dict(row=name, column=kcol, old=ktxt, new=new_k))
                    r[ix[kcol]] = "" if nk is None else repr(nk)
        if "flags" in ix and r[ix["flags"]]:
            def fix(m):
                label = m.group(2).strip()
                a = axes.get(label) or axes.get(re.sub(r" \([^()]*degC\)$", "", label))  # liquids append the temperature
                if a is None:
                    out["unexplained"].append(dict(row=name, flag_label=label, why="label not in selections"))
                    return m.group(0)
                (on, ok), (nn, nk) = old_new(a["data_path"])
                new_n = resolve(m.group(4), on, nn)
                if new_n is None:
                    out["unexplained"].append(dict(row=name, flag_label=label, published=m.group(4), old_interp=on["interp"], old_exact=on["exact"]))
                    return m.group(0)
                text = m.group(1) + m.group(2) + m.group(3) + new_n
                if m.group(5):
                    new_k = resolve_k(m.group(6), ok, nk)
                    if new_k is None:
                        out["unexplained"].append(dict(row=name, flag_label=label, published_k=m.group(6), old_k=ok, new_k=nk))
                        return m.group(0)
                    text += ", k=" + new_k
                if text != m.group(0):
                    out["flags_updated"].append(dict(row=name, label=label, old=m.group(0), new=text))
                return text
            r[ix["flags"]] = FLAG_VALUE.sub(fix, r[ix["flags"]])
    if out["unexplained"]:
        raise ResampleError(f"{path.name}: {len(out['unexplained'])} unexplained values: {out['unexplained'][:3]}")
    if apply and (out["cells_updated"] or out["flags_updated"]):
        with open(path, "w", newline="") as fh:
            csv.writer(fh, lineterminator="\n").writerows([head] + body)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", action="append", type=Path)
    ap.add_argument("--csv", action="append", type=Path)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--report", type=Path, help="write a JSON report here")
    a = ap.parse_args(argv)
    pages = rf4._catalog_pages()
    rep = dict(applied=a.apply, dbs=[resample_db(p, a.apply) for p in (a.db or DEFAULT_DBS)],
               csvs=[resample_csv(p, a.apply, pages) for p in (a.csv or DEFAULT_CSVS)],
               family_csvs=[] if a.csv or a.db else [refresh_family_csv(rf4._ROOT / "data" / f"{f}.csv", rf4._ROOT / "data" / sel, a.apply)
                                                     for f, sel in FAMILY_CSVS.items()])
    tag = "APPLIED" if a.apply else "dry-run"
    for d in rep["dbs"]:
        print(f"[{tag}] {d['db']}: {len(d['datasets'])} formula datasets resampled ({d['rows_before']} -> {d['rows_after']} rows), "
              f"{len(d['already_new'])} already on the new sampling")
    for c in rep["csvs"]:
        print(f"[{tag}] {c['csv']}: {c['rows']} rows, {len(c['cells_updated'])} n/k_633 cells changed")
    for c in rep["family_csvs"]:
        print(f"[{tag}] {c['csv']}: {len(c['cells_updated'])} n/k_633 cells, {len(c['flags_updated'])} flag values changed")
    if a.report:
        a.report.write_text(json.dumps(rep, indent=1, default=str))
    return rep


if __name__ == "__main__":
    main()
