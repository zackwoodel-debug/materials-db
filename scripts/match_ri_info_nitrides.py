#!/usr/bin/env python3
"""
scripts/match_ri_info_nitrides.py
==================================
Nitride equivalent of match_ri_info_oxides.py (reuses its catalog flattening / matching / wavelength-range
helpers). Writes data/nitride_ri_matches.json and data/step1_selections_nitrides.json and prints a
matched / multi-match / missing report.

Selection policy (never auto-pick):
  * candidate with a human-made prior selection (batches 2/3b) -> that selection is carried over, labelled
    exactly as load_batch2_db.py labelled it;
  * every other matched candidate -> selection null (multi-match or no prior decision): optical load is
    skipped and the candidate is flagged for the user;
  * missing candidates get no selection entry; build_nitrides_csv.py writes them to nitride_gaps.csv.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from match_ri_info_oxides import CATALOG_PATH, DATA_ROOT, find_matches, flatten_catalog, wavelength_range_from_yaml  # noqa: E402
from nitride_material_list import CANDIDATES, CARRY_OVER, EXCLUDED_DATASETS, USER_SELECTIONS  # noqa: E402
from fluoride_nitride_sulfide_material_list import MATERIALS_31  # noqa: E402
from load_family_db import label_join  # noqa: E402

MATCHES_OUT = _ROOT / "data" / "nitride_ri_matches.json"
SELECTIONS_OUT = _ROOT / "data" / "step1_selections_nitrides.json"


def paper_key(page: str) -> str:
    for suf in ("-o", "-e", "-alpha", "-beta", "-gamma"):
        if page.endswith(suf):
            return page[: -len(suf)]
    return page


def main():
    books = flatten_catalog(yaml.safe_load(open(CATALOG_PATH)))
    batch2 = {m["formula"]: m for m in MATERIALS_31}
    matches, selections = [], {}

    for c in CANDIDATES:
        hits = find_matches(dict(aliases=c["ri_aliases"]), books)
        datasets = []
        for b in hits:
            for p in b["pages"]:
                path = DATA_ROOT / p["data"] if p["data"] else None
                datasets.append(dict(shelf=b["shelf"], book=b["book"], page=p["page"], page_name=p["name"],
                                     data_path=p["data"], wl_range=wavelength_range_from_yaml(path) if path and path.exists() else "?"))
        papers = defaultdict(list)
        for d in datasets:
            papers[paper_key(d["page"])].append(d["page"])
        status = "MISSING" if not datasets else ("MULTIPLE" if len(papers) > 1 else "FOUND")
        key = c["selection_key"]
        prior = key in CARRY_OVER and status != "MISSING"
        user = key in USER_SELECTIONS and status != "MISSING"
        matches.append(dict(name=c["name"], formula=c["formula"], selection_key=key, status=status,
                            n_papers=len(papers), papers=dict(papers), datasets=datasets, prior_selection=prior,
                            user_selection=user,
                            excluded_pages=[pg for pg, _ in EXCLUDED_DATASETS.get(key, [])],
                            note=("BN book on RI.info holds only h-BN pages; no cubic-BN dataset" if key == "BN-cubic" else None)))
        if status == "MISSING":
            continue
        if prior:
            m = batch2[CARRY_OVER[key]]
            poly = m["polymorph"]
            selections[key] = dict(
                name=m["name"], polymorph=poly, effective_polymorph=poly, source="carried over from batch2/3b (human selection)",
                axes=[dict(page=a["page"], axis=a["axis"], data_path=a["data_path"],
                           dataset_label=label_join(poly, a["source_label"], a["axis"])) for a in m["ri_axes"]])
        elif user:
            u = USER_SELECTIONS[key]
            by_page = {d["page"]: d for d in datasets}
            axes = []
            for page, tag in u["pages"]:
                if page not in by_page:
                    raise SystemExit(f"{key}: selected page {page!r} not in RI catalog")
                axes.append(dict(page=page, axis=u["axis"], data_path=by_page[page]["data_path"],
                                 dataset_label=label_join(u["polymorph"], tag)))  # isotropic: axis segment omitted
            selections[key] = dict(name=c["name"], polymorph=u["polymorph"], effective_polymorph=u["polymorph"],
                                   source="user decision (Luke primary, Philipp secondary)", basis=u["basis"], axes=axes)
        else:
            selections[key] = None  # flagged for the user; never auto-picked

    MATCHES_OUT.write_text(json.dumps(matches, indent=2))
    SELECTIONS_OUT.write_text(json.dumps(selections, indent=2))

    print(f"{'formula':8} {'status':9} {'papers':>6}  note")
    for m in matches:
        tag = "prior selection carried over" if m["prior_selection"] else "user selection" if m["user_selection"] else ("SELECTION NULL -> flag for user" if m["status"] != "MISSING" else "gap")
        print(f"{m['selection_key']:8} {m['status']:9} {m['n_papers']:>6}  {tag}")
    n = lambda s: sum(m["status"] == s for m in matches)
    print(f"\nmatched(one paper)={n('FOUND')}  multi-match={n('MULTIPLE')}  missing={n('MISSING')}")
    print(f"Wrote {MATCHES_OUT.name}, {SELECTIONS_OUT.name}")


if __name__ == "__main__":
    main()
