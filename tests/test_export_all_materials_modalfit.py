"""Tests for scripts/export_all_materials_modalfit.py's _discover_materials().

Regression coverage for the same bug shape as _lookup_mp_id (see
materials_db.export.modalfit's docstring): this script used to read
exactly three hardcoded CSV filenames, which would silently miss a
renamed or newly-added batch CSV. _discover_materials() globs data/*.csv
instead -- this proves that directly, rather than trusting the current
three files happen to still be named what the code expects.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "export_all_materials_modalfit", ROOT / "scripts" / "export_all_materials_modalfit.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(ROOT / "src"))
_spec.loader.exec_module(_mod)


def test_discover_materials_is_filename_agnostic(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    pd.DataFrame([{"formula": "Aaa1", "name": "Fake A"}]).to_csv(
        tmp_path / "data" / "some_batch_nobody_expected.csv", index=False
    )
    pd.DataFrame([{"formula": "Bbb2", "name": "Fake B"}]).to_csv(
        tmp_path / "data" / "yet_another_2099_batch.csv", index=False
    )
    materials = _mod._discover_materials()
    assert set(materials["formula"]) == {"Aaa1", "Bbb2"}


def test_discover_materials_ignores_unrelated_csvs(tmp_path, monkeypatch):
    """A CSV without formula/name columns (e.g. a training manifest) must
    be silently skipped, not crash or get misread."""
    monkeypatch.setattr(_mod, "_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    pd.DataFrame([{"formula": "Ccc3", "name": "Fake C"}]).to_csv(
        tmp_path / "data" / "real_batch.csv", index=False
    )
    pd.DataFrame([{"unrelated_column": 1}]).to_csv(
        tmp_path / "data" / "not_a_material_csv.csv", index=False
    )
    materials = _mod._discover_materials()
    assert set(materials["formula"]) == {"Ccc3"}


def test_discover_materials_allows_duplicate_formula_across_csvs(tmp_path, monkeypatch):
    """Batch 3b made a shared formula legitimate: Diamond and Graphite are
    two distinct materials (different `name`) that genuinely share formula
    "C". Only a duplicate `name` -- the schema's real UNIQUE identity key
    -- is a real conflict; formula never was."""
    monkeypatch.setattr(_mod, "_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    pd.DataFrame([{"formula": "Dupe1", "name": "First"}]).to_csv(
        tmp_path / "data" / "batch_a.csv", index=False
    )
    pd.DataFrame([{"formula": "Dupe1", "name": "Second"}]).to_csv(
        tmp_path / "data" / "batch_b.csv", index=False
    )
    materials = _mod._discover_materials()
    assert set(materials["name"]) == {"First", "Second"}
    assert list(materials["formula"]) == ["Dupe1", "Dupe1"]


def test_discover_materials_raises_on_duplicate_name_across_csvs(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    pd.DataFrame([{"formula": "Aaa1", "name": "SameName"}]).to_csv(
        tmp_path / "data" / "batch_a.csv", index=False
    )
    pd.DataFrame([{"formula": "Bbb2", "name": "SameName"}]).to_csv(
        tmp_path / "data" / "batch_b.csv", index=False
    )
    with pytest.raises(AssertionError, match="more than one batch"):
        _mod._discover_materials()


def test_discover_materials_raises_on_case_insensitive_dirname_collision(tmp_path, monkeypatch):
    """Two distinct names that would collide once turned into a directory
    name on a case-insensitive filesystem (macOS default) must fail loudly
    rather than silently overwrite one material's export with another's --
    the exact incident this guards against, found live during batch 3b
    (a stale "TiN/" directory collided with "Tin/")."""
    monkeypatch.setattr(_mod, "_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    pd.DataFrame([{"formula": "Sn", "name": "Tin"}]).to_csv(
        tmp_path / "data" / "batch_a.csv", index=False
    )
    pd.DataFrame([{"formula": "TiN", "name": "TiN"}]).to_csv(
        tmp_path / "data" / "batch_b.csv", index=False
    )
    with pytest.raises(AssertionError, match="collide case-insensitively"):
        _mod._discover_materials()


# ---- family registry and output-dir safety (the script used to glob every CSV against one DB and rmtree its output folder)

def test_every_family_lists_a_db_and_csvs_whose_names_are_unique_within_the_family():
    for fam, (db, csvs, out) in _mod.FAMILIES.items():
        materials = _mod._discover_materials([ROOT / "data" / c for c in csvs])  # raises on a duplicate name inside ONE family
        assert len(materials) > 0, fam
    assert set(_mod.FAMILIES) == {"oxide", "nitride", "polymer", "inorganic3", "halide", "chalcogenide", "liquid"}
    assert len({v[2] for v in _mod.FAMILIES.values()}) == len(_mod.FAMILIES), "each family exports to its own folder"


def test_nitride_csv_alone_is_clean_although_globbing_all_csvs_hits_the_known_cross_family_duplicates():
    assert len(_mod._discover_materials([ROOT / "data" / "nitrides.csv"])) == 6
    with pytest.raises(AssertionError, match="more than one batch"):
        _mod._discover_materials()  # the glob mixes families: nitrides.csv repeats five batch-2 names


def test_prepare_out_dir_refuses_a_populated_folder_it_did_not_create(tmp_path):
    d = tmp_path / "curated"
    d.mkdir()
    (d / "hand_made.txt").write_text("keep me")
    with pytest.raises(SystemExit, match="Refusing to wipe"):
        _mod.prepare_out_dir(d)
    assert (d / "hand_made.txt").read_text() == "keep me"


def test_prepare_out_dir_wipes_only_its_own_and_accepts_new_or_empty(tmp_path):
    new, empty = tmp_path / "new", tmp_path / "empty"
    empty.mkdir()
    for d in (new, empty):
        _mod.prepare_out_dir(d)
        assert (d / _mod.OWNER_MARKER).exists()
    (new / "stale").mkdir()
    _mod.prepare_out_dir(new)  # created by the script -> may be rebuilt
    assert not (new / "stale").exists() and (new / _mod.OWNER_MARKER).exists()


def test_halide_family_exports_every_material_end_to_end(tmp_path):
    """Regression: halide optical labels carried no polymorph while the physical row did, so every halide was skipped."""
    import load_family_db  # noqa: F401  (scripts dir is on sys.path via other tests)
    pytest.importorskip("pandas")
    sys.path.insert(0, str(ROOT / "scripts"))
    import load_halides_db as wrap
    import load_family_db as fam
    db = tmp_path / "materials_halide_test.db"
    fam.run_family("halide", wrap.CSV_PATH, wrap.SELECTIONS_PATH, db, fresh=True, load_physical_fn=fam.load_physical_properties,
                   literature_title=wrap.LITERATURE_TITLE, literature_technique=wrap.LITERATURE_TECHNIQUE, literature_note=wrap.LITERATURE_NOTE)
    data = tmp_path / "data"
    data.mkdir()
    (data / "materials_halide_test.db").write_bytes(db.read_bytes())
    (data / "halides.csv").write_bytes((ROOT / "data" / "halides.csv").read_bytes())
    import unittest.mock as um
    with um.patch.object(_mod, "_ROOT", tmp_path):
        report = _mod.main(["--family", "halide", "--out-dir", str(tmp_path / "out"), "--strict"])
    assert (report["status"] == "OK").all() and len(report) == 21
