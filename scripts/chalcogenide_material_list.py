#!/usr/bin/env python3
"""
scripts/chalcogenide_material_list.py
======================================
Candidate list for the sulfide/selenide family: BULK-crystal (or bulk-like amorphous film) sulfides and selenides in RI.info's `main` shelf that no
earlier family holds. A CHECKLIST: scripts/match_ri_info_chalcogenides.py scans the catalog and is authoritative. Formulas are the ones RI.info
prints in the book title. Tellurides are not part of this run.

Scope rule (applies to every book): the selected pages must not describe the sample as a nm-scale film, few-layer film or exfoliated flake. Those
n,k values are tied to thickness/substrate (the 2D / thin-film follow-up in NOTES.md), not to a bulk crystal, and are listed in OUT_OF_FAMILY.
"""


def _c(key, name, formula, book, materialclass, note=None, page_polymorph=None, basis=None):
    return dict(key=key, name=name, formula=formula, book=book, shelf="main", note=note, materialclass=materialclass,
                page_polymorph=page_polymorph or {}, basis=basis)


MULTI_BASIS = ("multi-paper: every RI.info paper is loaded as its own labelled dataset (standing rule 'whatever gives more info', as for SiC and "
               "the halides); none is dropped or merged; primary = measured before model fits, then widest span covering 633 nm")

CANDIDATES = [
    # sulfides
    _c("Ag3AsS3", "Silver arsenic sulfide (proustite)", "Ag3AsS3", "Ag3AsS3", "sulfide", note="birefringent"),
    _c("AgGaS2", "Silver gallium sulfide (AGS)", "AgGaS2", "AgGaS2", "sulfide", note="birefringent", page_polymorph={"Takaoka-o": None, "Takaoka-e": None, "Kato-o": None, "Kato-e": None, "Boyd-o": None, "Boyd-e": None}, basis=MULTI_BASIS),
    _c("BaGa4S7", "Barium gallium sulfide (BGS)", "BaGa4S7", "BaGa4S7", "sulfide", note="birefringent", page_polymorph={"Badikov-α": None, "Badikov-β": None, "Badikov-γ": None, "Kato-α": None, "Kato-β": None, "Kato-γ": None}, basis=MULTI_BASIS),
    _c("CdGa2S4", "Cadmium gallium sulfide", "CdGa2S4", "CdGa2S4", "sulfide", note="birefringent"),
    _c("CuGaS2", "Copper gallium sulfide", "CuGaS2", "CuGaS2", "sulfide", note="birefringent"),
    _c("HgGa2S4", "Mercury gallium sulfide", "HgGa2S4", "HgGa2S4", "sulfide", note="birefringent"),
    _c("LiGaS2", "Lithium gallium sulfide (LGS)", "LiGaS2", "LiGaS2", "sulfide", note="biaxial"),
    # selenides
    _c("AgGaSe2", "Silver gallium selenide (AGSe)", "AgGaSe2", "AgGaSe2", "selenide", note="birefringent", page_polymorph={"Kato-o": None, "Kato-e": None, "Harasaki-o": None, "Harasaki-e": None, "Boyd-o": None, "Boyd-e": None}, basis=MULTI_BASIS),
    _c("As2Se3", "Arsenic triselenide", "As2Se3", "As2Se3", "selenide",
       note="RI.info pages are 400 nm and 700 nm amorphous films on glass (two papers); density is a bulk approximation", page_polymorph={"Joseph-400nm": None, "Joseph-700nm": None}, basis=MULTI_BASIS),
    _c("BaGa2GeSe6", "Barium gallium germanium selenide (BGGSe)", "BaGa2GeSe6", "BaGa2GeSe6", "selenide"),
    _c("BaGa4Se7", "Barium gallium selenide (BGSe)", "BaGa4Se7", "BaGa4Se7", "selenide", note="biaxial", page_polymorph={"Badikov-α": None, "Badikov-β": None, "Badikov-γ": None, "Kato-α": None, "Kato-β": None, "Kato-γ": None}, basis=MULTI_BASIS),
    _c("CdSe", "Cadmium selenide", "CdSe", "CdSe", "selenide",
       note="Ninomiya & Adachi states the phase on its pages (hexagonal o/e, cubic); Lisitsa and Bond state only o/e rays, no phase",
       page_polymorph={"Lisitsa-o": None, "Lisitsa-e": None, "Bond-o": None, "Bond-e": None, "Ninomiya-o": "hexagonal", "Ninomiya-e": "hexagonal",
                       "Ninomiya-cubic": "cubic"}, basis=MULTI_BASIS + "; phase labels only where the source page states one"),
    _c("PbSe", "Lead selenide", "PbSe", "PbSe", "selenide", page_polymorph={"Zemel": None, "Suzuki": None}, basis=MULTI_BASIS),
    _c("SnSe", "Tin selenide", "SnSe", "SnSe", "selenide", note="biaxial; RI.info does not state the sample form (crystal vs film)"),
    _c("Tl3AsSe3", "Thallium arsenic selenide (TAS)", "Tl3AsSe3", "Tl3AsSe3", "selenide", note="birefringent"),
    _c("ZnSe", "Zinc selenide", "ZnSe", "ZnSe", "selenide", page_polymorph={"Marple": None, "Amotchkina": None, "Querry": None, "Connolly": None, "Adachi": None}, basis=MULTI_BASIS),
]

