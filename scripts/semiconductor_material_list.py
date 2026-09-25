#!/usr/bin/env python3
"""
scripts/semiconductor_material_list.py
=======================================
Candidate list for the compound-semiconductor family: bulk III-V semiconductors, the II-VI / IV-VI tellurides (not part of the
chalcogenide run) and the II-IV-V2 chalcopyrite pnictides in RI.info's `main` shelf that no earlier family holds. A CHECKLIST:
scripts/match_ri_info_semiconductors.py scans the catalog and is authoritative. Formulas are the ones RI.info prints in the book title.

Scope rule (as for the chalcogenides): the selected pages must not describe the sample as a film, few-layer film or flake. Such pages
are listed in EXCLUDED_PAGES (a bulk paper of the same material IS loaded) or, when the whole book is film/flake data, OUT_OF_FAMILY.
Multi-paper books load every listed page as its own labelled dataset (standing rule 'whatever gives more info'); temperature series
are separate datasets carrying their temperature. Pages are listed explicitly so a new upstream page never enters unreviewed.
"""


def _c(key, name, formula, materialclass, pages=None, note=None, book=None):
    return dict(key=key, name=name, formula=formula, book=book or key, shelf="main", note=note, materialclass=materialclass,
                page_polymorph={p: None for p in pages} if pages else {},
                basis=MULTI_BASIS if pages else None)


MULTI_BASIS = ("multi-paper: every RI.info paper is loaded as its own labelled dataset (standing rule 'whatever gives more info', as for SiC, "
               "the halides and chalcogenides); none is dropped or merged; primary = ambient temperature, measured before model fits, then widest span covering 633 nm")

CANDIDATES = [
    # III-V
    _c("AlAs", "Aluminium arsenide", "AlAs", "III-V semiconductor", ["Fern", "Gadras", "Rakic"],
       note="Gadras 2025 is AlxGa1-xAs with x = 1.0 at 600 degC (temperature on the rows)"),
    _c("AlSb", "Aluminium antimonide", "AlSb", "III-V semiconductor", ["Zollner", "Adachi", "Djurisic"]),
    _c("BP", "Boron phosphide", "BP", "III-V semiconductor"),
    _c("GaAs", "Gallium arsenide", "GaAs", "III-V semiconductor",
       ["Aspnes", "Franta-300K", "Franta-370K", "Franta-440K", "Gadras", "Perner", "Papatryfonos", "Skauli", "Jellison", "Kachare",
        "Adachi", "Rakic", "Ozaki"],
       note="Franta 2026 is a 300/370/440 K series; Gadras 2025 is AlxGa1-xAs with x = 0.0 at 600 degC"),
    _c("GaP", "Gallium phosphide", "GaP", "III-V semiconductor", ["Aspnes", "Khmelevskaia", "Jellison", "Parsons", "Bond", "Adachi"]),
    _c("GaSb", "Gallium antimonide", "GaSb", "III-V semiconductor", ["Aspnes", "Adachi", "Djurisic"]),
    _c("InAs", "Indium arsenide", "InAs", "III-V semiconductor", ["Aspnes", "Lorimor", "Adachi"]),
    _c("InP", "Indium phosphide", "InP", "III-V semiconductor", ["Aspnes", "Panah", "Pettit", "Adachi"]),
    _c("InSb", "Indium antimonide", "InSb", "III-V semiconductor", ["Aspnes", "Adachi", "Djurisic"]),
    # II-VI and IV-VI tellurides
    _c("CdTe", "Cadmium telluride", "CdTe", "II-VI semiconductor", ["Marple", "DeBell-300K", "DeBell-80K", "DeBell-20K", "Adachi"],
       note="DeBell 1979 is a 300/80/20 K series"),
    _c("ZnTe", "Zinc telluride", "ZnTe", "II-VI semiconductor", ["Marple", "Li", "Sato"]),
    _c("PbTe", "Lead telluride", "PbTe", "IV-VI semiconductor", ["Weiting-300K", "Weiting-130K", "Weiting-80K"],
       note="one paper, a 300/130/80 K series (its title's range differs per temperature, so the pages are listed)"),
    # II-IV-V2 chalcopyrites (birefringent nonlinear-optical crystals)
    _c("CdGeAs2", "Cadmium germanium arsenide", "CdGeAs2", "chalcopyrite semiconductor", note="birefringent"),
    _c("CdGeP2", "Cadmium germanium phosphide", "CdGeP2", "chalcopyrite semiconductor", note="birefringent; Boyd 1972 is a 20/118 degC series"),
    _c("ZnGeP2", "Zinc germanium phosphide (ZGP)", "ZnGeP2", "chalcopyrite semiconductor",
       ["Boyd-20C-o", "Boyd-20C-e", "Boyd-70C-o", "Boyd-70C-e", "Das-o", "Das-e", "Zelmon-o", "Zelmon-e"]
       + [f"Ghosh-{t}K-{ax}" for t in (100, 150, 200, 250, 300, 350, 400, 450, 500) for ax in ("o", "e")],
       note="birefringent; Boyd 1971 20/70 degC and Ghosh 1998 100-500 K series"),
    _c("ZnSiAs2", "Zinc silicon arsenide", "ZnSiAs2", "chalcopyrite semiconductor", note="birefringent"),
]

# Books in scope but NOT loaded in this run because they need a user decision (evidence recorded in data/semiconductor_gaps.csv).
DEFERRED = {
    "Ge2Sb2Te5": ("phase-change material: Frantz 2024 gives crystalline and amorphous Ge2Sb2Te5 (one paper, two phases). The crystalline "
                  "density needs a structure choice (metastable rock-salt vs stable trigonal GST) and the amorphous phase has no density "
                  "source; load after that decision."),
}
# Single pages excluded from an otherwise loaded material, with the evidence (the material's bulk papers ARE loaded).
EXCLUDED_PAGES = {
    ("CdTe", "Treharne"): ("sputtered film: 'A CdTe film was deposited on to a soda-lime glass substrate using RF magnetron sputtering' "
                           "(film n,k depend on deposition; scope rule). Bulk papers Marple, DeBell, Adachi are loaded."),
    ("GaSb", "Ferrini"): ("film: 'Thin film grown by molecular beam epitaxy on a GaSb substrate' (the page also mislabels x = 0 as GaAs); "
                          "scope rule. Bulk papers Aspnes, Adachi, Djurisic are loaded."),
}
# Semiconductor books in `main` deliberately NOT in this family, with the reason (each is a follow-up, not a gap of this run).
OUT_OF_FAMILY = {
    "Bi2Te3": "CVD flakes on Si/SiO2 (Ermolaev 2024): thickness/substrate-dependent, 2D / thin-film follow-up",
    **{k: "layered van der Waals telluride measured as flake / few-layer film: 2D / thin-film follow-up" for k in ("MoTe2", "WTe2", "ZrTe5")},
}

# Ambient-condition crystal structure (name, space-group number, symbol), standard crystallography, used ONLY to choose which Materials
# Project entry supplies the calculated density (the lowest-energy MP entry can be another phase, e.g. wurtzite vs zincblende).
_ZB = ("zincblende", 216, "F-43m")
_CH = ("chalcopyrite", 122, "I-42d")
AMBIENT_STRUCTURE = {
    **{k: _ZB for k in ("AlAs", "AlSb", "BP", "GaAs", "GaP", "GaSb", "InAs", "InP", "InSb", "CdTe", "ZnTe")},
    "PbTe": ("rock-salt", 225, "Fm-3m"),
    **{k: _CH for k in ("CdGeAs2", "CdGeP2", "ZnGeP2", "ZnSiAs2")},
}
