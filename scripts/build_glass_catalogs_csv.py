#!/usr/bin/env python3
"""
scripts/build_glass_catalogs_csv.py
===================================
Builds data/step1_selections_glass_catalogs.json, data/glass_catalogs.csv and data/glass_catalog_gaps.csv from the
manufacturer catalogs (scripts/glass_catalog_list.py) with the shared listed-pages builder. Offline: a catalog glass has no
formula, PubChem or Materials Project entry. A page another family already loads is skipped (listed in the gaps file).
"""
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from glass_catalog_list import materials, popular_equivalents  # noqa: E402
from listed_family import build  # noqa: E402


def other_families_data_paths():
    """Data files any other family loads: every selections file's axes, and the tracked base DB (oxides, batch 2, elements)."""
    paths = set()
    for f in sorted((_ROOT / "data").glob("step1_selections*.json")):
        if f.name == "step1_selections_glass_catalogs.json":
            continue
        def walk(x):
            if isinstance(x, dict):
                if isinstance(x.get("data_path"), str):
                    paths.add(x["data_path"])
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(json.loads(f.read_text()))
    con = sqlite3.connect(f"file:{_ROOT / 'data' / 'materials_oxide_test.db'}?mode=ro", uri=True)
    paths |= {p for (p,) in con.execute("SELECT DISTINCT raw_record_table FROM optical_dispersion")}
    return paths


def other_families_excluded_pages():
    """{(shelf, book, page): reason} of every page another family excluded on review (its *_gaps.csv, gap_kind excluded_page)."""
    import pandas as pd
    out = {}
    for f in sorted((_ROOT / "data").glob("*_gaps.csv")):
        if f.name == "glass_catalog_gaps.csv":
            continue
        g = pd.read_csv(f)
        if {"key", "gap_kind", "reason"} <= set(g.columns):
            for key, reason in g.loc[g.gap_kind == "excluded_page", ["key", "reason"]].values:
                parts = str(key).split("/")
                if len(parts) == 3:
                    out[tuple(parts)] = reason
    return out


def main():
    mats, skipped = materials(other_families_data_paths(), other_families_excluded_pages())
    excluded = dict(skipped)
    out_of_family = {f"popular_glass/{book}": "not loaded: its pages are the catalog pages themselves (the same data files); used as "
                                               "the list of cross-maker equivalents for the ML splits" for book in popular_equivalents()}
    build(mats, {}, out_of_family, "glass_catalogs", "glass_catalogs", "glass_catalog_gaps",
          formula_null_reason="formula NULL: a catalog optical glass (composition proprietary); no x-ray / neutron SLD",
          density_null_reason="density/SLD left NULL: the catalog page states no density",
          source_label="glass_catalog_list.py (manufacturer catalog, generated)")
    import pandas as pd  # the pages another family already holds are recorded, not silently dropped
    gaps = pd.read_csv(_ROOT / "data" / "glass_catalog_gaps.csv")
    extra = pd.DataFrame([dict(key=f"{s}/{b}/{p}", name=p, gap_kind=kind, reason=why) for (s, b, p), (kind, why) in excluded.items()])
    pd.concat([gaps, extra], ignore_index=True).to_csv(_ROOT / "data" / "glass_catalog_gaps.csv", index=False)


if __name__ == "__main__":
    main()
