#!/usr/bin/env python3
"""
scripts/match_ri_info_oxides.py
================================
Step 1 of the 50-oxide dataset task: match each of the 50 target materials
against refractiveindex.info's catalog-nk.yml (shelf/book/page index) and
report which exist, which have multiple candidate datasets, and which are
missing.

Does not fetch or write any n,k data -- that's Step 2/3. This only builds
the match table for CHECKPOINT 1.
"""

import json
import re
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = _ROOT / "refractiveindex_db" / "database" / "catalog-nk.yml"
DATA_ROOT = _ROOT / "refractiveindex_db" / "database" / "data"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oxide_material_list import MATERIALS_50  # noqa: E402

# name/formula/aliases for each of the 50 target materials, plus known
# RI.info book-id spellings to try (RI.info book ids are case-sensitive
# formula strings, occasionally with a polymorph suffix). Canonical source:
# scripts/oxide_material_list.py -- shared with build_oxides_csv.py so the
# polymorph field can't drift apart between the two steps again.
TARGETS = [
    dict(idx=m["idx"], name=m["name"], formula=m["formula"], polymorph=m["polymorph"],
         aliases=m["ri_aliases"])
    for m in MATERIALS_50
]

RELEVANT_SHELVES = {"main", "other"}


def flatten_catalog(catalog: list) -> list[dict]:
    """Return a flat list of {shelf, book, book_name, pages:[{page,name,data}]}."""
    books = []
    shelf = None
    for entry in catalog:
        if "SHELF" in entry:
            shelf = entry["SHELF"]
            for item in entry.get("content", []):
                if "BOOK" not in item:
                    continue  # DIVIDER within shelf content
                pages = []
                for p in item.get("content", []):
                    if "PAGE" not in p:
                        continue  # DIVIDER within book content
                    pages.append(dict(page=p["PAGE"], name=p.get("name", ""), data=p.get("data")))
                books.append(dict(shelf=shelf, book=item["BOOK"], book_name=item.get("name", ""), pages=pages))
    return books


def norm(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s).lower()


def find_matches(target: dict, books: list[dict]) -> list[dict]:
    aliases_norm = {norm(a) for a in target["aliases"]}
    hits = []
    for b in books:
        if b["shelf"] not in RELEVANT_SHELVES:
            continue
        if norm(b["book"]) in aliases_norm:
            hits.append(b)
    return hits


def wavelength_range_from_yaml(path: Path) -> str:
    try:
        with open(path) as fh:
            raw = yaml.safe_load(fh)
    except Exception as e:
        return f"<parse error: {e}>"
    ranges = []
    for block in raw.get("DATA", []):
        t = block.get("type", "")
        if t == "tabulated nk" or t == "tabulated n" or t == "tabulated k":
            lines = block["data"].strip().splitlines()
            lam = [float(line.split()[0]) for line in lines if line.strip()]
            if lam:
                ranges.append((min(lam), max(lam)))
        elif t.startswith("formula"):
            rng = block.get("wavelength_range") or block.get("range")
            if rng:
                vals = [float(x) for x in str(rng).split()]
                ranges.append((min(vals), max(vals)))
    if not ranges:
        return "?"
    lo = min(r[0] for r in ranges)
    hi = max(r[1] for r in ranges)
    return f"{lo:.3f}-{hi:.3f} um"


def main():
    with open(CATALOG_PATH) as f:
        catalog = yaml.safe_load(f)
    books = flatten_catalog(catalog)

    report = []
    for t in TARGETS:
        hits = find_matches(t, books)
        row = dict(idx=t["idx"], name=t["name"], formula=t["formula"], polymorph=t["polymorph"])
        if not hits:
            row["status"] = "MISSING"
            row["datasets"] = []
        else:
            datasets = []
            for b in hits:
                for p in b["pages"]:
                    wl = "?"
                    if p["data"]:
                        yaml_path = DATA_ROOT / p["data"]
                        if yaml_path.exists():
                            wl = wavelength_range_from_yaml(yaml_path)
                    datasets.append(dict(
                        shelf=b["shelf"], book=b["book"], page=p["page"],
                        page_name=p["name"], wl_range=wl, data_path=p["data"],
                    ))
            row["status"] = "MULTIPLE" if len(datasets) > 1 else "FOUND"
            row["datasets"] = datasets
        report.append(row)

    out_path = _ROOT / "data" / "ri_info_match_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    n_found = sum(1 for r in report if r["status"] in ("FOUND", "MULTIPLE"))
    n_multiple = sum(1 for r in report if r["status"] == "MULTIPLE")
    n_missing = sum(1 for r in report if r["status"] == "MISSING")
    print(f"Matched: {n_found}/50  (multiple datasets: {n_multiple})  Missing: {n_missing}")
    print(f"Wrote {out_path}")

    print("\n=== MISSING ===")
    for r in report:
        if r["status"] == "MISSING":
            print(f"  {r['idx']:2d}. {r['name']} ({r['formula']})")

    print("\n=== MULTIPLE DATASETS ===")
    for r in report:
        if r["status"] == "MULTIPLE":
            print(f"  {r['idx']:2d}. {r['name']} ({r['formula']}) -- {len(r['datasets'])} datasets")
            for d in r["datasets"]:
                print(f"       [{d['shelf']}/{d['book']}/{d['page']}] {d['page_name']}  ({d['wl_range']})")


if __name__ == "__main__":
    main()
