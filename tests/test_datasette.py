"""scripts/build_datasette.py: the browse bundle. Metadata describes every column of the release (from the data dictionary),
saved queries run on the release, the material index agrees with the release's family tables and the ML set, and the release
file is linked, never copied or changed. Needs a built release; Datasette itself is not needed."""
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from materials_db.access import AccessError, find_release  # noqa: E402

try:
    find_release()
except AccessError:
    pytest.skip("no release built locally", allow_module_level=True)

import build_datasette as bd  # noqa: E402

PARAMS = {"material": "Gallium arsenide", "wavelength_nm": 633, "n_min": 2.4, "n_max": 2.5}


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out, idx, meta = bd.build(out_root=tmp_path_factory.mktemp("browse"))
    return out, idx, meta


def test_release_file_is_linked_unchanged(bundle):
    out, _, _ = bundle
    link = out / "materials-db.sqlite"
    rel = find_release()[1]
    before = hashlib.sha256(rel.read_bytes()).hexdigest()
    assert link.is_symlink() and link.resolve() == rel.resolve()
    manifest = find_release()[0] / "SHA256SUMS"
    if manifest.exists():
        assert before in manifest.read_text()


def test_metadata_describes_every_release_column(bundle):
    out, _, meta = bundle
    con = sqlite3.connect(find_release()[1])
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    described = meta["databases"][bd.DB_NAME]["tables"]
    for t in tables:
        if t in ("spr_data", "xrr_data"):  # legacy empty tables the dictionary does not cover
            continue
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
        assert set(cols) <= set(described[t]["columns"]), t
        assert all(described[t]["columns"][c] for c in cols), t
    idx_cols = [c[1] for c in sqlite3.connect(out / "families.db").execute("PRAGMA table_info(material_index)")]
    assert idx_cols == list(bd.INDEX_COLUMNS)


@pytest.mark.parametrize("db,name", [(db, q) for db, qs in bd.CANNED.items() for q in qs])
def test_saved_queries_run(bundle, db, name):
    out, _, _ = bundle
    sql = bd.CANNED[db][name]["sql"]
    con = sqlite3.connect(find_release()[1] if db == bd.DB_NAME else out / "families.db")
    params = {p: PARAMS[p] for p in set(re.findall(r":(\w+)", sql))}
    rows = con.execute(sql, params).fetchall()
    assert rows, name
    assert sql.lstrip().upper().startswith("SELECT")


def test_index_shows_published_values(bundle):
    """n_633 is the family table's published value where the table has one; only polymers are interpolated, and those match
    the ML set (same interpolation)."""
    _, idx, _ = bundle
    rel_dir = find_release()[0]
    fam = {}
    for csv in sorted((rel_dir / "family_tables").glob("*.csv")):
        if csv.stem.endswith("_gaps"):
            continue
        t = pd.read_csv(csv)
        for _, r in t.iterrows():
            fam.setdefault(r["name"], (r.get("n_633"), r.get("k_633"), "n_633" in t))
    fm = pd.read_parquet(ROOT / "data" / "ML_release_feature_matrix.parquet", columns=["material_id", "target_n_633nm"]).set_index("material_id")
    n_family = n_interp = 0
    for r in idx.itertuples():
        fn, fk, has_col = fam[r.name]
        if has_col:
            assert (pd.isna(r.n_633) and pd.isna(fn)) or r.n_633 == fn, r.name
            assert r.n_633_origin == ("family table" if pd.notna(fn) else None)
            n_family += pd.notna(fn)
        else:
            ml = fm.target_n_633nm.get(r.material_id)
            assert (pd.isna(r.n_633) and pd.isna(ml)) or abs(r.n_633 - ml) < 1e-9, r.name
            n_interp += pd.notna(r.n_633)
    assert n_family > 250 and n_interp > 20
    assert idx.material_id.is_unique and len(idx) == len(fm)


def test_family_tables_copied_whole(bundle):
    out, _, _ = bundle
    con = sqlite3.connect(out / "families.db")
    for csv in sorted((find_release()[0] / "family_tables").glob("*.csv")):
        assert con.execute(f'SELECT COUNT(*) FROM "{csv.stem}"').fetchone()[0] == len(pd.read_csv(csv))


def test_serve_command_names_the_bundle(bundle):
    out, _, _ = bundle
    cmd = bd.serve_command(out)
    assert "-i" in cmd and "metadata.json" in cmd and "families.db" in cmd
