#!/usr/bin/env python3
"""
scripts/halide_material_list.py
================================
Candidate list for the halide family: the simple chlorides, bromides and iodides in RI.info's `main` shelf. A CHECKLIST:
scripts/match_ri_info_halides.py scans the catalog and is authoritative (a missing book is a gap, never padded). Formulas are the
ones RI.info prints in the book title. Fluorides are not part of this run (CdF2 is already loaded by an earlier family).
"""


MULTI_BASIS = "multi-paper: every RI.info paper is loaded as its own labelled dataset (standing rule 'whatever gives more info', as for SiC); none is dropped or merged; primary = measured before model fits, then widest span"


def _c(key, name, formula, book, note=None, materialclass="halide", page_polymorph=None, basis=None):
    return dict(key=key, name=name, formula=formula, book=book, shelf="main", note=note, materialclass=materialclass,
                page_polymorph=page_polymorph or {}, basis=basis)


CANDIDATES = [
    # chlorides
    _c("AgCl", "Silver chloride", "AgCl", "AgCl"),
    _c("CsCl", "Cesium chloride", "CsCl", "CsCl"),
    _c("CuCl", "Copper(I) chloride", "CuCl", "CuCl"),
    _c("KCl", "Potassium chloride", "KCl", "KCl", page_polymorph={"Li": None, "Querry": None}, basis=MULTI_BASIS),
    _c("LiCl", "Lithium chloride", "LiCl", "LiCl"),
    _c("NaCl", "Sodium chloride", "NaCl", "NaCl", page_polymorph={"Li": None, "Querry": None}, basis=MULTI_BASIS),
    _c("RbCl", "Rubidium chloride", "RbCl", "RbCl"),
    _c("TlCl", "Thallium(I) chloride", "TlCl", "TlCl"),
    # bromides
    _c("AgBr", "Silver bromide", "AgBr", "AgBr", page_polymorph={"Schröter": None, "Polyanskiy": None}, basis=MULTI_BASIS),
    _c("CsBr", "Cesium bromide", "CsBr", "CsBr", page_polymorph={"Li": None, "Querry": None, "Rodney": None}, basis=MULTI_BASIS),
    _c("KBr", "Potassium bromide", "KBr", "KBr"),
    _c("LiBr", "Lithium bromide", "LiBr", "LiBr"),
    _c("NaBr", "Sodium bromide", "NaBr", "NaBr"),
    _c("RbBr", "Rubidium bromide", "RbBr", "RbBr"),
    _c("TlBr", "Thallium(I) bromide", "TlBr", "TlBr", page_polymorph={"Palik": None, "Schroter": None}, basis=MULTI_BASIS),
    # iodides
    _c("CsI", "Cesium iodide", "CsI", "CsI", page_polymorph={"Li": None, "Querry": None, "Rodney": None}, basis=MULTI_BASIS),
    _c("KI", "Potassium iodide", "KI", "KI"),
    _c("LiI", "Lithium iodide", "LiI", "LiI"),
    _c("NaI", "Sodium iodide", "NaI", "NaI", page_polymorph={"Jellison": None, "Li": None}, basis=MULTI_BASIS),
    _c("PbI2", "Lead(II) iodide", "PbI2", "PbI2", note="layered, birefringent crystal"),
    _c("RbI", "Rubidium iodide", "RbI", "RbI"),
]

# Uncovered `main` halide-adjacent books deliberately NOT in this family, with the reason.
OUT_OF_FAMILY = {
    "LiIO3": "iodate, not a halide; already loaded as Lithium_iodate by the oxide family",
    "MoOCl2": "oxychloride, layered 2D-type crystal (thin-flake sheet effects): belongs with the graphene/2D follow-up",
}

# Ambient-condition crystal structure of each solid (standard crystallography: rock-salt B1, CsCl-type B2, zincblende B3, CdI2-type).
# Used ONLY to choose which Materials Project entry supplies the (calculated) density: the MP entry with THIS space group. The lowest-energy
# MP entry is often a different phase (DFT puts wurtzite LiCl/LiBr/LiI, rock-salt CsI, orthorhombic TlCl/TlBr lowest), which would give a
# wrong density for the material RI.info measured. (structure name, space-group number, symbol)
AMBIENT_STRUCTURE = {
    **{k: ("rock-salt", 225, "Fm-3m") for k in ("AgCl", "KCl", "LiCl", "NaCl", "RbCl", "AgBr", "KBr", "LiBr", "NaBr", "RbBr",
                                                 "KI", "LiI", "NaI", "RbI")},
    **{k: ("CsCl-type", 221, "Pm-3m") for k in ("CsCl", "CsBr", "CsI", "TlCl", "TlBr")},
    "CuCl": ("zincblende", 216, "F-43m"),
    "PbI2": ("CdI2-type 2H", 164, "P-3m1"),
}
