#!/usr/bin/env python3
"""
scripts/release_curation.py
===========================
Release build stage 3a: citation clean-up and material synonyms. Reads only committed inputs (offline, reproducible).

curate_sources   1. rows of `sources` identical in every column are merged into the oldest (references repointed, nothing lost);
                 2. refractiveindex.info citations without a DOI get the DOI cached in data/descriptors/source_dois.json
                    (scripts/fetch_source_dois.py: Crossref, accepted only on year + first author + title match); when that DOI
                    already belongs to another row of the same technique, the two rows are one paper and are merged.
populate_synonyms  material_synonyms from sources that name the material itself:
                 * the alternate name in the material's own name, "Zinc germanium phosphide (ZGP)" -> ZGP and the base name,
                   only for brackets reviewed as synonyms (NAME_SYNONYMS); brackets that are a phase, grade, supplier, species or
                   form (NAME_QUALIFIERS) are not synonyms; an unreviewed bracket stops the build;
                 * the names in the title of the refractiveindex.info book holding the material's data, when that book holds
                   no other material of the release ("C (Carbon, diamond, graphite, ...)" names several and is skipped);
                 * the polymer family's abbreviation column;
                 * PubChem's record title for the material's CID (data/descriptors/pubchem_titles.json), without a trailing
                   bracket that only repeats the formula and without PubChem's " atom" suffix of elements;
                 * British / American spellings of the name (aluminium / aluminum, caesium / cesium, sulphide / sulfide, ...).
                 A synonym equal to the material's name or formula is dropped; a synonym that would name MORE THAN ONE material is
                 dropped for all of them (ambiguous, e.g. "BGO") and recorded in the manifest.
"""
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_source_dois import citation_key  # noqa: E402

DOI_CACHE = _ROOT / "data" / "descriptors" / "source_dois.json"
PUBCHEM_TITLES = _ROOT / "data" / "descriptors" / "pubchem_titles.json"
RI_CATALOG = _ROOT / "refractiveindex_db" / "database" / "catalog-nk.yml"
REF_TABLES = ["optical_dispersion", "physical_properties", "mechanical_properties", "rheology"]

NAME_SYNONYMS = {
    "isopropanol", "BBO", "BGGSe", "BGSe", "BGS", "BGO", "BSO", "BiBO", "hexanoic acid", "octanoic acid", "heptanoic acid",
    "nonanoic acid", "CLBO", "calcium magnesium carbonate", "D2O", "HDPE", "LLDPE", "3-methyl-1-butanol", "2-methyl-1-propanol",
    "2,2,4-trimethylpentane", "2-methylbutane", "galena", "cinnabar", "proustite", "LiCAF", "LGS", "LBO", "SCAM", "PDLA", "PNIPAM",
    "PCTFE", "PEI", "TPX", "AGSe", "AGS", "TAS", "YLF", "ZGP", "berlinite", "anhydrite", "KDP", "ADP", "KTP", "RTP",
}
NAME_QUALIFIERS = {
    "hexagonal", "liquid", "rutile / anatase", "sodium salt, calf thymus", "polyimide film", "negative photoresist", "negative resist",
    "copolymer resist", "epoxy photoresist", "cured", "Mitsubishi", "Tomson", "DuPont ionomer resin", "cyclo olefin polymer",
    "Dow Corning, 5:1 mass ratio", "Dow Corning, 10:1 mass ratio", "Dow Corning, 15:1 mass ratio", "Dow Corning, 20:1 mass ratio",
    "Antheraea assamensis", "Antheraea mylitta", "Bombyx mori", "Samia ricini",
}
SPELLINGS = [("aluminium", "aluminum"), ("caesium", "cesium"), ("sulphide", "sulfide"), ("sulphate", "sulfate"), ("sulphur", "sulfur")]


class CurationError(RuntimeError):
    pass


# ---------------------------------------------------------------- sources

def _merge(conn, keep, drop):
    for t in REF_TABLES:
        conn.execute(f"UPDATE {t} SET source_id = ? WHERE source_id = ?", (keep, drop))
    conn.execute("DELETE FROM sources WHERE source_id = ?", (drop,))


