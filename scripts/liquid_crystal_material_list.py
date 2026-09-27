#!/usr/bin/env python3
"""
scripts/liquid_crystal_material_list.py
=======================================
The liquid-crystal family (refractiveindex.info `other` shelf, "Liquid crystals"): two single compounds (5CB, 5PCH; identity from
PubChem) and seven commercial mixtures (formula NULL). Every page is listed with its optical axis (ordinary / extraordinary ray);
the Wu 1993 temperature series keep their temperature in the label (Wu1993-25.1C) and on every row. All listed temperatures are
below each compound's nematic-isotropic transition (5CB ~35 degC, 5PCH ~54 degC); the pages do not name the phase, so no phase
label is added. Built by scripts/build_liquid_crystals_csv.py with the shared listed-pages builder.
"""
SHELF = "other"


def _p(book, page, axis, suffix=None):
    return dict(shelf=SHELF, book=book, page=page, axis=axis, tag_suffix=suffix)


def _oe(book, stem, suffix=None, skip=()):
    return [_p(book, f"{stem}-{ax}", ax, suffix) for ax in ("o", "e") if ax not in skip]


def _lc(key, name, pages, formula=None, pubchem_name=None, note=None):
    return dict(key=key, name=name, pages=pages, formula=formula, pubchem_name=pubchem_name, note=note, density_page=None,
                materialclass="liquid crystal" if formula else "liquid crystal mixture",
                prefer_stated_temperature=True)  # user decision: n of a liquid crystal depends strongly on temperature


_WU_5CB = [("25.1C", ()), ("27.2C", ("e",)), ("29.9C", ()), ("32.6C", ()), ("34.8C", ())]
_WU_5PCH = [("25.0C", "Wu-25.0C"), ("30.4C", None), ("34.8C", "Wu-34.8C"), ("40.1C", "Wu-40.1C"), ("45.4C", "Wu-45.4C"),
            ("50.8C", "Wu-50.8C"), ("53.4C", "Wu-53.4C")]

MATERIALS = [
    _lc("5CB", "5CB (4-pentyl-4'-cyanobiphenyl)",
        _oe("5CB", "Li") + _oe("5CB", "Tkachenko") + [p for t, skip in _WU_5CB for p in _oe("5CB", f"Wu-{t}", t, skip)],
        formula="C18H19N", pubchem_name="4-Cyano-4'-pentylbiphenyl", note="nematic below ~35 degC"),
    _lc("5PCH", "5PCH (4-trans-pentylcyclohexylcyanobenzene)",
        _oe("5PCH", "Li") + [p for t, stem in _WU_5PCH if stem for p in _oe("5PCH", stem, t)]
        + [_p("5PCH", "Wu-30.4-o", "o", "30.4C"), _p("5PCH", "Wu-30.4C-e", "e", "30.4C")],  # the source names the 30.4 degC o-ray page without "C"
        formula="C18H25N", pubchem_name="4-(trans-4-Pentylcyclohexyl)benzonitrile", note="nematic below ~54 degC"),
    _lc("E7", "E7 liquid crystal mixture", _oe("E7", "Li") + _oe("E7", "Tkachenko")),
    _lc("E44", "E44 liquid crystal mixture", _oe("E44", "Li")),
    _lc("MLC-6241-000", "MLC-6241-000 liquid crystal mixture", _oe("MLC-6241-000", "Li")),
    _lc("MLC-6608", "MLC-6608 liquid crystal mixture", _oe("MLC-6608", "Li")),
    _lc("MLC-9200-000", "MLC-9200-000 liquid crystal mixture", _oe("MLC-9200-000", "Li")),
    _lc("MLC-9200-100", "MLC-9200-100 liquid crystal mixture", _oe("MLC-9200-100", "Li")),
    _lc("TL-216", "TL-216 liquid crystal mixture", _oe("TL-216", "Li")),
]

EXCLUDED_PAGES = {
    (SHELF, "5CB", "Wu-27.2C-e"): ("duplicate of the 29.9 degC e-ray page: identical coefficients, and its own comment says 29.9 degC "
                                   "(the page title and CONDITIONS say 27.2 degC). The 27.2 degC o-ray page has its own data and is loaded"),
}
OUT_OF_FAMILY = {}
