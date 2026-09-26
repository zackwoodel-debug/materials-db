#!/usr/bin/env python3
"""
scripts/match_ri_info_polymers.py
==================================
Polymer equivalent of match_ri_info_nitrides.py. Scans the RI.info catalog (organic, other, 3d/plastics aliases -- the scan is
AUTHORITATIVE over the candidate list), matches scripts/polymer_material_list.CANDIDATES and writes
data/polymer_ri_matches.json + data/step1_selections_polymers.json.

Tiers (computed, never assumed):
  1 = >=1 dispersion-capable RI.info dataset (tabulated n[,k] with >1 wavelength, or an n dispersion formula)
  2 = no RI.info dataset, but a literature citation is already recorded in this repo (cite only)
  3 = RI.info has only single-wavelength n (no dispersion)
  4 = nothing traceable            BLOCKED = identity undefined (needs_specific_formulation), never auto-loaded
Selection policy: exactly one tier-1 dataset -> selected; several -> selection null + flagged (NEVER guessed); none -> gap.
k-only pages are listed but not counted (no n to load). Attributes (grade / Mw / tacticity / cure ratio / supplier) are read only
from the RI.info page title + COMMENTS by regex; anything not found is recorded as "not stated by source" -- never inferred.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymer_material_list import CANDIDATES, DEFERRED, EXCLUDED_CANDIDATES, RESOLUTIONS  # noqa: E402

RI = _ROOT / "refractiveindex_db" / "database"
MATCHES_OUT = _ROOT / "data" / "polymer_ri_matches.json"
SELECTIONS_OUT = _ROOT / "data" / "step1_selections_polymers.json"
POLYMER_DIVIDERS = {("organic", "Polymers"), ("other", "Commercial polymers"), ("other", "Resists")}

ATTRS = dict(  # heuristic regexes over RI page title + COMMENTS
    grade=r"HDPE|LLDPE|LDPE|Kapton[- ]?\w*|type H|\bHN\b|PDLA|E48R|PH102|RTV ?\d+|Sylgard ?\d+|SU-8 \d+|\bTPX\b|Pyralin[\w -]*",
    molecular_weight=r"molecular weight[^;.]*|\bM[wW]\b[^;.]*|g/mol",
    tacticity=r"[a-z]*tactic\w*",
    cure_ratio=r"\d+\s*:\s*\d+[^;.]*|uncured|UV curable|cured|curing agent",
    supplier=r"Manufacturer[^.;]*|[Mm]anufactured by[^.;]*|DuPont|Dow(?: Corning)?|Bayer|Momentive|Micro[Cc]hem|Imperial Chemical\w*|Sigma",
)
SIGNALS = dict(  # flags that hint two datasets may be different materials, not one material with several papers
    cure_ratio=r"\d+\s*:\s*\d+|ratio|uncured|UV curable|curing", resist_grade=r"resist|Micro[Cc]hem|spec sheet",
    molecular_weight=r"molecular weight", product=r"RTV|Sylgard|Kapton|HN\b|Pyralin|Avicel|TPX|SF-96",
    physical_form=r"powder|microsphere|film|fluid|monomer|microcrystalline|substrate|sheet", linear_or_branched=r"LLDPE|HDPE|LDPE",
)


def strip(s):
    return re.sub(r"<[^>]+>", "", str(s or ""))


def formula_of(book_name):
    """Formula token in an RI book title like '(C2H4)n (Polyethylene, PE)'; None for grade names like 'Zeonex E48R'."""
    m = re.match(r"^\s*(\S+)\s+\(", strip(book_name))
    return m.group(1) if m and re.search(r"\)n|[A-Z][a-z]?\d", m.group(1)) else None


def tag_of(page, page_name):
    m = re.match(r"^([^:]*?)(?: et al\.| and \w+)? (\d{4})", strip(page_name))
    if m:
        who = unicodedata.normalize("NFKD", m.group(1)).encode("ascii", "ignore").decode().replace(" ", "")
        return f"{who}{m.group(2)}"
    return re.sub(r"\W+", "", page)


def scan_page(data_path):
    d = yaml.safe_load(open(RI / "data" / data_path))
    n = k = form = tab = False
    lams, spans = set(), []
    for b in d.get("DATA", []):
        t = b.get("type", "")
        n |= t in ("tabulated nk", "tabulated n") or t.startswith("formula")
        k |= t in ("tabulated nk", "tabulated k")
        form |= t.startswith("formula")
        if t.startswith("tabulated"):
            tab = True
            lam = [float(x.split()[0]) for x in b["data"].strip().splitlines() if x.strip()]
            lams.update(lam)
            spans.append((min(lam), max(lam)))
        elif "wavelength_range" in b:
            v = [float(x) for x in str(b["wavelength_range"]).split()]
            spans.append((min(v), max(v)))
    return dict(kind="nk" if n and k else "n" if n else "k-only",
                dispersion="formula+tabulated" if form and tab else "formula" if form else "tabulated",
                span_um=[min(s[0] for s in spans), max(s[1] for s in spans)] if spans else None,
                single_point=bool(tab and not form and len(lams) == 1), comments=strip(d.get("COMMENTS")))


def find(rx, text):
    m = re.search(rx, text)
    return m.group(0).strip() if m else None


def flatten(cat):
    books, aliases = {}, {}
    for e in cat:
        shelf, div = e.get("SHELF"), None
        for b in e.get("content", []):
            if "DIVIDER" in b:
                div = b["DIVIDER"]
            elif "BOOK" in b:
                books[(shelf, b["BOOK"])] = dict(name=strip(b.get("name")), divider=div,
                                                 pages=[p for p in b.get("content", []) if "PAGE" in p and p.get("data")])
                if shelf == "3d" and b["BOOK"] == "plastics":  # alias pages point at data files owned by other shelves
                    for p in books[(shelf, b["BOOK"])]["pages"]:
                        aliases[p["data"]] = f"3d/plastics/{p['PAGE']}"
    return books, aliases


def dataset(shelf, book, p, aliases):
    s = scan_page(p["data"])
    title = strip(p.get("name"))
    text = f"{p['PAGE']} {title} {s['comments']}"
    return dict(shelf=shelf, book=book, page=p["PAGE"], page_name=title, data_path=p["data"],
                tag=book if p["PAGE"] == "specs" else tag_of(p["PAGE"], title),  # spec sheets: book id keeps tags unique
                also_listed_in=aliases.get(p["data"]), attributes_stated={a: find(rx, text) for a, rx in ATTRS.items()},
                signals=[s_ for s_, rx in SIGNALS.items() if re.search(rx, text, re.I)], **s)


def main():
    cat = yaml.safe_load(open(RI / "catalog-nk.yml"))
    books, aliases = flatten(cat)
    used, out = set(), []
    for c in CANDIDATES:
        ds = []
        for key in c["ri_books"]:
            for p in books[key]["pages"]:
                text = f"{p['PAGE']} {strip(p.get('name'))}"
                if c["include_re"] or c["exclude_re"]:
                    text += " " + scan_page(p["data"])["comments"]
                if c["include_re"] and not re.search(c["include_re"], text):
                    continue
                if c["exclude_re"] and re.search(c["exclude_re"], text):
                    continue
                ds.append(dataset(*key, p, aliases))
        used |= {d["data_path"] for d in ds}
        disp = [d for d in ds if d["kind"] != "k-only" and not d["single_point"]]
        single = [d for d in ds if d["kind"] != "k-only" and d["single_point"]]
        if c["blocked"]:
            tier, status = "BLOCKED", "BLOCKED"
        elif disp:
            tier, status = 1, "FOUND" if len(disp) == 1 else "MULTIPLE"
        elif single:
            tier, status = 3, "SINGLE_POINT"
        else:
            tier, status = (2 if c["citations"] else 4), "MISSING"
        formula = next((formula_of(books[k]["name"]) for k in c["ri_books"] if formula_of(books[k]["name"])), None)
        out.append(dict(c, ri_books=[list(b) for b in c["ri_books"]], tier=tier, status=status, formula_ri=formula,
                        n_dispersion_datasets=len(disp), datasets=ds, single_point_datasets=[d["page"] for d in single],
                        k_only_datasets=[d["page"] for d in ds if d["kind"] == "k-only"]))

    extras = []  # polymer-section pages on RI.info that no candidate claimed: reported, never added
    for (shelf, book), b in books.items():
        if (shelf, b["divider"]) in POLYMER_DIVIDERS:
            for p in b["pages"]:
                if p["data"] not in used:
                    extras.append(dict(shelf=shelf, book=book, page=p["PAGE"], page_name=strip(p.get("name")), data_path=p["data"]))

    selections = {}
    for r in out:
        if r["tier"] != 1:
            continue
        key = r["key"]
        # datasets of this candidate that are deliberately not loaded (candidate-level list); each must exist on RI.info
        r["excluded_datasets"] = []
        for shelf, book, page, why in r["excluded_pages"]:
            if not any(p["PAGE"] == page for p in books[(shelf, book)]["pages"]):
                raise SystemExit(f"{key}: excluded page {shelf}/{book}/{page} not in the RI catalog")
            r["excluded_datasets"].append(dict(page=f"{book}/{page}", reason=why, gap_key=f"{key}:{book}/{page}"))
        if key in EXCLUDED_CANDIDATES:  # usable dataset exists but the candidate is deliberately not loaded: no material row
            r["status"], r["excluded_reason"] = "EXCLUDED", EXCLUDED_CANDIDATES[key]
            continue
        if key in DEFERRED:  # deferred entirely: no dataset picked, no material row
            r["status"] = "DEFERRED"
            r["deferred_reason"] = DEFERRED[key]
            selections[key] = dict(selection=None, deferred=True, reason=DEFERRED[key])
            continue
        res = RESOLUTIONS.get(key)
        if res:
            chosen = []
            for shelf, book, page in res["pages"]:
                d = next(d for d in r["datasets"] if (d["shelf"], d["book"], d["page"]) == (shelf, book, page))
                chosen.append(d)
            r["status"] = "SELECTED_BY_USER"
            r["excluded_datasets"] += [dict(page=pg, reason=why, gap_key=f"{key}:{pg}") for pg, why in res["excluded"]]
            if res.get("name"):
                r["name"] = res["name"]
            src = "user decision (this run): " + res["basis"]
        elif r["status"] == "FOUND":
            chosen, src = [r["datasets"][0]], "auto: the only dispersion-capable RI.info dataset"
        else:
            raise SystemExit(f"{key}: unresolved multi-match reached selection (must be RESOLUTIONS or DEFERRED)")
        axis_names = list(res["axes"]) if res and res.get("axes") else [None] * len(chosen)
        labels = list(res["labels"]) if res and res.get("labels") else None  # pages of one paper sharing a tag need distinct labels
        if labels and len(labels) != len(chosen):
            raise SystemExit(f"{key}: {len(labels)} labels for {len(chosen)} pages")
        selections[key] = dict(
            name=r["name"], polymorph=None, effective_polymorph=None, source=src,
            not_stated_by_source=[f"{a}: not stated by source" for a in ATTRS if all(d["attributes_stated"][a] is None for d in chosen)],
            axes=[dict(page=d["page"], axis=axis_names[i], data_path=d["data_path"],
                       dataset_label=labels[i] if labels else d["tag"] if axis_names[i] is None else f"{d['tag']} | {axis_names[i]}",
                       span_um=d["span_um"], kind=d["kind"], attributes_stated={a: v for a, v in d["attributes_stated"].items() if v})
                  for i, d in enumerate(chosen)])
    MATCHES_OUT.write_text(json.dumps(dict(candidates=out, extras_found_not_in_pool=extras), indent=1, default=str))
    SELECTIONS_OUT.write_text(json.dumps(selections, indent=1))

    tiers = {}
    for r in out:
        tiers.setdefault(str(r["tier"]), []).append(r["key"])
    print(f"candidates={len(out)}  extras(not in pool)={len(extras)}")
    for t in ("1", "2", "3", "4", "BLOCKED"):
        print(f"  tier {t:7}: {len(tiers.get(t, [])):2}  " + (", ".join(tiers.get(t, [])) if t != "4" else ""))
    print("  FOUND (selected):", [r["key"] for r in out if r["status"] == "FOUND"])
    print("  SELECTED_BY_USER:", [r["key"] for r in out if r["status"] == "SELECTED_BY_USER"])
    print("  DEFERRED:", [r["key"] for r in out if r["status"] == "DEFERRED"])
    print("  EXCLUDED candidates:", [r["key"] for r in out if r["status"] == "EXCLUDED"])
    print("  unresolved MULTIPLE:", [r["key"] for r in out if r["status"] == "MULTIPLE"])


if __name__ == "__main__":
    main()
