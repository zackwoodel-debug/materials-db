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
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = _ROOT / "refractiveindex_db" / "database" / "catalog-nk.yml"
DATA_ROOT = _ROOT / "refractiveindex_db" / "database" / "data"

# name/formula/aliases for each of the 50 target materials, plus known
# RI.info book-id spellings to try (RI.info book ids are case-sensitive
# formula strings, occasionally with a polymorph suffix).
TARGETS = [
    dict(idx=1,  name="Aluminium oxide / sapphire", formula="Al2O3", polymorph="corundum/sapphire", aliases=["Al2O3"]),
    dict(idx=2,  name="Beryllium oxide", formula="BeO", polymorph=None, aliases=["BeO"]),
    dict(idx=3,  name="Chrysoberyl", formula="BeAl2O4", polymorph="chrysoberyl", aliases=["BeAl2O4"]),
    dict(idx=4,  name="Beryllium hexaaluminate", formula="BeAl6O10", polymorph=None, aliases=["BeAl6O10"]),
    dict(idx=5,  name="Calcium gadolinium aluminate", formula="CaGdAlO4", polymorph=None, aliases=["CaGdAlO4"]),
    dict(idx=6,  name="Calcium yttrium aluminate", formula="CaYAlO4", polymorph=None, aliases=["CaYAlO4"]),
    dict(idx=7,  name="Spinel", formula="MgAl2O4", polymorph="spinel", aliases=["MgAl2O4"]),
    dict(idx=8,  name="Lanthanum aluminate", formula="LaAlO3", polymorph=None, aliases=["LaAlO3"]),
    dict(idx=9,  name="Barium borate (BBO)", formula="BaB2O4", polymorph="beta-BBO", aliases=["BaB2O4", "BBO"]),
    dict(idx=10, name="Bismuth triborate (BiBO)", formula="BiB3O6", polymorph=None, aliases=["BiB3O6", "BiBO3"]),
    dict(idx=11, name="Lithium triborate (LBO)", formula="LiB3O5", polymorph=None, aliases=["LiB3O5", "LBO"]),
    dict(idx=12, name="Cesium lithium borate (CLBO)", formula="CsLiB6O10", polymorph=None, aliases=["CsLiB6O10", "CLBO"]),
    dict(idx=13, name="Lutetium aluminium borate", formula="LuAl3(BO3)4", polymorph=None, aliases=["LuAl3(BO3)4", "LuAl3B4O12"]),
    dict(idx=14, name="Calcite", formula="CaCO3", polymorph="calcite", aliases=["CaCO3"]),
    dict(idx=15, name="Copper(II) oxide", formula="CuO", polymorph=None, aliases=["CuO"]),
    dict(idx=16, name="Copper(I) oxide", formula="Cu2O", polymorph=None, aliases=["Cu2O"]),
    dict(idx=17, name="Dysprosium oxide", formula="Dy2O3", polymorph=None, aliases=["Dy2O3"]),
    dict(idx=18, name="Hematite", formula="Fe2O3", polymorph="hematite", aliases=["Fe2O3"]),
    dict(idx=19, name="Magnetite", formula="Fe3O4", polymorph="magnetite", aliases=["Fe3O4"]),
    dict(idx=20, name="Germanium dioxide", formula="GeO2", polymorph=None, aliases=["GeO2"]),
    dict(idx=21, name="Bismuth germanate", formula="Bi12GeO20", polymorph="BGO", aliases=["Bi12GeO20", "BGO"]),
    dict(idx=22, name="Lead germanate", formula="Pb5Ge3O11", polymorph=None, aliases=["Pb5Ge3O11"]),
    dict(idx=23, name="Hafnium dioxide", formula="HfO2", polymorph=None, aliases=["HfO2"]),
    dict(idx=24, name="Lithium iodate", formula="LiIO3", polymorph=None, aliases=["LiIO3"]),
    dict(idx=25, name="Lutetium oxide", formula="Lu2O3", polymorph=None, aliases=["Lu2O3"]),
    dict(idx=26, name="LuAG", formula="Lu3Al5O12", polymorph="garnet", aliases=["Lu3Al5O12", "LuAG"]),
    dict(idx=27, name="Magnesium oxide", formula="MgO", polymorph=None, aliases=["MgO"]),
    dict(idx=28, name="Molybdenum dioxide", formula="MoO2", polymorph=None, aliases=["MoO2"]),
    dict(idx=29, name="Molybdenum trioxide", formula="MoO3", polymorph=None, aliases=["MoO3"]),
    dict(idx=30, name="Calcium molybdate", formula="CaMoO4", polymorph=None, aliases=["CaMoO4"]),
    dict(idx=31, name="Lead molybdate", formula="PbMoO4", polymorph=None, aliases=["PbMoO4"]),
    dict(idx=32, name="Strontium molybdate", formula="SrMoO4", polymorph=None, aliases=["SrMoO4"]),
    dict(idx=33, name="Niobium pentoxide", formula="Nb2O5", polymorph=None, aliases=["Nb2O5"]),
    dict(idx=34, name="Potassium niobate", formula="KNbO3", polymorph=None, aliases=["KNbO3"]),
    dict(idx=35, name="Lithium niobate", formula="LiNbO3", polymorph=None, aliases=["LiNbO3"]),
    dict(idx=36, name="Scandium oxide", formula="Sc2O3", polymorph=None, aliases=["Sc2O3"]),
    dict(idx=37, name="Silicon monoxide", formula="SiO", polymorph="amorphous", aliases=["SiO"]),
    dict(idx=38, name="Silicon dioxide / quartz", formula="SiO2", polymorph="alpha-quartz", aliases=["SiO2"]),
    dict(idx=39, name="Tantalum pentoxide", formula="Ta2O5", polymorph=None, aliases=["Ta2O5"]),
    dict(idx=40, name="TGG", formula="Tb3Ga5O12", polymorph="garnet", aliases=["Tb3Ga5O12", "TGG"]),
    dict(idx=41, name="Tellurium dioxide", formula="TeO2", polymorph=None, aliases=["TeO2"]),
    dict(idx=42, name="Titanium dioxide (rutile / anatase)", formula="TiO2", polymorph="rutile/anatase", aliases=["TiO2"]),
    dict(idx=43, name="Barium titanate", formula="BaTiO3", polymorph=None, aliases=["BaTiO3"]),
    dict(idx=44, name="Strontium titanate", formula="SrTiO3", polymorph=None, aliases=["SrTiO3"]),
    dict(idx=45, name="Vanadium dioxide", formula="VO2", polymorph=None, aliases=["VO2"]),
    dict(idx=46, name="Yttrium orthovanadate", formula="YVO4", polymorph=None, aliases=["YVO4"]),
    dict(idx=47, name="Tungsten trioxide", formula="WO3", polymorph=None, aliases=["WO3"]),
    dict(idx=48, name="Yttrium oxide", formula="Y2O3", polymorph=None, aliases=["Y2O3"]),
    dict(idx=49, name="YAG", formula="Y3Al5O12", polymorph="garnet", aliases=["Y3Al5O12", "YAG"]),
    dict(idx=50, name="Zinc oxide", formula="ZnO", polymorph=None, aliases=["ZnO"]),
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
