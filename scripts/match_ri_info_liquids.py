#!/usr/bin/env python3
"""
scripts/match_ri_info_liquids.py
=================================
Matches scripts/liquid_material_list.CANDIDATES against the local refractiveindex.info catalog (authoritative) and writes
data/liquid_ri_matches.json + data/step1_selections_liquids.json.

Rules:
  * a candidate owns every dispersion-capable page of its book, or exactly the `pages` it names (books holding several compounds);
    pages in EXCLUDED_PAGES are never loaded; k-only and single-point pages are listed, not loaded;
  * several papers -> all loaded as separate datasets (standing rule); primary = measured before model fits (dataset_kind.py), then the
    widest page covering 633 nm, else the widest;
  * phase labels only where the candidate maps a page to the phase that page states (water);
  * pages of one paper that share (phase, author-year, axis) get the page qualifier: Kerl1995-293K, Sani2016-formula, Querry1987-NIR;
  * every book in the scanned areas must be a candidate or in OUT_OF_FAMILY (nothing silently skipped);
  * the about.yml formula of each book must match the candidate's composition, or the mismatch is recorded.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_ROOT / "src"))
from dataset_kind import is_model_fit  # noqa: E402
from liquid_material_list import CANDIDATES, EXCLUDED_PAGES, OUT_OF_FAMILY  # noqa: E402

RI = _ROOT / "refractiveindex_db" / "database"
MATCHES_OUT = _ROOT / "data" / "liquid_ri_matches.json"
SELECTIONS_OUT = _ROOT / "data" / "step1_selections_liquids.json"
AXIS_SUFFIX = re.compile(r"-(o|e|a|b|c|alpha|beta|gamma|α|β|γ)$")
AXIS_LABEL = {"o": "o-ray", "e": "e-ray", "a": "a-axis", "b": "b-axis", "c": "c-axis", "alpha": "alpha-axis", "beta": "beta-axis",
              "gamma": "gamma-axis", "α": "alpha-axis", "β": "beta-axis", "γ": "gamma-axis"}
# the catalog areas this family scans; every book in them must be a candidate or out of family
SCANNED = {"organic": lambda div: div != "Polymers",
           "main": lambda div: div in ("H, D - Hydrogen, deuterium, and hydrides", "Hg - Mercury", "O - Oxygen, oxides and garnets", "S - Sulfides and sulfates",
                                       "Ar - Argon", "Kr - Krypton", "Xe - Xenon", "Na - Sodium"),
           "other": lambda div: div in ("Mixed organic/inorganic compounds", "Fuel", "Immersion oils", "Microscopy mounting media",
                                        "Heat transfer fluids", "Human body", "Silk", "Buffer solutions", "Liquid crystals"),
           "specs": lambda div: div == "Index matching liquids"}
MAIN_BOOKS_IN_SCOPE = {"H2O", "Hg", "CS2", "H2", "D2", "NH3", "MgH2", "TiH2", "Ar", "Kr", "Xe", "Na"}  # the rest of those main sections are solids


def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(s or ""))).strip()


def tag_of(page, title):
    m = re.match(r"^([^:]*?)(?:,? et al\.?| and [\w'\u2019-]+)?,? (\d{4})", title)  # "Sani and Dell'Oro 2016" -> Sani2016
    if m:
        author = unicodedata.normalize("NFKD", m.group(1)).encode("ascii", "ignore").decode()
        return re.sub(r"[^A-Za-z]", "", author) + m.group(2)  # letters only: 'El-Kashef' -> ElKashef (labels must read as AuthorYYYY)
    return re.sub(r"\W+", "", page)


def label_of(phase, tag, axis):
    return " | ".join(x for x in (phase, tag, axis) if x)


def temperature_c(text):
    """The FIRST temperature the page text states, in degC (None if none). First by position: a later '0-100 degC' is the
    validity range of a temperature-dependent formula, not the sample's temperature (H2O Bashkatov)."""
    t = strip(text)
    found = []
    for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s*[\u2013-]\s*(-?\d+(?:\.\d+)?)\s*\u00b0\s*C", t):
        found.append((m.start(), round((float(m.group(1)) + float(m.group(2))) / 2, 2)))
    for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s*\u00b0\s*C", t):
        if not any(s <= m.start() < s + 40 for s, _ in found):  # the end of a range is not a separate statement
            found.append((m.start(), float(m.group(1))))
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*K\b", t):
        found.append((m.start(), round(float(m.group(1)) - 273.15, 2)))
    return min(found)[1] if found else None


