#!/usr/bin/env python3
"""
scripts/inorganic3_material_list.py
====================================
Candidate list for the "inorganic batch 3" family: the solid, non-elemental compounds in RI.info's `main` shelf that no DB of ours holds
yet (carbides, a carbonate, a ferrite, sillenites, tantalates, titanates, tungstates, two oxides). A CHECKLIST: scripts/match_ri_info_inorganic3.py
scans the catalog and is authoritative (a missing book is a gap, never padded). Formulas are the ones RI.info prints in the book title.
"""


def _c(key, name, formula, book, note=None, materialclass="oxide", page_polymorph=None, basis=None):
    return dict(key=key, name=name, formula=formula, book=book, shelf="main", note=note, materialclass=materialclass,
                page_polymorph=page_polymorph or {}, basis=basis)


CANDIDATES = [
    _c("B4C", "Boron carbide", "B4C", "B4C", materialclass="carbide"),
    # SiC: ONE materials row (one PubChem InChIKey, UNIQUE); every polytype/phase is a separate, labelled dataset and is never merged.
    # Decision (user, defaults + "whatever gives more info"): all 10 RI.info pages are loaded, each under its own phase label.
    _c("SiC", "Silicon carbide", "SiC", "SiC", materialclass="carbide",
       note="polytypes/phases are distinct datasets under one material; the source states 4H, 6H, beta (zincblende), alpha (hexagonal, polytype not stated) and a thin film",
       basis="all 10 RI.info pages, each labelled by the phase its source states; 4H combines Wang 2013 (0.405-5 um) with Fischer 2017 (17-150 um), which do not overlap",
       page_polymorph={"Wang-4H-o": "4H", "Wang-4H-e": "4H", "Fischer-o": "4H", "Fischer-e": "4H", "Wang-6H-o": "6H", "Wang-6H-e": "6H",
                       "Shaffer": "3C (beta, zincblende)", "Singh-o": "alpha (hexagonal, polytype not stated)",
                       "Singh-e": "alpha (hexagonal, polytype not stated)", "Larruquert": "thin film"}),
    _c("TiC", "Titanium carbide", "TiC", "TiC", materialclass="carbide", note="source states composition TiC1.0"),
    _c("VC", "Vanadium carbide", "VC", "VC", materialclass="carbide", note="source states composition VC0.88 (sub-stoichiometric), not VC1.0"),
    _c("CaMgCO32", "Dolomite (calcium magnesium carbonate)", "CaMg(CO3)2", "CaMg_CO3_2", materialclass="carbonate", note="birefringent"),
    _c("BiFeO3", "Bismuth ferrite", "BiFeO3", "BiFeO3"),
    _c("Bi4Ge3O12", "Bismuth germanate (BGO)", "Bi4Ge3O12", "Bi4Ge3O12"),
    _c("Bi12SiO20", "Bismuth silicate (BSO)", "Bi12SiO20", "Bi12SiO20"),
    _c("ScAlMgO4", "Magnesium aluminate scandium oxide (SCAM)", "ScAlMgO4", "ScAlMgO4", note="birefringent"),
    _c("Yb2O3", "Ytterbium oxide", "Yb2O3", "Yb2O3"),
    _c("KTaO3", "Potassium tantalate", "KTaO3", "KTaO3"),
    _c("LiTaO3", "Lithium tantalate", "LiTaO3", "LiTaO3", note="birefringent"),
    _c("Bi4Ti3O12", "Bismuth titanate", "Bi4Ti3O12", "Bi4Ti3O12"),
    _c("PbTiO3", "Lead titanate", "PbTiO3", "PbTiO3"),
    _c("CaWO4", "Calcium tungstate", "CaWO4", "CaWO4"),
    _c("ZnWO4", "Zinc tungstate", "ZnWO4", "ZnWO4"),
]

# Uncovered `main` books deliberately NOT in this family, with the reason (each is a follow-up, not a gap of this run).
OUT_OF_FAMILY = {
    "Ti3C2": "Ti3C2 MXene is a 2D layered material: belongs with the graphene/2D follow-up (film thickness and sheet effects), not bulk-crystal loading",
    "O2": "gas", "CO": "gas", "CO2": "gas", "N2": "gas", "SF6": "gas", "Ar": "noble gas", "He": "noble gas", "Kr": "noble gas",
    "Ne": "noble gas", "Xe": "noble gas",
    "H2O": "liquid water / ice, 28 pages (temperature series); already in the benchmark DB from another source; a liquids family",
    "Hg": "liquid metal element",
}
