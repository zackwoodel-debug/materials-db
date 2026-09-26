#!/usr/bin/env python3
"""
scripts/optical_media_material_list.py
======================================
The optical-media family: commercial index-matching liquids, a cured optical adhesive and microscopy mounting media, from
refractiveindex.info (`specs` Cargille catalog; `other` optical adhesives and mounting media). Proprietary formulations: formula
NULL, no SLD, no structure; density only where the manufacturer states it (Cargille, at 25 degC). Built by
scripts/build_optical_media_csv.py with the shared listed-pages builder.
"""
from glass_material_list import _m  # same record shape as the glasses

MATERIALS = [
    _m("Cargille-BK7", "Cargille BK7 matching liquid", [("specs", "Cargille", "BK7_matching_liquid", None)],
       materialclass="index-matching liquid", density_page=("specs", "Cargille", "BK7_matching_liquid")),
    _m("Cargille-06350", "Cargille fused silica matching liquid 06350", [("specs", "Cargille", "Cargille-06350", None)],
       materialclass="index-matching liquid", density_page=("specs", "Cargille", "Cargille-06350")),
    _m("Cargille-50350", "Cargille fused silica matching liquid 50350", [("specs", "Cargille", "Cargille-50350", None)],
       materialclass="index-matching liquid", density_page=("specs", "Cargille", "Cargille-50350")),
    _m("Cargille-acrylic", "Cargille acrylic matching liquid", [("specs", "Cargille", "acrylic_matching_liquid", None)],
       materialclass="index-matching liquid", density_page=("specs", "Cargille", "acrylic_matching_liquid")),
    _m("Cargille-acrylic-double", "Cargille acrylic double matching liquid", [("specs", "Cargille", "acrylic_double_matching_liquid", None)],
       materialclass="index-matching liquid", density_page=("specs", "Cargille", "acrylic_double_matching_liquid")),
    _m("NOA61", "Norland NOA 61 optical adhesive (cured)", [("other", "Norland_NOA-61", "Norland", None)],
       materialclass="optical adhesive", note="UV-curable adhesive; manufacturer's cured-state dispersion"),
    _m("Eukitt", "Eukitt mounting medium", [("other", "Eukitt", "Nyakuchena", None)], materialclass="mounting medium",
       note="near-infrared only (1.1-1.65 um), 23 degC"),
    _m("FluorSave", "FluorSave mounting medium", [("other", "FluorSave", "Nyakuchena", None)], materialclass="mounting medium",
       note="near-infrared only (1.1-1.65 um), 23 degC"),
]

_UNCURED = "source states the film is uncured; uncured resin n is not a material constant (user decision, as for SU-8 2000)"
_CURE_UNSTATED = ("2 um spin-coated film whose cure state the page does not state; for a UV-curable adhesive n depends on the cure "
                  "(user decision on uncured resins): deferred until the paper confirms the state")
EXCLUDED_PAGES = {
    ("other", "Norland_NOA-61", "Joseph"): _UNCURED,
}
OUT_OF_FAMILY = {
    "Loctite 3526 (Iezzi 2020)": _CURE_UNSTATED,
    "Norland NOA 170 (Iezzi 2020)": _CURE_UNSTATED,
    "Norland NOA 1348 (Iezzi 2020)": _CURE_UNSTATED,
    "immersion oils (Leica Type F, Olympus IMMOIL-F30CC, Sigma Aldrich M5904)": "k only (Wang 2017, 1.2-1.9 um): no refractive index to load",
}
