"""Materials Project ids for the ModalFit export, packaged so installed and checkout exports agree (docs/adr/0001).

mp_id is an external identifier (which calculated MP structure a density or descriptor came from), recorded per family in the
checkout's data/*.csv. build_map() derives formula -> mp_id from those files with exactly the rule the exporter has always used
(every data/*.csv with "formula" and "mp_id" columns, in filename order, whatever it is called; the first row with the formula in
a file; the first file whose row has an id wins). scripts/build_mp_id_map.py writes the result to mp_ids.json next to this
module, which ships in the wheel; tests/test_mp_id_map.py fails if it is stale. The ids are redistributed under the Materials
Project's CC BY 4.0 terms with its attribution (DATA_LICENSE.md), as the release's family tables already do.

Note: the lookup is by formula, so materials sharing a formula (polymorphs) share whatever id the first matching row records.
"""
import json
from pathlib import Path

MAP_PATH = Path(__file__).with_name("mp_ids.json")

FOUND = "found"
NO_MP_ENTRY = "no_mp_entry_recorded"          # the formula is in a family table, which records no MP id for it
NOT_IN_TABLES = "formula_not_in_family_tables"
MAP_UNAVAILABLE = "id_map_unavailable"        # the packaged map could not be read: the id is unknown, not absent
STATUSES = (FOUND, NO_MP_ENTRY, NOT_IN_TABLES, MAP_UNAVAILABLE)


def build_map(data_dir):
    """formula -> mp_id (str) or None, and the files read. The exporter's historical rule, unchanged."""
    import pandas as pd

    out, files = {}, []
    for csv_path in sorted(Path(data_dir).glob("*.csv")):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue
        if "formula" not in df.columns or "mp_id" not in df.columns:
            continue
        files.append(csv_path.name)
        for formula in df["formula"].dropna().unique():
            if out.get(formula):
                continue  # an earlier file already gave this formula an id
            val = df[df["formula"] == formula].iloc[0].get("mp_id")
            out[formula] = str(val) if pd.notna(val) else out.get(formula)
    return dict(sorted(out.items())), files


_cache = {}


def load_map():
    """The packaged map ({formula: mp_id or None}), or None if it cannot be read."""
    if "map" not in _cache:
        try:
            _cache["map"] = json.loads(MAP_PATH.read_text())["formulas"]
        except (OSError, ValueError, KeyError):
            _cache["map"] = None
    return _cache["map"]


def lookup(formula):
    """(mp_id or None, status). Never guesses: a missing id says why it is missing."""
    ids = load_map()
    if ids is None:
        return None, MAP_UNAVAILABLE
    if formula not in ids:
        return None, NOT_IN_TABLES
    return (ids[formula], FOUND) if ids[formula] else (None, NO_MP_ENTRY)