# Books in scope but NOT loaded in this run because they need a user decision (evidence recorded in data/chalcogenide_gaps.csv).
DEFERRED = {
    "GaSe": ("all four GaSe formula pages give n^2 <= 0 inside their own stated ranges (reststrahlen band: Kato 2013 o 39.4-47.1 um, e 37.3-44.6 um; "
             "Chen 2009 n-formula o 39.2-46.8 um and 511.6-512.0 um, e 40.7-42.2 um), which the pipeline would store as floored n ~1e-15; "
             "Kato 2013 page title says 0.8-162 um but its data file says 0.8-1620 um; density needs a polytype choice (MP: P6_3mc mp-568263, "
             "P6_3/mmc mp-1943, P-6m2 (epsilon) mp-1572, R3m (gamma) mp-11342 all within 1.5 meV of the hull). "
             "Recommended: drop n^2<=0 samples instead of flooring, use the narrower 0.8-162 um range, epsilon-GaSe (P-6m2) density."),
}
# Single pages excluded from an otherwise loaded material, with the evidence (the rest of the paper IS loaded).
EXCLUDED_PAGES = {
    ("SnSe", "Guo-\u03b1"): ("alpha-axis data is physically implausible for SnSe (narrow-gap semiconductor, epsilon_inf > 10 on every axis): the source gives "
                          "n = 1.24-1.49 and k = 0.000 exactly over 0.19-1.7 um, while its beta and gamma axes have n ~2.5-2.7, k ~1.5-1.9 at 0.6 um. "
                          "Not loaded (the DB cannot carry a warning); beta and gamma are loaded. Reversible user decision."),
}

# `main` sulfide/selenide books deliberately NOT in this family, with the reason (each is a follow-up, not a gap of this run).
_2D = "layered van der Waals material measured as nm-scale film / few-layer / exfoliated flake: n,k depend on thickness and substrate (2D / thin-film follow-up)"
OUT_OF_FAMILY = {
    "CS2": "liquid",
    **{k: _2D for k in ("MoS2", "WS2", "ReS2", "TaS2", "PtS2", "SnS2", "NiPS3", "MoSe2", "WSe2", "NbSe2", "TaSe2", "PtSe2", "PdSe2", "SnSe2",
                        "HfSe2", "ZrSe2", "In2Se3", "MnPSe3", "Bi2Se3")},
}
# Already loaded by an earlier family (batch 2): As2S3, CdS, EuS, GaS, GeS2, HgS, PbS, ZnS.
ALREADY_LOADED = ["As2S3", "CdS", "EuS", "GaS", "GeS2", "HgS", "PbS", "ZnS"]

# Ambient-condition crystal structure (name, space-group number, symbol), standard crystallography, used ONLY to choose which Materials Project
# entry supplies the calculated density (the halide lesson: the lowest-energy MP entry is often another phase). Only structures known with
# confidence are listed; for every other material the generic rule applies (exactly one non-theoretical MP entry near the hull, else NULL).
AMBIENT_STRUCTURE = {
    "Ag3AsS3": ("proustite", 161, "R3c"),
    "AgGaS2": ("chalcopyrite", 122, "I-42d"),
    "AgGaSe2": ("chalcopyrite", 122, "I-42d"),
    "CuGaS2": ("chalcopyrite", 122, "I-42d"),
    "LiGaS2": ("beta-NaFeO2-type", 33, "Pna2_1"),
    "ZnSe": ("zincblende", 216, "F-43m"),
    "PbSe": ("rock-salt", 225, "Fm-3m"),
    "SnSe": ("Pnma (GeS-type)", 62, "Pnma"),
    "CdSe": ("wurtzite", 186, "P6_3mc"),
}
