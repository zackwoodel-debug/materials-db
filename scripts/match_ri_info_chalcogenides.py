#!/usr/bin/env python3
"""
scripts/match_ri_info_chalcogenides.py
====================================
Matches scripts/chalcogenide_material_list.CANDIDATES against the local RI.info catalog (authoritative) and writes
data/chalcogenide_ri_matches.json + data/step1_selections_chalcogenides.json.

Selection policy (never auto-pick among alternatives):
  * pages are grouped into PAPERS by their title before the ';' (o/e/alpha/beta/gamma axis pages of one paper share it);
  * exactly one paper -> selected, all of its pages loaded as axes (labels from the page suffix); this is structure, not a choice;
  * more than one paper -> selection null, flagged for the user;  no book -> gap.
Only dispersion-capable datasets count (tabulated n[,k] over >1 wavelength, or an n formula); k-only pages are listed, not counted.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chalcogenide_material_list import CANDIDATES, DEFERRED, EXCLUDED_PAGES, OUT_OF_FAMILY  # noqa: E402

RI = _ROOT / "refractiveindex_db" / "database"
MATCHES_OUT = _ROOT / "data" / "chalcogenide_ri_matches.json"
SELECTIONS_OUT = _ROOT / "data" / "step1_selections_chalcogenides.json"
AXIS_SUFFIX = re.compile(r"-(o|e|a|b|c|alpha|beta|gamma|\u03b1|\u03b2|\u03b3)$")
AXIS_LABEL = {"o": "o-ray", "e": "e-ray", "a": "a-axis", "b": "b-axis", "c": "c-axis", "alpha": "alpha-axis", "beta": "beta-axis",
              "gamma": "gamma-axis", "\u03b1": "alpha-axis", "\u03b2": "beta-axis", "\u03b3": "gamma-axis"}
# an axis descriptor inside a page title, e.g. "n(o) 0.45-4.0 um", "n,k(e) ...", "n(\u03b1)": stripped so pages of ONE paper share a key
AXIS_IN_TITLE = re.compile(r"[:;,]?\s*n,?k?\s*\(\s*(?:o|e|a|b|c|alpha|beta|gamma|\u03b1|\u03b2|\u03b3)\s*\).*$")


def tag_of(page, title):
    """Author+year tag for dataset labels, e.g. 'Wang et al. 2013: 6H-SiC' -> 'Wang2013' (accents stripped)."""
    import unicodedata
    m = re.match(r"^([^:]*?)(?:,? et al\.?| and \w+)?,? (\d{4})", title)
    if m:
        return unicodedata.normalize("NFKD", m.group(1)).encode("ascii", "ignore").decode().replace(" ", "") + m.group(2)
    return re.sub(r"\W+", "", page)


def label_of(polymorph, tag, axis):
    return " | ".join(x for x in (polymorph, tag, axis) if x)


def paper_key(title):
    return AXIS_IN_TITLE.sub("", title.split(";")[0] if AXIS_IN_TITLE.search(title.split(";")[0]) is None else title).strip(" :;,")
PHASE_WORDS = re.compile(r"\b(3C|4H|6H|15R|alpha|beta|gamma|amorphous|crystalline|single.crystal|poly\w*|ceramic|thin film|film|bulk|nanopart\w*|powder|ordinary|extraordinary)\b|[a-z]-[A-Z]", re.I)


def strip(s):
    return re.sub(r"<[^>]+>", "", str(s or ""))


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
                conditions=strip(d.get("CONDITIONS")))


def _disambiguate(axes):
    """Pages of ONE paper can share (author-year, axis): CuGaS2 Boyd 20 C / 120 C, GaSe Chen n-only formula vs n,k table. Their dataset_label must
    stay distinct (loader key), so the page stem after the author is appended to the tag: Boyd1971-20, Boyd1971-120, Chen2009-n, Chen2009-nk."""
    groups = {}
    for a in axes:
        groups.setdefault((a["phase"], a["tag"], a["axis"]), []).append(a)
    for group in groups.values():
        if len(group) > 1:
            for a in group:
                stem = AXIS_SUFFIX.sub("", a["page"])
                if "-" not in stem:
                    raise SystemExit(f"cannot disambiguate colliding labels for page {a['page']!r}")
                suffix = stem.split("-", 1)[1]
                if suffix.isdigit() and "\u00b0C" in (a.get("comments") or ""):
                    suffix += "C"  # a temperature series (CuGaS2 Boyd 20 / 120 degC)
                a["tag"] = a["tag"] + "-" + suffix
                a["dataset_label"] = label_of(a["phase"], a["tag"], a["axis"])
    labels = [a["dataset_label"] for a in axes]
    assert len(labels) == len(set(labels)), f"dataset labels still collide: {labels}"
    return axes


def main():
    cat = yaml.safe_load(open(RI / "catalog-nk.yml"))
    books = {}
    for e in cat:
        for b in e.get("content", []):
            if "BOOK" in b:
                books[(e["SHELF"], b["BOOK"])] = dict(name=strip(b.get("name")), pages=[p for p in b.get("content", []) if "PAGE" in p and p.get("data")])
    have = {r[0] for r in sqlite3.connect(f"{(_ROOT / 'data/materials_oxide_test.db').as_uri()}?mode=ro", uri=True).execute("select formula from materials")}
    out, selections = [], {}
    for c in CANDIDATES:
        b = books.get((c["shelf"], c["book"]))
        ds = []
        for p in (b["pages"] if b else []):
            s = scan_page(p["data"])
            title = strip(p.get("name"))
            ds.append(dict(page=p["PAGE"], title=title, paper=paper_key(title), data_path=p["data"],
                           axis=AXIS_LABEL.get(m.group(1)) if (m := AXIS_SUFFIX.search(p["PAGE"])) else None,
                           phase_words=sorted({w.group(0) for w in PHASE_WORDS.finditer(title + " " + s["comments"])}), **s))
        excluded = [d["page"] for d in ds if (c["key"], d["page"]) in EXCLUDED_PAGES]
        disp = [d for d in ds if d["kind"] != "k-only" and not d["single_point"] and d["page"] not in excluded]
        papers = sorted({d["paper"] for d in disp})
        status = "MISSING" if not b else ("FOUND" if len(papers) == 1 else "MULTIPLE" if papers else "NO_DISPERSION")
        out.append(dict(c, status=status, n_pages=len(ds), n_papers=len(papers), papers=papers, datasets=ds,
                        k_only_pages=[d["page"] for d in ds if d["kind"] == "k-only"], excluded_pages=excluded, single_point_pages=[d["page"] for d in ds if d["single_point"]],
                        already_in_135_db=c["formula"] in have, ri_book_title=b["name"] if b else None))
        if c["page_polymorph"]:  # user-resolved multi-paper candidate: every listed page, labelled by its own phase
            missing = set(c["page_polymorph"]) - {d["page"] for d in disp}
            if missing:
                raise SystemExit(f"{c['key']}: pages not found on RI.info: {sorted(missing)}")
            chosen = sorted((d for d in disp if d["page"] in c["page_polymorph"]), key=lambda d: (not d["span_um"][0] <= 0.633 <= d["span_um"][1], d["span_um"][0] - d["span_um"][1]))  # primary: widest span among pages covering 633 nm, else widest
            out[-1]["status"] = "SELECTED_BY_USER"
            selections[c["key"]] = dict(name=c["name"], formula=c["formula"], source="standing rule (user: whatever gives more info): " + c["basis"],
                                        axes=[dict(page=d["page"], axis=d["axis"], phase=c["page_polymorph"][d["page"]], data_path=d["data_path"],
                                                   span_um=d["span_um"], kind=d["kind"], dispersion=d["dispersion"],
                                                   comments=d["comments"], tag=tag_of(d["page"], d["paper"]), dataset_label=label_of(c["page_polymorph"][d["page"]], tag_of(d["page"], d["paper"]), d["axis"])) for d in chosen])
        elif status == "FOUND":
            selections[c["key"]] = dict(name=c["name"], formula=c["formula"], source="auto: exactly one paper on RI.info (all its pages are axes of it)",
                                        axes=[dict(page=d["page"], axis=d["axis"], phase=None, data_path=d["data_path"], span_um=d["span_um"], kind=d["kind"],
                                                   dispersion=d["dispersion"], comments=d["comments"], tag=tag_of(d["page"], d["paper"]), dataset_label=label_of(None, tag_of(d["page"], d["paper"]), d["axis"]))
                                              for d in disp if d["paper"] == papers[0]])
        elif status != "MISSING":
            selections[c["key"]] = None  # multi-match / no dispersion: flagged for the user, never guessed
    for v in selections.values():
        if v:
            _disambiguate(v["axes"])
    MATCHES_OUT.write_text(json.dumps(dict(candidates=out, out_of_family=OUT_OF_FAMILY, deferred=DEFERRED, excluded_pages={f"{k}:{p}": why for (k, p), why in EXCLUDED_PAGES.items()}), indent=1, default=str))
    SELECTIONS_OUT.write_text(json.dumps(selections, indent=1))
    n = lambda s: [r["key"] for r in out if r["status"] == s]
    print(f"candidates={len(out)}  FOUND={len(n('FOUND'))}  SELECTED_BY_USER={n('SELECTED_BY_USER')}  MULTIPLE={len(n('MULTIPLE'))}  MISSING={len(n('MISSING'))}  NO_DISPERSION={len(n('NO_DISPERSION'))}")
    print("already in the 135 DB by formula:", [r["key"] for r in out if r["already_in_135_db"]] or "none")


if __name__ == "__main__":
    main()
