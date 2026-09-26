#!/usr/bin/env python3
"""
scripts/inorganic4_material_list.py
====================================
Candidate list for inorganic batch 4: the bulk phosphate and sulfate crystals left in RI.info's `main` shelf with linear n,k data
(nonlinear-optics crystals KDP, ADP, KTP, RTP; berlinite AlPO4; anhydrite CaSO4). A CHECKLIST: scripts/match_ri_info_inorganic4.py
scans the catalog and is authoritative. Several `main` books (CaO, SrO, Ga2O3, Er2O3, Gd3Ga5O12, YAlO3, KTiOAsO4, ...) hold only
nonlinear n2 data (catalog-n2.yml), not n,k, and are not candidates. Same scope rule and standing rules as the semiconductor family.
"""


def _c(key, name, formula, materialclass, note=None, book=None):
    return dict(key=key, name=name, formula=formula, book=book or key, shelf="main", note=note, materialclass=materialclass,
                page_polymorph={}, basis=None)


CANDIDATES = [
    _c("AlPO4", "Aluminium phosphate (berlinite)", "AlPO4", "phosphate", note="birefringent (trigonal, quartz-like)"),
    _c("CaSO4", "Calcium sulfate (anhydrite)", "CaSO4", "sulfate", note="biaxial; infrared only (2.5-55.6 um)"),
    _c("KH2PO4", "Potassium dihydrogen phosphate (KDP)", "KH2PO4", "phosphate", note="birefringent nonlinear-optical crystal"),
    _c("NH4H2PO4", "Ammonium dihydrogen phosphate (ADP)", "NH4H2PO4", "phosphate", note="birefringent nonlinear-optical crystal"),
    _c("KTiOPO4", "Potassium titanyl phosphate (KTP)", "KTiOPO4", "phosphate", note="biaxial nonlinear-optical crystal"),
    _c("RbTiOPO4", "Rubidium titanyl phosphate (RTP)", "RbTiOPO4", "phosphate", note="biaxial nonlinear-optical crystal"),
]

DEFERRED = {
    "ZrO2": ("no page is bulk ZrO2 as such: Wood 1982 is cubic zirconia stabilized with 12 mol% Y2O3 (a different composition, needs "
             "the composition convention pending with Aiden), Synowicki 2004 states 'Data generated from oscillator model' (a model "
             "fit, and the stabilizer is not stated), Bodurov 2016 is <100 nm nanoparticles dispersed in water (not bulk)."),
}
EXCLUDED_PAGES = {}
OUT_OF_FAMILY = {
    "MgH2": "200 nm thin film under 7 bar H2 (Palm 2018): film-only data, thin-film follow-up",
    "TiH2": "200 nm thin film under 7 bar H2 (Palm 2018): film-only data, thin-film follow-up",
    "Ti3C2": "MXene (2D): 2D / thin-film follow-up",
    "MoOCl2": "layered van der Waals crystal measured by a 2D-materials group, sample form not stated: 2D / thin-film follow-up",
    "CO": "gas",
}

# Ambient-condition structure (name, space-group number, symbol), standard crystallography, used ONLY to choose the MP entry for
# the calculated density.
AMBIENT_STRUCTURE = {
    "AlPO4": ("berlinite", 152, "P3_121"),
    "CaSO4": ("anhydrite", 63, "Cmcm"),
    "KH2PO4": ("tetragonal KDP", 122, "I-42d"),
    "NH4H2PO4": ("tetragonal ADP", 122, "I-42d"),
    "KTiOPO4": ("KTP-type", 33, "Pna2_1"),
    "RbTiOPO4": ("KTP-type", 33, "Pna2_1"),
}