def page_temperature_c(data_path, comments):
    """The temperature the pipeline stores for the page: file name / CONDITIONS (as parse_file reads them), else the page text."""
    from materials_db.pipeline.fetch_optical_data import parse_file
    try:
        t = parse_file(RI / "data" / data_path)[4]
    except ValueError:  # k-only page: parse_file has no n to read, and the page is never loaded
        t = None
    return round(t, 2) if t is not None else temperature_c(comments)


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
                single_point=bool(tab and not form and len(lams) == 1), comments=strip(d.get("COMMENTS")),
                temperature_c=page_temperature_c(data_path, d.get("COMMENTS")), types=[b.get("type") for b in d.get("DATA", [])])


def about_formula(book_dir):
    """The formula string listed in the book's about.yml NAMES (the entry that looks like a formula), if any."""
    p = RI / "data" / book_dir / "about.yml"
    if not p.exists():
        return None
    for n in (yaml.safe_load(open(p)) or {}).get("NAMES") or []:
        s = strip(n).replace(" ", "")
        if re.fullmatch(r"\(?([A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+\)?n?", s) and any(ch.isdigit() for ch in s):
            return s
    return None


def _same_composition(a, b):
    from pymatgen.core import Composition
    try:
        return Composition(a.strip("()n") if a.endswith(")n") else a) == Composition(b)
    except Exception:
        return False


def _disambiguate(axes):
    groups = {}
    for a in axes:
        groups.setdefault((a["phase"], a["tag"], a["axis"]), []).append(a)
    for group in groups.values():
        if len(group) > 1:
            plain = [a for a in group if "-" not in AXIS_SUFFIX.sub("", a["page"])]
            if len(plain) > 1:  # two pages with no qualifier: nothing on the page tells them apart
                raise SystemExit(f"cannot disambiguate colliding labels for pages {[a['page'] for a in plain]}")
            for a in group:  # the unqualified page (e.g. 'Sani') keeps the plain tag; 'Sani-formula' -> Sani2016-formula
                stem = AXIS_SUFFIX.sub("", a["page"])
                if "-" in stem:
                    a["tag"] = a["tag"] + "-" + stem.split("-", 1)[1]
                    a["dataset_label"] = label_of(a["phase"], a["tag"], a["axis"])
    labels = [a["dataset_label"] for a in axes]
    assert len(labels) == len(set(labels)), f"dataset labels still collide: {labels}"
    return axes


