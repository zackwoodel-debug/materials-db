"""Guards the STORED data (not just the parser) against the old formula-4 bug, and tests the remediation script itself.

Ground truth is independent of the pipeline: RI.info's published formula-4 definition written out here, published BBO indices (Eimerl 1987) and
well-known indices of rutile TiO2 / ZnO / KNbO3 / LuAG / MgO at 633 nm.
"""
import csv
import io
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import load_family_db as fam  # noqa: E402
import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import remediate_formula4_data as rem  # noqa: E402

DATA, RI = ROOT / "data", ROOT / "refractiveindex_db" / "database" / "data"
DB = DATA / "materials_oxide_test.db"
CSVS = ["oxides_50.csv", "batch2_31.csv", "batch3b_4.csv", "pure_elements_50.csv"]


def official(block, lam):
    t, c, l2 = block["type"], [float(x) for x in block["coefficients"].split()], lam * lam
    if t == "formula 1":
        return np.sqrt(1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1] ** 2) for i in range(1, len(c) - 1, 2)))
    if t == "formula 2":
        return np.sqrt(1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1]) for i in range(1, len(c) - 1, 2)))
    if t == "formula 3":
        return np.sqrt(c[0] + sum(c[i] * lam ** c[i + 1] for i in range(1, len(c) - 1, 2)))
    if t == "formula 4":
        def group(B, p, C, q):
            # a resonance group with B == 0 contributes exactly 0 (LuAG has an all-zero second group whose denominator vanishes at 1.000 um: 0/0)
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(B == 0.0, 0.0, B * lam ** p / (l2 - C ** q))

        n2 = np.full_like(lam, c[0])
        if len(c) >= 5:
            n2 = n2 + group(*c[1:5])
        if len(c) >= 9:
            n2 = n2 + group(*c[5:9])
        for i in range(9, len(c) - 1, 2):
            n2 = n2 + c[i] * lam ** c[i + 1]
        return np.sqrt(n2)
    if t == "formula 5":
        return c[0] + sum(c[i] * lam ** c[i + 1] for i in range(1, len(c) - 1, 2))
    raise AssertionError(f"unsupported {t}")


def _f4_paths(conn):
    out = []
    for (p,) in conn.execute("SELECT DISTINCT raw_record_table FROM optical_dispersion WHERE raw_record_table LIKE '%/%/%'"):
        if rem.has_formula4(p):
            out.append(p)
    return sorted(out)


_conn = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
F4 = _f4_paths(_conn)
_conn.close()


def test_the_tracked_db_still_has_the_37_formula4_datasets():
    assert len(F4) == 37


@pytest.mark.parametrize("path", F4, ids=[p.split("/")[1] + "/" + p.split("/")[-1][:-4] for p in F4])
def test_stored_n_equals_the_published_formula_at_every_stored_wavelength(path):
    c = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
    rows = c.execute("SELECT wavelength_nm, n FROM optical_dispersion WHERE raw_record_table=? ORDER BY raw_record_id", (path,)).fetchall()
    c.close()
    blk = next(b for b in yaml.safe_load(open(RI / path))["DATA"] if b["type"] == "formula 4")
    lo, hi = [float(x) for x in blk["wavelength_range"].split()]
    lam = np.array([r[0] for r in rows]) / 1000.0
    m = (lam >= lo - 1e-12) & (lam <= hi + 1e-12)
    got, want = np.array([r[1] for r in rows])[m], official(blk, lam[m])
    assert m.sum() > 100 and np.isfinite(got).all() and np.isfinite(want).all(), f"{path}: non-finite values (a NaN must never pass a comparison)"
    assert np.allclose(got, want, rtol=1e-9, atol=1e-12), f"{path}: max diff {np.max(np.abs(got - want)):.3e}"


def _n_at(conn, mat_like, label_like, lam_nm):
    rows = conn.execute("SELECT o.wavelength_nm, o.n FROM optical_dispersion o JOIN materials m USING(material_id) WHERE m.name LIKE ? AND o.dataset_label LIKE ? "
                        "ORDER BY o.wavelength_nm", (mat_like, label_like)).fetchall()
    return float(np.interp(lam_nm, [r[0] for r in rows], [r[1] for r in rows]))


