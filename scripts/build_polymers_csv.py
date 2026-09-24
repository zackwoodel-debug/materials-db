#!/usr/bin/env python3
"""
scripts/build_polymers_csv.py
==============================
Phase 1 tiered catalog. Reads data/polymer_ri_matches.json (run match_ri_info_polymers.py first) and writes:
  data/polymers.csv      -- candidates that get a material row: Tier 1 (FOUND = selected, MULTIPLE = selection pending your decision)
  data/polymer_gaps.csv  -- everything else, one row per gap: whole candidates (Tier 2/3/4/BLOCKED) and per-property density gaps.
Together they partition the candidate pool. materialclass='polymer' on every catalog row. No chemical descriptors, no PubChem/SMILES
here (Phase 3). Density / SLD stay NULL: no polymer in this repo has a traceable density source (see density_gap rows).
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
import sys

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymer_material_list import GRADE_NOTES  # noqa: E402

DATA = _ROOT / "data"
DENSITY_GAP = ("no traceable density source: RI.info pages state none, and the DB's legacy density values are tagged "
               "'Migration fallback for legacy records without reference'. Left NULL; SLD not derived.")
FORMULA_NULL = "formula not stated by source (grade-specific commercial material): formula NULL (valid), never a placeholder token"


def existing_db_names():
    """Read-only look at materials_normalized.db for name collisions (never written)."""
    con = sqlite3.connect(f"file:{DATA / 'materials_normalized.db'}?mode=ro", uri=True)
    rows = {r[1].lower(): (r[0], r[2]) for r in con.execute("SELECT material_id, name, formula FROM materials")}
    con.close()
    return rows


def main():
    m = json.loads((DATA / "polymer_ri_matches.json").read_text())
    db = existing_db_names()
    alias = {"PS": "polystyrene", "PMMA": "pmma", "PDMS": "pdms", "PEI": "pei", "PVA": "pva", "PTFE": "ptfe", "PEEK": "peek",
             "PA66": "nylon66", "PEG": "peg"}
    cat, gaps = [], []
    for i, c in enumerate(m["candidates"], start=1):
        hit = db.get(alias.get(c["key"], "\0"))
        collision = (f"materials_normalized.db already has '{c['key']}' (id {hit[0]}, formula {hit[1]}); separate DB here, matters at merge"
                     if hit else None)
        ds = [d for d in c["datasets"] if d["kind"] != "k-only"]
        if c["tier"] == 1:
            gaps.append(dict(name=c["name"], key=c["key"], gap_kind="density", tier=1, reason=DENSITY_GAP, ri_match=None, citation=None,
                             note=None))
            if c["status"] == "DEFERRED":
                gaps.append(dict(name=c["name"], key=c["key"], gap_kind="deferred", tier=1,
                                 reason=f"DEFERRED (not covered by this PR): {c['deferred_reason']}",
                                 ri_match=f"{c['n_dispersion_datasets']} dispersion-capable datasets; selection left null", citation=None,
                                 note=" ; ".join(x for x in (c["note"], collision) if x) or None))
                continue
            for ex in c.get("excluded_datasets", []):
                gaps.append(dict(name=c["name"], key=f"{c['key']}:{ex['page']}", gap_kind="excluded_dataset", tier=1, reason=ex["reason"],
                                 ri_match=ex["page"], citation=None, note="dataset excluded; the material itself is loaded from the selected dataset(s)"))
            formula = c["formula_ri"]  # NULL is valid for a polymer row
            notes = f"grade: {GRADE_NOTES[c['key']]}" if c["key"] in GRADE_NOTES else None
            flags = [f for f in (c["note"], collision, FORMULA_NULL if not formula else None) if f]
            sel_paths = {x["data_path"] for x in json.loads((DATA / "step1_selections_polymers.json").read_text())[c["key"]]["axes"]}
            if c["status"] == "SELECTED_BY_USER":
                flags.append("multi-match resolved by user: " + "; ".join(f"{d['book']}/{d['page']}" for d in ds if d["data_path"] in sel_paths))
            if c["k_only_datasets"]:
                flags.append(f"k-only pages not counted (no n): {', '.join(c['k_only_datasets'])}")
            chosen = [d for d in ds if d["data_path"] in sel_paths]  # by path: SU-8 2000/3000 both use page id 'specs'
            cat.append(dict(idx=i, name=c["name"], formula=formula, notes=notes, abbreviation=c["key"], polymer_group=c["group"],
                            materialclass="polymer", tier=1, status=c["status"], selection_key=c["key"],
                            ri_shelf="|".join(sorted({d["shelf"] for d in chosen})), ri_book="|".join(sorted({d["book"] for d in chosen})),
                            n_selected_datasets=len(chosen), needs_specific_formulation=False,
                            density_g_cm3=None, density_source=None, flags=" ; ".join(flags)))
            continue
        reason = {
            "BLOCKED": "needs_specific_formulation: identity undefined without composition / doping / cure state; never auto-loaded",
            2: "dispersion exists in citable literature but not on RI.info; citation logged only, NOT transcribed or fetched this run",
            3: "single-point n only, no dispersion" + ("; no traceable density source, so no material row" if c["tier"] == 3 else ""),
            4: "no RI.info dataset and no traceable in-repo source; no material row",
        }[c["tier"]]
        gaps.append(dict(name=c["name"], key=c["key"], gap_kind="material", tier=c["tier"], reason=reason,
                         ri_match=" ; ".join(f"{d['shelf']}/{d['book']}/{d['page']}" for d in c["datasets"]) or None,
                         citation=" | ".join(c["citations"]) or None,
                         note=" ; ".join(x for x in (c["note"], collision) if x) or None))
    pd.DataFrame(cat).to_csv(DATA / "polymers.csv", index=False)
    pd.DataFrame(gaps).to_csv(DATA / "polymer_gaps.csv", index=False)
    g = pd.DataFrame(gaps)
    print(f"polymers.csv: {len(cat)} rows | polymer_gaps.csv: {len(gaps)} rows | by kind: {g.gap_kind.value_counts().to_dict()}")
    print(g[g.gap_kind == "material"].groupby("tier").size().to_dict())


if __name__ == "__main__":
    main()