def main():
    cat = yaml.safe_load(open(RI / "catalog-nk.yml"))
    books, in_scope = {}, set()
    for shelf in cat:
        s, div = shelf.get("SHELF"), None
        for item in shelf.get("content", []):
            if "DIVIDER" in item:
                div = strip(item["DIVIDER"])
                continue
            if "BOOK" not in item:
                continue
            books[(s, item["BOOK"])] = dict(name=strip(item.get("name")), pages=[p for p in item.get("content", []) if "PAGE" in p and p.get("data")])
            if s in SCANNED and SCANNED[s](div) and (s != "main" or item["BOOK"] in MAIN_BOOKS_IN_SCOPE):
                in_scope.add(f"{s}/{item['BOOK']}")
    claimed = {f"{c['shelf']}/{c['book']}" for c in CANDIDATES} | set(OUT_OF_FAMILY)
    unaccounted = sorted(in_scope - claimed)
    if unaccounted:
        raise SystemExit(f"books in the scanned areas that are neither candidates nor out of family: {unaccounted}")
    missing_out = sorted(set(OUT_OF_FAMILY) - {f"{s}/{b}" for s, b in books})
    if missing_out:
        raise SystemExit(f"OUT_OF_FAMILY names books that do not exist: {missing_out}")

    out, selections = [], {}
    for c in CANDIDATES:
        b = books.get((c["shelf"], c["book"]))
        if not b:
            out.append(dict(c, status="MISSING"))
            continue
        page_ids = [p["PAGE"] for p in b["pages"]]
        wanted = c["pages"] or page_ids
        unknown = set(wanted) - set(page_ids)
        if unknown:
            raise SystemExit(f"{c['key']}: pages not in book {c['book']}: {sorted(unknown)}")
        ds, excluded = [], []
        for p in b["pages"]:
            if p["PAGE"] not in wanted:
                continue
            if (c["shelf"], c["book"], p["PAGE"]) in EXCLUDED_PAGES:
                excluded.append(p["PAGE"])
                continue
            title = strip(p.get("name"))
            s = scan_page(p["data"])
            ds.append(dict(page=p["PAGE"], title=title, paper=title.split(":")[0].strip(), data_path=p["data"],
                           axis=AXIS_LABEL.get(m.group(1)) if (m := AXIS_SUFFIX.search(p["PAGE"])) else None,
                           phase=c["page_phase"].get(p["PAGE"]), **s))
        disp = [d for d in ds if d["kind"] != "k-only" and not d["single_point"]]
        papers = sorted({d["paper"] for d in disp})
        book_dir = "/".join(b["pages"][0]["data"].split("/")[:2]) if b["pages"] else None
        af = about_formula(book_dir) if book_dir else None
        about_ok = None if (af is None or c["formula"] is None) else _same_composition(af, c["formula"])
        status = "FOUND" if len(papers) == 1 else "MULTI_PAPER" if papers else "NO_DISPERSION"
        out.append(dict({k: v for k, v in c.items() if k != "page_phase"}, status=status, n_pages=len(ds), n_papers=len(papers), papers=papers,
                        datasets=ds, excluded_pages=excluded, k_only_pages=[d["page"] for d in ds if d["kind"] == "k-only"],
                        single_point_pages=[d["page"] for d in ds if d["single_point"]], ri_book_title=b["name"],
                        about_yml_formula=af, about_yml_formula_matches=about_ok))
        if not disp:
            continue
        chosen = sorted(disp, key=lambda d: (is_model_fit(d["data_path"]), not d["span_um"][0] <= 0.633 <= d["span_um"][1], d["span_um"][0] - d["span_um"][1]))
        axes = [dict(page=d["page"], axis=d["axis"], phase=d["phase"], data_path=d["data_path"], span_um=d["span_um"], kind=d["kind"],
                     dispersion=d["dispersion"], comments=d["comments"], temperature_c=d["temperature_c"], tag=tag_of(d["page"], d["title"]),
                     dataset_label=label_of(d["phase"], tag_of(d["page"], d["title"]), d["axis"])) for d in chosen]
        selections[c["key"]] = dict(name=c["name"], formula=c["formula"],
                                    source=("auto: one paper" if status == "FOUND" else
                                            "standing rule (user: whatever gives more info): every paper loaded as its own dataset; primary = widest span covering 633 nm"),
                                    axes=_disambiguate(axes))
    MATCHES_OUT.write_text(json.dumps(dict(candidates=out, excluded_pages={"/".join(k): v for k, v in EXCLUDED_PAGES.items()},
                                           out_of_family=OUT_OF_FAMILY), indent=1, default=str))
    SELECTIONS_OUT.write_text(json.dumps(selections, indent=1))
    n = lambda s: [r["key"] for r in out if r["status"] == s]
    print(f"candidates={len(out)}  FOUND={len(n('FOUND'))}  MULTI_PAPER={len(n('MULTI_PAPER'))}  NO_DISPERSION={n('NO_DISPERSION')}  MISSING={n('MISSING')}  "
          f"datasets={sum(len(v['axes']) for v in selections.values())}")
    print("about.yml formula mismatches:", [(r["key"], r["about_yml_formula"]) for r in out if r.get("about_yml_formula_matches") is False] or "none")


if __name__ == "__main__":
    main()
