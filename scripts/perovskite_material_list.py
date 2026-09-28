#!/usr/bin/env python3
"""
scripts/perovskite_material_list.py
===================================
Metal halide perovskites from refractiveindex.info's `other` shelf: MAPbI3, MAPbBr3 (hybrid organic-inorganic), CsPbBr3,
CsPbCl3 and the mixed CsPb(Br,Cl)3 crystals. Built by scripts/build_perovskites_csv.py. Same rules as the alloys
(scripts/alloy_material_list.py): each composition its own material, preparation (single crystal, film, orientation) is the
variant, the CsPb(Br,Cl)3 series and its end members are one ML split group. Pure compounds get their identity from PubChem.
Perovskite optical constants depend strongly on the sample (single crystal vs polycrystalline film, orientation, humidity):
compare variants only knowingly.
"""

_O = "other"


def _p(book, page, variant=None, axis=None):
    return dict(shelf=_O, book=book, page=page, variant=variant, axis=axis)


def _m(series, key, name, formula, pages, materialclass, pubchem=True, pubchem_name=None, note=None):
    return dict(key=f"{series}@{key}", name=name, pages=pages, formula=formula, pubchem=pubchem, pubchem_name=pubchem_name or name,
                note=note, density_page=None, materialclass=materialclass, series=series)


MATERIALS = [
    _m("MAPbX3", "MAPbI3", "Methylammonium lead iodide (MAPbI3)", "CH3NH3PbI3",
       [_p("CH3NH3PbI3", "Leguy", "single crystal"), _p("CH3NH3PbI3", "Ball", "film"),
        _p("CH3NH3PbI3", "Phillips", "vapour-deposited film on Si")], "hybrid halide perovskite",
       pubchem_name="methylammonium lead iodide",
       note="Leguy 2015: critical-point model fit, not reliable below the band gap (the page)"),
    _m("MAPbX3", "MAPbBr3", "Methylammonium lead bromide (MAPbBr3)", "CH3NH3PbBr3",
       [_p("CH3NH3PbBr3", "Ishteev", "single crystal"), _p("CH3NH3PbBr3", "McCleese", "single crystal, <100>")],
       "hybrid halide perovskite", pubchem_name="methylammonium lead bromide"),
    _m("CsPbX3", "CsPbBr3", "Cesium lead bromide (CsPbBr3)", "CsPbBr3",
       [_p("CsPbBr3", "Ermolaev-o", "single crystal", "o"), _p("CsPbBr3", "Ermolaev-e", "single crystal", "e"),
        _p("CsPbBr3", "Brennan", "Bridgman crystal, <251>")], "inorganic halide perovskite", pubchem_name="cesium lead bromide"),
    _m("CsPbX3", "CsPbCl3", "Cesium lead chloride (CsPbCl3)", "CsPbCl3",
       [_p("CsPbCl3", "Ermolaev-o", "single crystal", "o"), _p("CsPbCl3", "Ermolaev-e", "single crystal", "e"),
        _p("CsPbCl3", "Zhang", "198 nm vapour-deposited film on glass")], "inorganic halide perovskite", pubchem_name="cesium lead chloride"),
    _m("CsPbX3", "CsPbBr1.3Cl1.7", "Cesium lead bromide chloride CsPbBr1.3Cl1.7", "CsPbBr1.3Cl1.7",
       [_p("CsPb_BrCl_3", "Ermolaev-Br1.3Cl1.7-o", "single crystal", "o"), _p("CsPb_BrCl_3", "Ermolaev-Br1.3Cl1.7-e", "single crystal", "e")],
       "inorganic halide perovskite", pubchem=False),
    _m("CsPbX3", "CsPbBr1.8Cl1.2", "Cesium lead bromide chloride CsPbBr1.8Cl1.2", "CsPbBr1.8Cl1.2",
       [_p("CsPb_BrCl_3", "Ermolaev-Br1.8Cl1.2-o", "single crystal", "o"), _p("CsPb_BrCl_3", "Ermolaev-Br1.8Cl1.2-e", "single crystal", "e")],
       "inorganic halide perovskite", pubchem=False),
]

# 2D perovskites (Song 2021, spin-coated films on glass). The formula is fixed by CHARGE NEUTRALITY of the ions the page itself
# names -- BA+ = CH3(CH2)3NH3+ (C4H12N), MA+ = CH3NH3+ (CH6N), 4AMP2+ = 4-(aminomethyl)piperidinium (C6H16N2), Pb2+, I-:
#   Ruddlesden-Popper (BA)2(MA)n-1 Pb_n I_(3n+1):   2 + (n-1) + 2n = 3n+1 iodides. The page writes I_(3n-1), which would leave
#     the crystal +2 charged (n = 1 would be (BA)2PbI2 instead of the well-known (BA)2PbI4): a typo, recorded, not used.
#   Dion-Jacobson (4AMP)(MA)m-1 Pb_m I_(3m+1):       2 + (m-1) + 2m = 3m+1, as the page writes.
_2D_NOTE = ("layered and optically anisotropic: these are ellipsometric constants of spin-coated films on glass (an effective "
            "film response), not axis-resolved crystal values; higher-n films can contain other n phases")


def _rp(n):
    return _m("RP-BA-MA", f"n{n}", f"Ruddlesden-Popper 2D perovskite BA2 MA{n - 1} Pb{n} I{3 * n + 1}, n = {n}",
              f"C{n + 7}H{6 * n + 18}N{n + 1}Pb{n}I{3 * n + 1}", [_p("2D_HOIP", f"Song-RP{n}", "spin-coated film on glass")],
              "2D hybrid halide perovskite", pubchem=False,
              note=f"(BA)2(MA){n - 1}Pb{n}I{3 * n + 1} by charge neutrality (the page writes I3n-1, a typo); " + _2D_NOTE)


def _dj(m):
    return _m("DJ-4AMP-MA", f"m{m}", f"Dion-Jacobson 2D perovskite 4AMP MA{m - 1} Pb{m} I{3 * m + 1}, m = {m}",
              f"C{m + 5}H{6 * m + 10}N{m + 1}Pb{m}I{3 * m + 1}", [_p("2D_HOIP", f"Song-DJ{m}", "spin-coated film on glass")],
              "2D hybrid halide perovskite", pubchem=False, note=f"(4AMP)(MA){m - 1}Pb{m}I{3 * m + 1}, as the page writes; " + _2D_NOTE)


MATERIALS += [_rp(n) for n in range(1, 6)] + [_dj(m) for m in range(1, 5)]

EXCLUDED_PAGES = {
    (_O, "CH3NH3PbI3", "Leguy-hydrated"): "CH3NH3PbI3.H2O: a different compound (the monohydrate), 207-427 nm only",
}
OUT_OF_FAMILY = {}
# the n, m -> infinity limit of both 2D series is 3D MAPbI3: they join its group in the ML splits
SERIES_END_MEMBERS = {"MAPbX3": [], "CsPbX3": [], "RP-BA-MA": ["perovskites:MAPbX3@MAPbI3"], "DJ-4AMP-MA": ["perovskites:MAPbX3@MAPbI3"]}
