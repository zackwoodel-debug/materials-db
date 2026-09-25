#!/usr/bin/env python3
"""
scripts/remediate_formula4_data.py
===================================
Corrects stored data produced by the OLD, wrong RI.info "formula 4" evaluation (fixed in fetch_optical_data.eval_formula):
  * databases: optical_dispersion.n for every dataset whose RI.info file has a formula-4 block (eps_real / eps_imag are GENERATED
    columns and recompute themselves);
  * catalogs: the n_633 / k_633 (+ axis2 / axis3) cells of the oxide / batch CSVs whose dataset uses formula 4.

DRY-RUN by default (writes nothing); --apply writes. Safety: a dataset's stored rows must match parse_file's grid exactly (row count,
raw_record_id, wavelength) or the run stops; k must be unchanged; CSVs are rewritten through csv.writer so every other byte is preserved
(round-trip identity is asserted first); CSV cells of datasets that do NOT use formula 4 must already equal a recomputation (proves the
row -> dataset mapping) or the run stops. Idempotent: a second run changes nothing.
"""
import argparse
import csv
import io
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402

fod.WL_MIN_NM = 0.01           # the loaders' window, unchanged
fod.WL_MAX_NM = 2_000_000.0
import build_oxides_csv as base  # noqa: E402

RI_DB = _ROOT / "refractiveindex_db" / "database"
RI_DATA = RI_DB / "data"
DEFAULT_DBS = [_ROOT / "data" / "materials_oxide_test.db"]
DEFAULT_CSVS = [_ROOT / "data" / f for f in ("oxides_50.csv", "batch2_31.csv", "batch3b_4.csv", "pure_elements_50.csv")]
N_COLS = (("n_633", "k_633", "ri_page_primary"), ("n_633_axis2", "k_633_axis2", "ri_page_axis2"), ("n_633_axis3", "k_633_axis3", "ri_page_axis3"))


class RemediationError(RuntimeError):
    pass


def has_formula4(rel):
    try:
        return any(b.get("type") == "formula 4" for b in yaml.safe_load(open(RI_DATA / rel))["DATA"])
    except Exception:
        return False


def _same(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a))


def remediate_db(db_path, apply):
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    paths = [p for (p,) in conn.execute("SELECT DISTINCT raw_record_table FROM optical_dispersion WHERE raw_record_table LIKE '%/%/%'")]
    out = dict(db=str(Path(db_path).name), datasets=[], rows_changed=0, rows_checked=0)
    try:
        for p in sorted(paths):
            if not has_formula4(p):
                continue
            wl, n, k, _, _ = fod.parse_file(RI_DATA / p)
            rows = conn.execute("SELECT record_id, raw_record_id, wavelength_nm, n, k, material_id, dataset_label FROM optical_dispersion "
                                "WHERE raw_record_table=? ORDER BY raw_record_id", (p,)).fetchall()
            if len(rows) != len(wl) or [r[1] for r in rows] != list(range(len(wl))):
                raise RemediationError(f"{p}: stored rows do not match parse_file's grid (rows {len(rows)} vs {len(wl)})")
            updates, max_dn, i633 = [], 0.0, int(np.argmin(np.abs(wl - 633.0)))
            for i, (rid, _raw, w, n_old, k_old, _mid, _lab) in enumerate(rows):
                if not math.isclose(w, float(wl[i]), rel_tol=1e-12):
                    raise RemediationError(f"{p}: wavelength mismatch at row {i}")
                k_new = None if k is None or np.isnan(k[i]) else float(k[i])
                if not _same(k_old, k_new, 1e-12):
                    raise RemediationError(f"{p}: k would change at row {i} ({k_old} -> {k_new}); refusing")
                n_new = float(n[i])
                if not _same(n_old, n_new, 1e-12):
                    updates.append((n_new, rid))
                    max_dn = max(max_dn, abs(n_new - n_old))
            mat = conn.execute("SELECT m.name FROM materials m WHERE m.material_id=?", (rows[0][5],)).fetchone()[0]
            out["datasets"].append(dict(data_path=p, material=mat, dataset_label=rows[0][6], rows=len(rows), rows_changed=len(updates), max_abs_dn=max_dn,
                                        n_633_before=rows[i633][3] if abs(rows[i633][2] - 633) < 20 else None,
                                        n_633_after=float(n[i633]) if abs(rows[i633][2] - 633) < 20 else None))
            out["rows_checked"] += len(rows)
            out["rows_changed"] += len(updates)
            conn.executemany("UPDATE optical_dispersion SET n=? WHERE record_id=?", updates)
        bad = conn.execute("SELECT COUNT(*) FROM optical_dispersion WHERE n IS NOT NULL AND k IS NOT NULL AND ABS(eps_real-(n*n-k*k)) > 1e-9").fetchone()[0]
        if bad:
            raise RemediationError(f"{bad} rows where eps_real != n^2-k^2 after the update")
        if apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return out