def curate_sources(conn, cache_path=DOI_CACHE):
    cols = "doi, title, authors, journal, year, technique, url, uncertainty, notes"
    groups = defaultdict(list)
    for sid, *rest in conn.execute(f"SELECT source_id, {cols} FROM sources ORDER BY source_id"):
        groups[tuple(rest)].append(sid)
    merged_identical = 0
    for ids in groups.values():
        for drop in ids[1:]:
            _merge(conn, ids[0], drop)
            merged_identical += 1
    accepted = json.loads(Path(cache_path).read_text())["accepted"] if Path(cache_path).exists() else {}
    dois_added, merged_same_doi = [], []
    for sid, title, authors, year, technique in conn.execute(
            "SELECT source_id, title, authors, year, technique FROM sources WHERE (doi IS NULL OR doi = '') "
            "AND technique = 'refractiveindex.info' ORDER BY source_id").fetchall():
        hit = accepted.get(citation_key(title, authors, year))
        if not hit:
            continue
        owner = conn.execute("SELECT source_id, technique FROM sources WHERE doi = ?", (hit["doi"],)).fetchone()
        if owner and owner[1] == technique:
            _merge(conn, owner[0], sid)
            merged_same_doi.append(dict(doi=hit["doi"], kept=owner[0], merged=sid))
        elif owner:
            raise CurationError(f"DOI {hit['doi']} already belongs to a {owner[1]!r} source; not merging across techniques")
        else:
            conn.execute("UPDATE sources SET doi = ? WHERE source_id = ?", (hit["doi"], sid))
            dois_added.append(dict(source_id=sid, doi=hit["doi"]))
    return dict(merged_identical_rows=merged_identical, dois_added=dois_added, merged_same_doi=merged_same_doi)


# ---------------------------------------------------------------- synonyms

