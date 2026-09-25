"""scripts/release_curation.py on synthetic databases with known answers: source merging and DOIs, and the synonym rules
(owned names, single-material books, ambiguity, reviewed brackets). The release build's own output is checked in
tests/test_release_build.py."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_curation as rc  # noqa: E402
from fetch_source_dois import citation_key  # noqa: E402

SCHEMA = """
CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT UNIQUE, formula TEXT, pubchem_cid INTEGER);
CREATE TABLE sources (source_id INTEGER PRIMARY KEY, doi TEXT UNIQUE, title TEXT, authors TEXT, journal TEXT, year INTEGER,
                      technique TEXT, url TEXT, uncertainty REAL, notes TEXT);
CREATE TABLE optical_dispersion (material_id INT, raw_record_table TEXT, source_id INT REFERENCES sources(source_id));
CREATE TABLE physical_properties (material_id INT, source_id INT REFERENCES sources(source_id));
CREATE TABLE mechanical_properties (material_id INT, source_id INT);
CREATE TABLE rheology (material_id INT, source_id INT);
CREATE TABLE material_synonyms (synonym_id INTEGER PRIMARY KEY, material_id INT, synonym TEXT, UNIQUE(material_id, synonym));
"""


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    return c


# ---------------------------------------------------------------- helpers

def test_split_trailing():
    assert rc.split_trailing("Lead(II) sulfide (galena)") == ("Lead(II) sulfide", "galena")
    assert rc.split_trailing("Poly(D-lactic acid) (PDLA)") == ("Poly(D-lactic acid)", "PDLA")
    assert rc.split_trailing("Cerium(III) fluoride") == ("Cerium(III) fluoride", None)
    assert rc.split_trailing("2-(Diisopropylamino)ethanol") == ("2-(Diisopropylamino)ethanol", None)


def test_spelling_variants_and_pubchem_names():
    assert rc.spelling_variants("Aluminium arsenide") == {"Aluminum arsenide"}
    assert rc.spelling_variants("Cesium iodide") == {"Caesium iodide"}
    assert rc.spelling_variants("Zinc sulfide") == {"Zinc sulphide"}
    assert rc.pubchem_name("Tin atom", "Sn") == "Tin"
    assert rc.pubchem_name("Aluminum magnesium oxide (Al2MgO4)", "MgAl2O4") == "Aluminum magnesium oxide"
    assert rc.pubchem_name("Aluminum arsenide (alas)", "AlAs") == "Aluminum arsenide"
    assert rc.pubchem_name("Iron(II,III) oxide", "Fe3O4") == "Iron(II,III) oxide"


# ---------------------------------------------------------------- sources

def _cache(tmp_path, entries):
    p = tmp_path / "dois.json"
    p.write_text(json.dumps(dict(accepted={citation_key(t, a, y): dict(doi=d) for t, a, y, d in entries})))
    return p


def test_identical_sources_merge_and_references_follow(tmp_path):
    c = _db()
    c.executemany("INSERT INTO sources(source_id, title, authors, year, technique) VALUES (?,?,?,?,?)",
                  [(1, "T", "A. Author.", 1985, "refractiveindex.info"), (2, "T", "A. Author.", 1985, "refractiveindex.info"),
                   (3, "T", "A. Author.", 1985, "literature")])  # 3 differs (technique): not identical
    c.executemany("INSERT INTO optical_dispersion VALUES (1, 'p', ?)", [(1,), (2,), (3,)])
    c.execute("INSERT INTO physical_properties VALUES (1, 2)")
    r = rc.curate_sources(c, _cache(tmp_path, []))
    assert r["merged_identical_rows"] == 1
    assert [x for (x,) in c.execute("SELECT source_id FROM sources ORDER BY 1")] == [1, 3]
    assert [x for (x,) in c.execute("SELECT source_id FROM optical_dispersion ORDER BY 1")] == [1, 1, 3]
    assert c.execute("SELECT source_id FROM physical_properties").fetchone()[0] == 1


def test_doi_is_added_and_a_second_row_of_the_same_paper_is_merged(tmp_path):
    c = _db()
    c.executemany("INSERT INTO sources(source_id, title, authors, year, technique) VALUES (?,?,?,?,?)",
                  [(1, "Dispersion of X.", "A. B. Author.", 2009, "refractiveindex.info"),
                   (2, None, "A. B. Author. Dispersion of X, J. 1 (2009)", 2009, "refractiveindex.info")])
    c.executemany("INSERT INTO optical_dispersion VALUES (1, 'p', ?)", [(1,), (2,)])
    cache = _cache(tmp_path, [("Dispersion of X.", "A. B. Author.", 2009, "10.1/x"), (None, "A. B. Author. Dispersion of X, J. 1 (2009)", 2009, "10.1/x")])
    r = rc.curate_sources(c, cache)
    assert r["dois_added"] == [dict(source_id=1, doi="10.1/x")] and r["merged_same_doi"] == [dict(doi="10.1/x", kept=1, merged=2)]
    assert c.execute("SELECT source_id, doi FROM sources").fetchall() == [(1, "10.1/x")]
    assert {x for (x,) in c.execute("SELECT source_id FROM optical_dispersion")} == {1}


def test_a_doi_owned_by_another_technique_stops_instead_of_merging(tmp_path):
    c = _db()
    c.executemany("INSERT INTO sources(source_id, doi, title, authors, year, technique) VALUES (?,?,?,?,?,?)",
                  [(1, "10.1/x", "T", "A.", 2000, "literature"), (2, None, "T", "A.", 2000, "refractiveindex.info")])
    with pytest.raises(rc.CurationError):
        rc.curate_sources(c, _cache(tmp_path, [("T", "A.", 2000, "10.1/x")]))


# ---------------------------------------------------------------- synonyms

def _catalog(tmp_path, books):
    p = tmp_path / "catalog.yml"
    p.write_text(yaml.safe_dump([dict(SHELF="main", content=[dict(BOOK=b, name=n) for b, n in books.items()])]))
    return p


def _titles(tmp_path, titles):
    p = tmp_path / "titles.json"
    p.write_text(json.dumps(dict(titles=titles)))
    return p


def _mats(c, rows):
    c.executemany("INSERT INTO materials VALUES (?,?,?,?)", [(i, n, f, cid) for i, n, f, cid, _ in rows])
    c.executemany("INSERT INTO optical_dispersion VALUES (?, ?, 1)", [(i, b) for i, _, _, _, b in rows])


def test_synonym_rules(tmp_path):
    c = _db()
    _mats(c, [(1, "Water", "H2O", None, "main/H2O/nk/Hale.yml"),
              (2, "Heavy water (D2O)", "D2O", 24602, "main/D2O/nk/Kedenburg.yml"),
              (3, "Lead(II) sulfide (galena)", "PbS", None, "main/PbS/nk/Zemel.yml"),
              (4, "Diamond", "C", 5462310, "main/C/nk/Phillip.yml"),
              (5, "Graphite", "C", 5462310, "main/C/nk/Djurisic-o.yml"),
              (6, "Aluminium oxide / sapphire", "Al2O3", None, "main/Al2O3/nk/Malitson-o.yml")])
    catalog = _catalog(tmp_path, {"H2O": "H2O, D2O (Water, heavy water, ice)", "D2O": "D2O (Heavy water)", "PbS": "PbS (Lead sulfide)",
                                  "C": "C (Carbon, diamond, graphite)", "Al2O3": "Al2O3 (Aluminium sesquioxide, Sapphire, Alumina)"})
    titles = _titles(tmp_path, {"24602": "Deuterium oxide", "5462310": "Carbon"})
    r = rc.populate_synonyms(c, {}, titles, catalog)
    syn = {}
    for mid, s in c.execute("SELECT material_id, synonym FROM material_synonyms"):
        syn.setdefault(mid, set()).add(s)
    assert syn[1] == {"ice"}                                        # "heavy water" is owned by material 2
    assert syn[2] == {"Heavy water", "Deuterium oxide"}             # D2O equals the formula: dropped
    assert syn[3] == {"galena", "Lead(II) sulfide", "Lead sulfide", "Lead(II) sulphide"}
    assert 4 not in syn and 5 not in syn                            # the C book holds both; "Carbon" would name both
    assert r["ambiguous_dropped"] == ["Carbon"]
    assert syn[6] >= {"Aluminium oxide", "sapphire", "Alumina", "Aluminium sesquioxide", "Aluminum oxide"}


def test_an_unreviewed_bracket_stops_the_build(tmp_path):
    c = _db()
    _mats(c, [(1, "Unobtainium (mystery)", "Uo", None, "main/Uo/nk/X.yml")])
    with pytest.raises(rc.CurationError, match="unreviewed bracket"):
        rc.populate_synonyms(c, {}, _titles(tmp_path, {}), _catalog(tmp_path, {}))


def test_qualifier_brackets_are_not_synonyms(tmp_path):
    c = _db()
    _mats(c, [(1, "Poly(methyl methacrylate) (Tomson)", None, None, "organic/x/nk/T.yml"),
              (2, "Poly(methyl methacrylate) (Mitsubishi)", None, None, "organic/x/nk/M.yml")])
    r = rc.populate_synonyms(c, {}, _titles(tmp_path, {}), _catalog(tmp_path, {}))
    assert c.execute("SELECT COUNT(*) FROM material_synonyms").fetchone()[0] == 0  # the shared base is ambiguous
    assert r["ambiguous_dropped"] == ["Poly(methyl methacrylate)"]
