#!/usr/bin/env python3
"""
scripts/material_registry.py
============================
Permanent material identifiers. data/material_registry.json maps a STABLE KEY to a material_id that never changes between releases:
a model, a split or a label file keyed by material_id stays valid in every later release. Before this, material_id was the load
order, and 150 of 379 materials changed id between v0.12.0 and v0.13.0.

Stable key (not the display name, which may be edited):
    <family table>:<selection_key>                    families whose table has a selection_key (e.g. semiconductors:GaAs)
    <family table>:<formula>[@<polymorph>]            the four earliest families (e.g. oxides_50:TiO2@rutile, batch3b_4:C@graphite)

Rules
  * The release build renumbers every material to its registry id (build stage 1b) and stops when a material has no entry.
  * A new material is registered only on request (build_release.py --register-new): it gets next_id, in key order. The registry
    file then has to be committed with the change that adds the material.
  * An id is never reused: a material that leaves the release keeps its entry (reported as absent in the manifest).

Seeded from the published v0.13.0 (its ids became permanent):
    python3 scripts/material_registry.py --seed-from release/materials-db-v0.13.0
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = _ROOT / "data" / "material_registry.json"
MATERIAL_TABLES = ["optical_dispersion", "physical_properties", "chemical_descriptors", "consensus_properties", "dataset_validation",
                   "material_synonyms", "mechanical_properties", "rheology"]
OFFSET = 10_000_000  # temporary id range while renumbering, far above any real id


class RegistryError(RuntimeError):
    pass


def _clean(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else str(v)


def material_key(stem, row):
    sk = _clean(row.get("selection_key"))
    if sk:
        return f"{stem}:{sk}"
    poly = _clean(row.get("polymorph"))
    return f"{stem}:{_clean(row.get('formula'))}" + (f"@{poly}" if poly else "")


def keys_by_name(family_rows):
    """material name -> stable key; raises if two materials would share a key."""
    out, seen = {}, {}
    for name, (stem, row) in family_rows.items():
        k = material_key(stem, row or {})
        if k in seen:
            raise RegistryError(f"stable key {k!r} would name both {seen[k]!r} and {name!r}")
        seen[k] = name
        out[name] = k
    return out


def load(path=REGISTRY):
    return json.loads(Path(path).read_text())


def save(reg, path=REGISTRY):
    reg["materials"] = dict(sorted(reg["materials"].items(), key=lambda kv: kv[1]["id"]))
    Path(path).write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n")


def assign(conn, family_rows, version, register_new=False, path=REGISTRY):
    """Renumber every material of the build to its registry id. Returns facts for the manifest."""
    reg = load(path)
    keys = keys_by_name(family_rows)
    mats = conn.execute("SELECT material_id, name FROM materials").fetchall()
    unregistered = sorted(keys[name] for _, name in mats if keys[name] not in reg["materials"])
    registered_now = []
    if unregistered:
        if not register_new:
            raise RegistryError(f"{len(unregistered)} material(s) have no permanent id: {unregistered[:8]}; rerun the build with "
                                "--register-new and commit data/material_registry.json with the change that adds them")
        for k in unregistered:  # key order: deterministic
            reg["materials"][k] = dict(id=reg["next_id"], name=next(n for n, kk in keys.items() if kk == k), registered_in=version)
            registered_now.append(dict(key=k, id=reg["next_id"]))
            reg["next_id"] += 1
        save(reg, path)
    mapping = {old: reg["materials"][keys[name]]["id"] for old, name in mats}
    if len(set(mapping.values())) != len(mapping):
        raise RegistryError("two materials map to one registry id")
    conn.execute("CREATE TEMP TABLE idmap (old INTEGER PRIMARY KEY, new INTEGER NOT NULL)")
    conn.executemany("INSERT INTO idmap VALUES (?, ?)", sorted(mapping.items()))
    conn.execute(f"UPDATE materials SET material_id = material_id + {OFFSET}")
    conn.execute(f"UPDATE materials SET material_id = (SELECT new FROM idmap WHERE old = material_id - {OFFSET})")
    for t in MATERIAL_TABLES:
        conn.execute(f"UPDATE {t} SET material_id = (SELECT new FROM idmap WHERE old = {t}.material_id)")
    conn.execute("DROP TABLE idmap")
    present = {keys[name] for _, name in mats}
    names_changed = [dict(key=keys[n], registered_name=reg["materials"][keys[n]]["name"], name=n) for _, n in mats
                     if reg["materials"][keys[n]]["name"] != n]
    return dict(materials=len(mats), registered_now=registered_now, next_id=reg["next_id"],
                absent_from_this_release=sorted(k for k in reg["materials"] if k not in present), name_changes=names_changed)


def export_csv(conn, out_path, family_rows):
    keys = keys_by_name(family_rows)
    rows = [dict(material_id=mid, key=keys[name], name=name) for mid, name in conn.execute("SELECT material_id, name FROM materials ORDER BY 1")]
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return len(rows)


def seed(release_dir, path=REGISTRY):
    sys.path.insert(0, str(_ROOT / "scripts"))
    import build_release as br
    rel = Path(release_dir)
    db = next(rel.glob("materials-db-v*.sqlite"))
    version = json.loads((rel / "MANIFEST.json").read_text())["version"]
    keys = keys_by_name(br.family_rows())
    mats = sqlite3.connect(str(db)).execute("SELECT material_id, name FROM materials").fetchall()
    missing = [n for _, n in mats if n not in keys]
    if missing:
        raise RegistryError(f"release materials not in the current family tables: {missing[:5]}")
    reg = dict(description="Permanent material ids (scripts/material_registry.py). Never edit an id; never reuse one.",
               seeded_from=f"materials-db v{version}", next_id=max(m for m, _ in mats) + 1,
               materials={keys[n]: dict(id=m, name=n, registered_in=version) for m, n in mats})
    save(reg, path)
    return len(mats), reg["next_id"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed-from", type=Path, required=True, help="release folder whose ids become permanent")
    a = ap.parse_args()
    n, nxt = seed(a.seed_from)
    print(f"seeded {n} materials from {a.seed_from.name}; next_id {nxt} -> {REGISTRY.relative_to(_ROOT)}")
