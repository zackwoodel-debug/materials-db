"""The packaged Materials Project id map (materials_db/export/mp_ids.json, docs/adr/0001) is exactly what the family tables in
data/*.csv give today, and a missing id always says why it is missing."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.export import mp_ids  # noqa: E402


def test_packaged_map_is_not_stale():
    ids, files = mp_ids.build_map(ROOT / "data")
    doc = json.loads(mp_ids.MAP_PATH.read_text())
    assert doc["formulas"] == ids, "data/*.csv changed: run python3 scripts/build_mp_id_map.py"
    assert doc["source_files"] == files


def test_each_missing_id_says_why():
    assert mp_ids.lookup("Al2O3") == ("mp-1143", mp_ids.FOUND)
    no_entry = next(f for f, v in json.loads(mp_ids.MAP_PATH.read_text())["formulas"].items() if v is None)
    assert mp_ids.lookup(no_entry) == (None, mp_ids.NO_MP_ENTRY)
    assert mp_ids.lookup("NotARealFormulaXYZ") == (None, mp_ids.NOT_IN_TABLES)


def test_an_unreadable_map_is_reported_not_treated_as_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(mp_ids, "MAP_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(mp_ids, "_cache", {})
    assert mp_ids.lookup("Al2O3") == (None, mp_ids.MAP_UNAVAILABLE)


def test_the_export_records_the_status_next_to_the_id(tmp_path, monkeypatch):
    import sqlite3
    from materials_db.export.modalfit import export_layer
    monkeypatch.chdir(tmp_path)  # export_layer writes its n,k file to the working directory
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'materials_oxide_test.db'}?mode=ro", uri=True)
    block = export_layer(con, "Aluminium oxide / sapphire")["materials_db"]
    assert (block["mp_id"], block["mp_id_status"]) == ("mp-1143", mp_ids.FOUND)
