"""Batch 3b runs on the shared family loader (Phase 5 pilot) with its policies explicit, and the tracked base DB
(data/materials_oxide_test.db) is reproducible from its committed inputs with the current loaders.

The parity reference is the tracked base DB itself: before the pilot, rebuilding it with the original batch-3b loader gave the
same content (record_id aside: an insertion counter the resampling script renumbered); the pilot's rebuild was identical to the
original loader's output in every table and column, ids included. This test keeps both true.
"""
import collections
import io
import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_batch3b_selections  # noqa: E402
import load_family_db as fam  # noqa: E402

TRACKED = ROOT / "data" / "materials_oxide_test.db"


def _rows(db, sql):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute(sql).fetchall()


def test_selections_file_is_generated_from_the_curated_list():
    on_disk = json.loads((ROOT / "data" / "step1_selections_batch3b.json").read_text())
    assert on_disk == build_batch3b_selections.selections(), "run: python3 scripts/build_batch3b_selections.py"


def test_the_tracked_base_db_is_reproducible_from_its_inputs(tmp_path, monkeypatch):
    import load_oxides_db as ox
    import load_batch2_db
    import load_pure_element_db
    import load_batch3b_db

    db = tmp_path / "base.db"
    monkeypatch.setattr(ox, "DB_PATH", db)
    with contextlib.redirect_stdout(io.StringIO()):
        ox.main([])
        load_batch2_db.main()
        load_pure_element_db.main()
        report = load_batch3b_db.main()
    assert report.skipped == [] and report.conflicts == [] and report.warnings == []
    tables = [t for (t,) in _rows(TRACKED, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    for t in tables:
        if t == "optical_dispersion":  # compared by content: record_id / raw_record_id are insertion counters
            cols = "material_id, wavelength_nm, n, k, temperature_c, dataset_label, raw_record_table, source_id"
            assert collections.Counter(_rows(db, f"SELECT {cols} FROM {t}")) == collections.Counter(_rows(TRACKED, f"SELECT {cols} FROM {t}"))
        else:
            assert sorted(_rows(db, f"SELECT * FROM {t}")) == sorted(_rows(TRACKED, f"SELECT * FROM {t}")), t
    graphite = _rows(db, "SELECT inchikey FROM materials WHERE name = 'Graphite'")
    assert graphite == [(None,)]  # the batch's InChIKey policy: Diamond keeps it, Graphite stores NULL


def test_the_new_options_default_to_the_previous_behaviour(tmp_path):
    cat = tmp_path / "cat.csv"
    cat.write_text("name,formula,inchikey\nA,C,KEY\nB,C,KEY\n")
    with pytest.raises(fam.CatalogError, match="duplicate selection_key"):  # formula keys collide by default
        fam.load_catalog(cat)
    with pytest.raises(fam.CatalogError, match="duplicate inchikey"):  # duplicate InChIKeys refused by default
        fam.load_catalog(cat, selection_key_column="name")
    df = fam.load_catalog(cat, selection_key_column="name", allow_duplicate_inchikey=True)
    assert list(df["selection_key"]) == ["A", "B"]
