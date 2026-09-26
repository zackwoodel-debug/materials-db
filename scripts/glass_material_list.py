#!/usr/bin/env python3
"""
scripts/glass_material_list.py
==============================
The glasses family: substrate, window and cover glasses and a few special glasses from refractiveindex.info's `glass` shelf and
the SCHOTT / Corning catalogs of its `specs` shelf. Fused silica is not here: it is the amorphous dataset of the SiO2 material.

Glasses are multicomponent (compositions proprietary or ratios, not one formula), so formula is NULL, there is no Materials
Project entry and no x-ray / neutron SLD (it needs a composition). Density only where the manufacturer's page states it.
Every page is listed explicitly (shelf, book, page) with the sample variant it describes; the variant is the first segment of
the dataset label ("clear window glass | Rubin1985"), so variants are never compared or combined with each other.
"""

SODA_LIME = [  # (page, variant): every Rubin 1985 window glass, the Kamptner slide (both float surfaces), Vogt's iron series
    ("Rubin-clear", "clear window glass"), ("Rubin-lowiron", "low-iron window glass"), ("Rubin-bronze", "bronze window glass"),
    ("Rubin-grey", "grey window glass"), ("Rubin-green", "green window glass"), ("Rubin-IR", "window glass"),
    ("Kamptner", "microscope slide, air side"), ("Kamptner-tin-side", "microscope slide, tin side"),
    ("Vogt-5ppm", "5 ppm Fe2O3"), ("Vogt-10ppm", "10 ppm Fe2O3"), ("Vogt-703ppm", "703 ppm Fe2O3"),
]


def _m(key, name, pages, materialclass="glass", note=None, density_page=None):
    """pages: [(shelf, book, page, variant or None)]; density_page: (shelf, book, page) whose PROPERTIES.density is used."""
    return dict(key=key, name=name, pages=pages, materialclass=materialclass, note=note, density_page=density_page)


MATERIALS = [
    _m("soda-lime", "Soda-lime silica glass", [("glass", "soda-lime", p, v) for p, v in SODA_LIME]
       + [("glass", "Pilkington-Optiwhite", "Treharne", "low-iron float glass (Pilkington Optiwhite)")],
       note="window, slide and float glass variants are separate datasets labelled by variant"),
    _m("N-BK7", "N-BK7 borosilicate crown glass (SCHOTT)", [("specs", "SCHOTT-optical", "N-BK7", "N-BK7"),
                                                            ("glass", "BK7-Schott", "Lane", "BK7")],
       note="Lane 1990 measured BK7 (the predecessor of N-BK7) in the infrared", density_page=("specs", "SCHOTT-optical", "N-BK7")),
    _m("B270", "B 270 Superwite crown glass (SCHOTT)", [("specs", "SCHOTT-misc", "B270", None)], note="modified soda-lime glass"),
    _m("BOROFLOAT33", "BOROFLOAT 33 borosilicate glass (SCHOTT)", [("specs", "SCHOTT-misc", "BOROFLOAT33", None)],
       density_page=("specs", "SCHOTT-misc", "BOROFLOAT33")),
    _m("D263TECO", "D 263 T eco thin borosilicate glass (SCHOTT)", [("specs", "SCHOTT-misc", "D263TECO", None)],
       note="cover-slip and thin-substrate glass", density_page=("specs", "SCHOTT-misc", "D263TECO")),
    _m("AF32ECO", "AF 32 eco alkali-free thin glass (SCHOTT)", [("specs", "SCHOTT-misc", "AF32ECO", None)],
       density_page=("specs", "SCHOTT-misc", "AF32ECO")),
    _m("ZERODUR", "ZERODUR glass-ceramic (SCHOTT)", [("specs", "SCHOTT-misc", "ZERODUR", None)], materialclass="glass-ceramic"),
    _m("EagleXG", "EAGLE XG display glass (Corning)", [("specs", "CORNING-display", "EagleXG", None)]),
    _m("K108", "K108 crown glass (LZOS)", [("glass", "K108-LZOS", "Bassarab", None)]),
    _m("BGG", "Barium gallogermanate glass (BGG)", [("glass", "BGG", "Zelmon", None)], note="BaO : Ga2O3 : GeO2 = 42.9 : 17.0 : 40.1"),
    _m("ZBLAN", "ZBLAN fluoride glass", [("glass", "ZBLAN", "Gan", None)], note="ZrF4-BaF2-LaF3-AlF3-NaF fluoride glass"),
]

EXCLUDED_PAGES = {
    ("glass", "soda-lime", "Nyakuchena"): "glass microspheres, not a bulk glass (scope rule)",
    ("specs", "SCHOTT-misc", "DURAN"): ("one refractive-index point only (n = 1.473 at 587.6 nm) plus k digitised from a transmission "
                                        "figure: no dispersion. Its PROPERTIES say nd = 1.527, contradicting its own n; the page itself "
                                        "says to use BOROFLOAT 33's data (loaded)"),
    ("specs", "SCHOTT-misc", "LITHOSIL-Q"): "obsolete fused silica grade; fused silica is the amorphous dataset of SiO2",
    ("specs", "SCHOTT-misc", "LITHOTEC-CAF2"): "obsolete CaF2 crystal grade; CaF2 is already a material",
}
OUT_OF_FAMILY = {
    "infrared chalcogenide glasses (AMTIR, IG, IRG, BD)": ("several are loaded materials under a product name (AMTIR-6 = As2S3, IG6 = "
                                                           "As2Se3) and the others have non-integer compositions (Ge33As12Se55): "
                                                           "a separate batch with the composition convention"),
    "optical-glass catalogs (SCHOTT, OHARA, HIKARI, CDGM, HOYA, SUMITA, LZOS; ~1,680 glasses)": (
        "lens-design glasses; only substrate glasses are in this family (N-BK7)"),
    "HIKARI miscellaneous (NIFS, NICF, numbered)": "NICF is CaF2 crystal (loaded); the rest are lens materials",
}