def split_trailing(name):
    """'Lead(II) sulfide (galena)' -> ('Lead(II) sulfide', 'galena'); no trailing ' (...)' -> (name, None)."""
    if not name.endswith(")"):
        return name, None
    depth = 0
    for i in range(len(name) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(name[i], 0)
        if depth == 0:
            return (name[:i - 1], name[i + 1:-1]) if i > 0 and name[i - 1] == " " else (name, None)
    return name, None


def spelling_variants(text):
    out = set()
    for a, b in SPELLINGS:
        for x, y in ((a, b), (b, a)):
            if re.search(x, text, re.I):
                out.add(re.sub(x, lambda m: y.capitalize() if m.group(0)[0].isupper() else y, text, flags=re.I))
    return out


def _composition(f):
    counts = defaultdict(int)
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", f or ""):
        counts[el] += int(n or 1)
    return dict(counts)


def pubchem_name(title, formula):
    """PubChem's title as a name: 'Tin atom' -> 'Tin'; a trailing bracket that is only the formula, in any case or element
    order, is dropped ('Aluminum arsenide (alas)', 'Aluminum magnesium oxide (Al2MgO4)' for MgAl2O4)."""
    title = re.sub(r" atom$", "", title)
    base, bracket = split_trailing(title)
    if bracket and formula and (bracket.casefold() == formula.casefold() or _composition(bracket) == _composition(formula) != {}):
        return base
    return title


def book_names(catalog=RI_CATALOG):
    """(shelf, book) -> names listed in the book title, 'AgGaS2 (Silver gallium sulfide, AGS)' -> [Silver gallium sulfide, AGS]."""
    out = {}
    for e in yaml.safe_load(open(catalog)):
        for b in e.get("content", []):
            if "BOOK" in b:
                title = re.sub(r"<[^>]+>", "", str(b.get("name") or ""))
                m = re.search(r"\((.*)\)\s*$", title)
                out[(e["SHELF"], b["BOOK"])] = [s.strip() for s in m.group(1).split(", ") if s.strip()] if m else []
    return out


def populate_synonyms(conn, family_rows, titles_path=PUBCHEM_TITLES, catalog=RI_CATALOG):
    """family_rows: material name -> (family stem, csv row dict), as build_release.family_rows() gives it."""
    conn.execute("DELETE FROM material_synonyms")
    mats = conn.execute("SELECT material_id, name, formula, pubchem_cid FROM materials").fetchall()
    titles = json.loads(Path(titles_path).read_text())["titles"] if Path(titles_path).exists() else {}
    books_of = defaultdict(set)
    for mid, table in conn.execute("SELECT DISTINCT material_id, raw_record_table FROM optical_dispersion"):
        books_of[mid].add(tuple(table.split("/")[:2]))
    materials_in_book = defaultdict(set)
    for mid, bks in books_of.items():
        for bk in bks:
            materials_in_book[bk].add(mid)
    bnames = book_names(catalog)

    cand = defaultdict(dict)  # mid -> casefolded synonym -> (synonym, origin)
    def add(mid, syn, origin):
        syn = " ".join(str(syn).split())
        if syn:
            cand[mid].setdefault(syn.casefold(), (syn, origin))

    # names a material OWNS: its name, a reviewed bracket synonym, the base name then, and the parts of "A / B". Another source
    # (a book title such as "H2O, D2O (Water, heavy water, ice)") cannot give an owned name to a different material.
    owned, unreviewed = {}, []
    for mid, name, formula, cid in mats:
        base, bracket = split_trailing(name)
        own = [name]
        if bracket is not None and bracket not in NAME_SYNONYMS | NAME_QUALIFIERS:
            unreviewed.append(name)
        if bracket is None or bracket in NAME_SYNONYMS:
            own += [bracket, base] if bracket else []
            own += [part for part in base.split(" / ")] if " / " in base else []
        for o in own:
            if o:
                owned.setdefault(o.casefold(), mid)
    if unreviewed:
        raise CurationError(f"material names with an unreviewed bracket (add to NAME_SYNONYMS or NAME_QUALIFIERS): {unreviewed}")

    def add(mid, syn, origin):  # noqa: F811  (the owned-name guard applies to every source)
        syn = " ".join(str(syn).split())
        if syn and owned.get(syn.casefold(), mid) == mid:
            cand[mid].setdefault(syn.casefold(), (syn, origin))

    for mid, name, formula, cid in mats:
        base, bracket = split_trailing(name)
        if bracket in NAME_SYNONYMS:
            add(mid, bracket, "name")
        if bracket is None or bracket in NAME_SYNONYMS:
            add(mid, base, "name")
            for part in base.split(" / ") if " / " in base else []:
                add(mid, part, "name")
        else:
            add(mid, base, "name without its qualifier")
        for bk in books_of[mid]:
            if materials_in_book[bk] == {mid}:
                for s in bnames.get(bk, []):
                    add(mid, s, "refractiveindex.info book")
        row = (family_rows.get(name) or (None, {}))[1] or {}
        abbr = row.get("abbreviation")
        if isinstance(abbr, str) and abbr.strip():
            add(mid, abbr.strip(), "family abbreviation")
        if cid is not None and str(int(cid)) in titles:
            add(mid, pubchem_name(titles[str(int(cid))], formula), "PubChem title")
        for part in (base.split(" / ") if " / " in base else [base]):
            for v in spelling_variants(part):
                add(mid, v, "spelling variant")

    names = {mid: (name, formula) for mid, name, formula, _ in mats}
    owners = defaultdict(set)
    for mid, syns in cand.items():
        for key in syns:
            owners[key].add(mid)
    ambiguous = sorted({cand[next(iter(m))][k][0] for k, m in owners.items() if len(m) > 1})
    counts = defaultdict(int)
    for mid, syns in cand.items():
        name, formula = names[mid]
        for key, (syn, origin) in syns.items():
            if key in (name.casefold(), (formula or "").casefold()) or len(owners[key]) > 1:
                continue
            conn.execute("INSERT INTO material_synonyms(material_id, synonym) VALUES (?, ?)", (mid, syn))
            counts[origin] += 1
    return dict(synonyms=sum(counts.values()), by_origin=dict(counts), ambiguous_dropped=ambiguous,
                materials_with_synonyms=conn.execute("SELECT COUNT(DISTINCT material_id) FROM material_synonyms").fetchone()[0])