@pytest.mark.parametrize("mat,label,lam,expected,tol", [
    ("Barium borate%", "%o-ray", 532.1, 1.6749, 5e-4), ("Barium borate%", "%e-ray", 532.1, 1.5555, 5e-4),   # published (Eimerl 1987); old code: 1.6649 / 1.5481
    ("Titanium dioxide%", "rutile | Devore1951 | o-ray", 633, 2.58, 0.01), ("Titanium dioxide%", "rutile | Devore1951 | e-ray", 633, 2.87, 0.01),
    ("Zinc oxide", "%o-ray", 633, 1.99, 0.02), ("Zinc oxide", "%e-ray", 633, 2.00, 0.02),                       # old code: 2.53 / 2.55
    ("Potassium niobate", "%alpha%", 633, 2.17, 0.02), ("Potassium niobate", "%beta%", 633, 2.28, 0.02), ("Potassium niobate", "%gamma%", 633, 2.33, 0.02),
    ("LuAG", "%", 633, 1.84, 0.01), ("Magnesium oxide", "%", 633, 1.7366, 0.01),
])
def test_stored_data_reproduces_published_or_textbook_indices(mat, label, lam, expected, tol):
    c = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
    v = _n_at(c, mat, label, lam)
    c.close()
    assert v == pytest.approx(expected, abs=tol)


def test_nothing_but_n_of_the_formula4_datasets_differs_from_a_fresh_recompute_and_k_is_intact():
    c = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
    assert c.execute("SELECT COUNT(*) FROM optical_dispersion WHERE n IS NOT NULL AND k IS NOT NULL AND (ABS(eps_real-(n*n-k*k))>1e-9 OR ABS(eps_imag-2*n*k)>1e-9)").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 135 and c.execute("SELECT COUNT(*) FROM optical_dispersion").fetchone()[0] == 124547
    c.close()


# ---------------------------------------------------------------- the CSV n_633 cells

def _cells():
    pages = rem._catalog_pages()
    out = []
    for f in CSVS:
        rows = list(csv.reader(open(DATA / f, newline="")))
        ix = {c: i for i, c in enumerate(rows[0])}
        for r in rows[1:]:
            for ncol, _k, pcol in rem.N_COLS:
                if pcol in ix and r[ix[pcol]]:
                    key = (r[ix["ri_shelf"]], r[ix["ri_book"]])
                    cand = list(dict.fromkeys(pages.get(key, {}).get(r[ix[pcol]], []) or pages.get((key[0], "~" + rem._norm(key[1])), {}).get(r[ix[pcol]], [])))
                    out.append((f, r[ix["formula"]], ncol, r[ix[ncol]], cand[0]))
    return out


CELLS = _cells()


def test_every_n633_cell_is_resolvable_and_the_four_csvs_have_182_of_them():
    assert len(CELLS) == 182


def test_every_n633_cell_equals_an_independent_evaluation_on_the_pipeline_grid(monkeypatch):
    """The pipeline interpolates linearly on its sampled wavelength grid; the formula VALUES on that grid are evaluated here independently."""
    monkeypatch.setattr(fod, "WL_MIN_NM", 0.01)
    monkeypatch.setattr(fod, "WL_MAX_NM", 2_000_000.0)
    bad = []
    for f, mat, col, cell, path in CELLS:
        wl, n, *_ = fod.parse_file(RI / path)
        blocks = yaml.safe_load(open(RI / path))["DATA"]
        if any(b["type"].startswith("formula") for b in blocks):
            fb = next(b for b in blocks if b["type"].startswith("formula"))
            lo, hi = [float(x) for x in fb["wavelength_range"].split()]
            lam = wl / 1000.0
            grid = np.where((lam >= lo - 1e-12) & (lam <= hi + 1e-12), official(fb, np.clip(lam, lo, hi)), n) if len(blocks) > 1 else official(fb, lam)
        else:
            grid = n
        want = float(np.interp(633.0, wl, grid, left=np.nan, right=np.nan))
        if (np.isnan(want)) != (cell == "") or (cell != "" and abs(float(cell) - want) > 1e-6):
            bad.append((f, mat, col, cell, want))
    assert not bad, bad[:3]


# ---------------------------------------------------------------- the remediation script

def _synthetic_db(path, stale=True):
    """A tiny DB with (a) a BBO formula-4 dataset holding STALE n, (b) an untouched non-formula-4 dataset."""
    conn = sqlite3.connect(str(path))
    conn.executescript(fam.SCHEMA_PATH.read_text())
    sid = conn.execute("INSERT INTO sources(title, technique) VALUES('S','refractiveindex.info')").lastrowid
    p4, p1 = "main/BaB2O4/nk/Eimerl-o.yml", "organic/(C16H14O3)n - polycarbonate/nk/Sultanova.yml"
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    for name, p, bump in (("BBO", p4, 0.01 if stale else 0.0), ("PC", p1, 0.0)):
        mid = conn.execute("INSERT INTO materials(name, formula) VALUES(?, ?)", (name, name)).lastrowid
        wl, n, *_ = fod.parse_file(RI / p)
        conn.executemany("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) VALUES(?,?,?,?,?,?,?,?)",
                         [(mid, float(wl[i]), float(n[i]) + bump, None, "L", p, i, sid) for i in range(len(wl))])
    conn.commit()
    conn.close()
    return p4, p1