def _norm(s):
    import re
    return re.sub(r"[^A-Za-z0-9]", "", s).lower()


def _catalog_pages():
    cat = yaml.safe_load(open(RI_DB / "catalog-nk.yml"))
    pages = {}
    for e in cat:
        for b in e.get("content", []):
            if "BOOK" in b:
                d = {}
                for p in b.get("content", []):
                    if "PAGE" in p and p.get("data"):
                        d.setdefault(p["PAGE"], []).append(p["data"])
                        d.setdefault(Path(p["data"]).stem, []).append(p["data"])  # the data file's base name ('Slavich-alpha' for page 'Slavich-\u03b1')
                pages[(e["SHELF"], b["BOOK"])] = d
                pages.setdefault((e["SHELF"], "~" + _norm(b["BOOK"])), d)  # normalized alias: 'LuAl3(BO3)4' == 'LuAl3_BO3_4'
    return pages


def remediate_csv(path, apply, pages):
    raw = open(path, newline="").read()
    rows = list(csv.reader(io.StringIO(raw, newline="")))
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    if buf.getvalue() != raw:
        raise RemediationError(f"{path.name}: csv round-trip is not byte-identical; refusing to rewrite")
    head, body = rows[0], rows[1:]
    ix = {c: i for i, c in enumerate(head)}
    out = dict(csv=path.name, rows=len(body), cells_updated=[], unexplained=[], unresolved=[])
    for r in body:
        label = r[ix["formula"]] if "formula" in ix else r[ix["name"]]
        for ncol, kcol, pcol in N_COLS:
            if pcol not in ix or not r[ix[pcol]]:
                continue
            key = (r[ix["ri_shelf"]], r[ix["ri_book"]])
            cand = pages.get(key, {}).get(r[ix[pcol]], []) or pages.get((key[0], "~" + _norm(key[1])), {}).get(r[ix[pcol]], [])
            cand = list(dict.fromkeys(cand))  # a page id and its file base name can both point at the same file
            if len(cand) != 1:
                out["unresolved"].append(dict(row=label, page=r[ix[pcol]], candidates=len(cand)))
                continue
            new = base.interpolate_axis(cand[0])
            f4 = has_formula4(cand[0])
            for col, val in ((ncol, new["n_633"]), (kcol, new["k_633"])):
                if col not in ix:
                    continue
                old = float(r[ix[col]]) if r[ix[col]] not in ("", None) else None
                if _same(old, val):
                    continue
                if f4 and col == ncol:
                    out["cells_updated"].append(dict(row=label, column=col, old=old, new=val))
                    r[ix[col]] = "" if val is None else repr(val)
                else:
                    out["unexplained"].append(dict(row=label, column=col, old=old, new=val, data_path=cand[0], formula4=f4))
    if out["unexplained"] or out["unresolved"]:
        raise RemediationError(f"{path.name}: {len(out['unexplained'])} unexplained cell differences, {len(out['unresolved'])} unresolved pages: "
                               f"{(out['unexplained'] + out['unresolved'])[:3]}")
    if apply and out["cells_updated"]:
        with open(path, "w", newline="") as fh:
            csv.writer(fh, lineterminator="\n").writerows([head] + body)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", action="append", type=Path, help="database(s) to correct (default: the tracked oxide DB)")
    ap.add_argument("--csv", action="append", type=Path, help="CSV(s) to correct (default: oxides_50, batch2_31, batch3b_4, pure_elements_50)")
    ap.add_argument("--apply", action="store_true", help="write the corrections (default: dry run)")
    ap.add_argument("--report", type=Path, help="write a JSON report here")
    a = ap.parse_args(argv)
    pages = _catalog_pages()
    rep = dict(applied=a.apply, dbs=[remediate_db(p, a.apply) for p in (a.db or DEFAULT_DBS)],
               csvs=[remediate_csv(p, a.apply, pages) for p in (a.csv or DEFAULT_CSVS)])
    for d in rep["dbs"]:
        print(f"[{'APPLIED' if a.apply else 'dry-run'}] {d['db']}: {len(d['datasets'])} formula-4 datasets, {d['rows_checked']} rows checked, {d['rows_changed']} rows changed")
    for c in rep["csvs"]:
        print(f"[{'APPLIED' if a.apply else 'dry-run'}] {c['csv']}: {c['rows']} rows, {len(c['cells_updated'])} n_633 cells changed")
    if a.report:
        a.report.write_text(json.dumps(rep, indent=1, default=str))
    return rep


if __name__ == "__main__":
    main()
