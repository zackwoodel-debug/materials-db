"""scripts/material_registry.py: permanent material ids. Synthetic databases show that an id survives when materials are added,
removed or reordered, that an unregistered material stops the build unless registration is asked for, and that ids are never
reused. The committed registry is checked against the family tables and the published v0.13.0."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import material_registry as mreg  # noqa: E402

REG = json.loads(mreg.REGISTRY.read_text())


def _db(names):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT)")
    for t in mreg.MATERIAL_TABLES:
        c.execute(f"CREATE TABLE {t} (material_id INTEGER, tag TEXT)")
    for i, n in enumerate(names, start=1):  # load order decides the provisional ids, as in a real build
        c.execute("INSERT INTO materials VALUES (?, ?)", (i, n))
        for t in mreg.MATERIAL_TABLES:
            c.execute(f"INSERT INTO {t} VALUES (?, ?)", (i, f"{t}:{n}"))
    return c


def _rows(names):
    return {n: ("fam", {"selection_key": n}) for n in names}


def _registry(tmp_path, entries, next_id):
    p = tmp_path / "reg.json"
    p.write_text(json.dumps(dict(next_id=next_id, materials={f"fam:{n}": dict(id=i, name=n) for n, i in entries.items()})))
    return p


def _ids(c):
    return dict(c.execute("SELECT name, material_id FROM materials"))


def test_ids_survive_a_new_material_loaded_first(tmp_path):
    reg = _registry(tmp_path, {"A": 1, "B": 2}, 3)
    c = _db(["NEW", "A", "B"])  # the new material arrives first, so it would take id 1 by load order
    facts = mreg.assign(c, _rows(["NEW", "A", "B"]), "9.9.9", register_new=True, path=reg)
    assert _ids(c) == {"A": 1, "B": 2, "NEW": 3} and facts["registered_now"] == [dict(key="fam:NEW", id=3)]
    for t in mreg.MATERIAL_TABLES:  # every child row follows its material
        assert dict((tag.split(":")[1], mid) for mid, tag in c.execute(f"SELECT material_id, tag FROM {t}")) == _ids(c)
    assert json.loads(reg.read_text())["next_id"] == 4


def test_an_unregistered_material_stops_the_build(tmp_path):
    reg = _registry(tmp_path, {"A": 1}, 2)
    with pytest.raises(mreg.RegistryError, match="no permanent id"):
        mreg.assign(_db(["A", "NEW"]), _rows(["A", "NEW"]), "9.9.9", path=reg)
    assert json.loads(reg.read_text())["next_id"] == 2  # nothing registered silently


def test_a_removed_material_keeps_its_id_retired(tmp_path):
    reg = _registry(tmp_path, {"A": 1, "GONE": 2, "B": 3}, 4)
    c = _db(["B", "A"])
    facts = mreg.assign(c, _rows(["B", "A"]), "9.9.9", path=reg)
    assert _ids(c) == {"A": 1, "B": 3} and facts["absent_from_this_release"] == ["fam:GONE"]
    c2 = _db(["A", "B", "LATE"])
    mreg.assign(c2, _rows(["A", "B", "LATE"]), "9.9.9", register_new=True, path=reg)
    assert _ids(c2)["LATE"] == 4  # the retired id 2 is never reused


def test_committed_registry_covers_every_family_material_with_unique_ids():
    import build_release as br
    keys = mreg.keys_by_name(br.family_rows())
    assert set(keys.values()) == set(REG["materials"])
    ids = [v["id"] for v in REG["materials"].values()]
    assert len(ids) == len(set(ids)) and REG["next_id"] > max(ids)


def test_seeded_ids_are_the_published_v0_13_0_ids():
    rel = ROOT / "release" / "materials-db-v0.13.0"
    if not rel.exists():
        pytest.skip("v0.13.0 not built locally")
    published = dict(sqlite3.connect(str(next(rel.glob("*.sqlite")))).execute("SELECT name, material_id FROM materials"))
    assert {v["name"]: v["id"] for v in REG["materials"].values() if v.get("registered_in") == "0.13.0"} == published