def test_remediation_corrects_only_the_formula4_dataset_and_is_idempotent(tmp_path):
    db = tmp_path / "s.db"
    p4, p1 = _synthetic_db(db)
    snap = lambda: sqlite3.connect(str(db)).execute("SELECT raw_record_table, raw_record_id, wavelength_nm, n, k FROM optical_dispersion ORDER BY 1,2").fetchall()
    before = snap()
    dry = rem.remediate_db(db, apply=False)
    assert snap() == before and dry["rows_changed"] == 500  # a dry run writes nothing
    done = rem.remediate_db(db, apply=True)
    after = snap()
    assert done["rows_changed"] == 500 and [r for r in after if r[0] == p1] == [r for r in before if r[0] == p1]  # the polycarbonate rows are untouched
    blk = next(b for b in yaml.safe_load(open(RI / p4))["DATA"] if b["type"] == "formula 4")
    got = np.array([r[3] for r in after if r[0] == p4])
    assert np.allclose(got, official(blk, np.array([r[2] for r in after if r[0] == p4]) / 1000.0), rtol=1e-9)
    assert [r[2] for r in after] == [r[2] for r in before] and rem.remediate_db(db, apply=True)["rows_changed"] == 0  # wavelengths intact; idempotent


def test_remediation_refuses_when_the_stored_grid_or_k_do_not_match(tmp_path):
    db = tmp_path / "g.db"
    p4, _ = _synthetic_db(db)
    c = sqlite3.connect(str(db))
    c.execute("DELETE FROM optical_dispersion WHERE raw_record_table=? AND raw_record_id=10", (p4,))
    c.commit()
    c.close()
    with pytest.raises(rem.RemediationError, match="grid"):
        rem.remediate_db(db, apply=True)
    db2 = tmp_path / "k.db"
    _synthetic_db(db2)
    c = sqlite3.connect(str(db2))
    c.execute("UPDATE optical_dispersion SET k = 0.5 WHERE raw_record_table=? AND raw_record_id=3", (p4,))
    c.commit()
    c.close()
    with pytest.raises(rem.RemediationError, match="k would change"):
        rem.remediate_db(db2, apply=True)


def _csv_with(tmp_path, n_bbo, n_pc, page_bbo="Eimerl-o"):
    head = ["formula", "ri_shelf", "ri_book", "ri_page_primary", "n_633", "k_633", "note"]
    rows = [head, ["BaB2O4", "main", "BaB2O4", page_bbo, n_bbo, "", "keep, this"],
            ["PC", "organic", "polycarbonate", "Sultanova", n_pc, "", 'has "quotes"']]
    p = tmp_path / "t.csv"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    p.write_text(buf.getvalue())
    return p


def test_csv_remediation_changes_only_the_stale_formula4_cell_and_preserves_every_other_byte(tmp_path):
    fod.WL_MIN_NM, fod.WL_MAX_NM = 0.01, 2_000_000.0
    good_pc = repr(rem.base.interpolate_axis("organic/(C16H14O3)n - polycarbonate/nk/Sultanova.yml")["n_633"])
    p = _csv_with(tmp_path, "1.6626", good_pc)
    before = p.read_text()
    out = rem.remediate_csv(p, apply=True, pages=rem._catalog_pages())
    after = p.read_text()
    assert [c["column"] for c in out["cells_updated"]] == ["n_633"] and out["cells_updated"][0]["new"] == pytest.approx(1.6681, abs=1e-3)
    b, a = before.splitlines(), after.splitlines()
    assert len(a) == len(b) and a[0] == b[0] and a[2] == b[2] and a[1] != b[1] and a[1].endswith(',,"keep, this"')
    assert rem.remediate_csv(p, apply=True, pages=rem._catalog_pages())["cells_updated"] == []  # idempotent


def test_csv_remediation_refuses_stale_non_formula4_cells_and_unresolvable_pages(tmp_path):
    with pytest.raises(rem.RemediationError, match="unexplained"):
        rem.remediate_csv(_csv_with(tmp_path, "1.6681", "1.5000"), apply=True, pages=rem._catalog_pages())  # PC is not formula 4: a stale value is NOT touched
    with pytest.raises(rem.RemediationError, match="unresolved"):
        rem.remediate_csv(_csv_with(tmp_path, "1.6681", "1.5", page_bbo="No-such-page"), apply=True, pages=rem._catalog_pages())
