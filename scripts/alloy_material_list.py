#!/usr/bin/env python3
"""
scripts/alloy_material_list.py
==============================
Solid solutions and doped crystals from refractiveindex.info's `other` shelf: composition series (AlGaAs, AlGaSb, SiGe, ZnCdO,
SiOx), lattice-matched alloys (InGaAs, GaInP, AgGa(1-x)In(x)S2), mixed halide crystals (KRS-5, KRS-6), yttria-stabilized oxides,
and doped crystals / transparent conducting oxides (MgO:LiNbO3, Mg:LiTaO3, ITO, AZO, AlON). Built by scripts/build_alloys_csv.py.

Rules (user decision 2026-09-27):
  * each COMPOSITION is its own material, with its fractional formula exactly as the page states it (x from the page's text or
    CONDITIONS; a mol% of an oxide or halide converts exactly); the source tag keeps papers apart;
  * samples that differ only by preparation (substrate, thickness, top / bottom of a graded film) are variants of one material;
  * a series and its end members are ONE group in the ML splits (SERIES below): interpolating between neighbouring compositions
    is not a test of a model;
  * end-member pages (x = 0 or 1) are not loaded: the pure compound is already a material (usually with the same paper);
  * no composition is guessed: a doped crystal or TCO whose page gives no exact composition has formula NULL (its dopant level in
    the name), and a page whose composition contradicts itself is excluded.
Identity: no PubChem lookup (a fractional formula has no compound record).
"""

_O = "other"


def _p(book, page, variant=None, axis=None, suffix=None):
    return dict(shelf=_O, book=book, page=page, variant=variant, axis=axis, tag_suffix=suffix)


def _series(series, key, name, formula, pages, materialclass, note=None):
    return dict(key=f"{series}@{key}", name=name, pages=pages, formula=formula, note=note, density_page=None, pubchem=False,
                materialclass=materialclass, series=series)


def _algaas(x, pages, note=None):
    xs = f"{x:.3f}".rstrip("0").rstrip(".")
    ga = f"{1 - x:.3f}".rstrip("0").rstrip(".")
    return _series("AlGaAs", f"x{xs}", f"Aluminium gallium arsenide Al{xs}Ga{ga}As", f"Al{xs}Ga{ga}As", pages, "III-V alloy", note)


_600C = "600 degC (Gadras 2025: in-situ, during growth)"
MATERIALS = [
    # --- AlxGa1-xAs (x = Al fraction; Aspnes 1986, Papatryfonos 2021, Adachi 1989 model, Gadras 2025 at 600 degC, Perner 2023)
    _algaas(0.097, [_p("AlAs-GaAs", "Papatryfonos-9.7")]),
    _algaas(0.099, [_p("AlAs-GaAs", "Aspnes-9.9")]),
    _algaas(0.198, [_p("AlAs-GaAs", "Aspnes-19.8")]),
    _algaas(0.219, [_p("AlAs-GaAs", "Papatryfonos-21.9")]),
    _algaas(0.315, [_p("AlAs-GaAs", "Aspnes-31.5"), _p("AlAs-GaAs", "Adachi-0.315")]),
    _algaas(0.32, [_p("AlAs-GaAs", "Gadras-32")], note=_600C),
    _algaas(0.342, [_p("AlAs-GaAs", "Papatryfonos-34.2")]),
    _algaas(0.411, [_p("AlAs-GaAs", "Papatryfonos-41.1")]),
    _algaas(0.419, [_p("AlAs-GaAs", "Aspnes-41.9")]),
    _algaas(0.452, [_p("AlAs-GaAs", "Papatryfonos-45.2")]),
    _algaas(0.491, [_p("AlAs-GaAs", "Aspnes-49.1")]),
    _algaas(0.53, [_p("AlAs-GaAs", "Gadras-53")], note=_600C),
    _algaas(0.59, [_p("AlAs-GaAs", "Aspnes-59.0")]),
    _algaas(0.7, [_p("AlAs-GaAs", "Aspnes-70.0"), _p("AlAs-GaAs", "Adachi-0.700")]),
    _algaas(0.804, [_p("AlAs-GaAs", "Aspnes-80.4")]),
    _algaas(0.929, [_p("AlAs-GaAs", "Perner-92.9")], note="Perner 2023: crystalline thin-film multilayer, 22 degC at 2.21 mbar"),
    # --- AlxGa1-xSb (Ferrini 1998, MBE films on GaSb)
    *[_series("AlGaSb", f"x{x}", f"Aluminium gallium antimonide Al{x}Ga{g}Sb", f"Al{x}Ga{g}Sb",
              [_p("AlSb-GaSb", page, "MBE film on GaSb")], "III-V alloy")
      for x, g, page in (("0.1", "0.9", "Ferrini-10"), ("0.3", "0.7", "Ferrini-30"), ("0.5", "0.5", "Ferrini-50"))],
    # --- SixGe1-x (Jellison 1993, x = Si fraction, from CONDITIONS)
    *[_series("SiGe", f"x{x}", f"Silicon-germanium Si{x}Ge{g}", f"Si{x}Ge{g}", [_p("Si-Ge", page, variant)], "group-IV alloy", note)
      for x, g, page, variant, note in (
          ("0.11", "0.89", "Jellison-11", "8 um film on Ge", None), ("0.2", "0.8", "Jellison-20", "8 um film on Ge", None),
          ("0.28", "0.72", "Jellison-28", "8 um film on Ge", None),
          ("0.48", "0.52", "Jellison-48", "4 um film on Ge",
           "x = 0.48 from the page name and its CONDITIONS; its comment says x = 0.28 (copied from the Jellison-28 page)"),
          ("0.47", "0.53", "Jellison-47", "7 um film on Si", None), ("0.65", "0.35", "Jellison-65", "8 um film on Si", None),
          ("0.85", "0.15", "Jellison-85", "7 um film on Si", None), ("0.98", "0.02", "Jellison-98", "8 um film on Si", None))],
    # --- lattice-matched alloys
    _series("InGaAs", "x0.48", "Indium gallium arsenide In0.52Ga0.48As", "In0.52Ga0.48As", [_p("GaAs-InAs", "Adachi")], "III-V alloy"),
    _series("InGaAs", "x0.47", "Indium gallium arsenide In0.53Ga0.47As", "In0.53Ga0.47As", [_p("GaAs-InAs", "Le", "310 nm film on Ge")],
            "III-V alloy"),
    _series("GaInP", "x0.49", "Gallium indium phosphide Ga0.51In0.49P", "Ga0.51In0.49P",
            [_p("GaP-InP", "Schubert"), _p("GaP-InP", "Ferrini-UV-VIS", "3.15 um MOVPE film on GaAs", suffix="UV-VIS"),
             _p("GaP-InP", "Ferrini-IR", "3.15 um MOVPE film on GaAs", suffix="IR"),
             _p("GaP-InP", "Ferrini-far-IR", "3.15 um MOVPE film on GaAs", suffix="far-IR")], "III-V alloy"),
    _series("AgGaInS2", "x0.14", "Silver gallium indium sulfide AgGa0.86In0.14S2", "AgGa0.86In0.14S2",
            [_p("AgGaS2-AgInS2", "Kato-o", axis="o"), _p("AgGaS2-AgInS2", "Kato-e", axis="e")], "chalcopyrite alloy"),
    # --- ZnxCd1-xO (Aguilar 2019 thin films)
    *[_series("ZnCdO", f"x{x}", f"Zinc cadmium oxide Zn{x}Cd{c}O", f"Zn{x}Cd{c}O", [_p("ZnO-CdO", page, "thin film")], "oxide alloy")
      for x, c, page in (("0.1", "0.9", "Aguilar-10"), ("0.25", "0.75", "Aguilar-25"), ("0.4", "0.6", "Aguilar-40"),
                         ("0.5", "0.5", "Aguilar-50"), ("0.63", "0.37", "Aguilar-63"), ("0.75", "0.25", "Aguilar-75"),
                         ("0.9", "0.1", "Aguilar-90"))],
    # --- SiOx (Herguedas 2023, sputtered, infrared)
    *[_series("SiOx", f"x{x}", f"Silicon suboxide SiO{x}", f"SiO{x}", [_p("Si-O", f"Herguedas-SiO{x}", "sputtered film")],
              "non-stoichiometric oxide")
      for x in ("0.31", "0.61", "1.10", "1.71", "1.89", "1.92")],
    # --- mixed halide crystals
    _series("KRS", "KRS-5", "Thallium bromide iodide (KRS-5)", "TlBr0.457I0.543", [_p("TlBr-TlI", "Rodney")], "mixed halide crystal",
            note="45.7 mol% TlBr + 54.3 mol% TlI (the page), 25 degC"),
    _series("KRS", "KRS-6", "Thallium bromide chloride (KRS-6)", None, [_p("TlBr-TlCl", "Hettner")], "mixed halide crystal",
            note="the page states no TlBr / TlCl ratio: formula NULL"),
    # --- yttria-stabilized oxides (mol% Y2O3 converts exactly: (MO2)(1-y)(Y2O3)y)
    _series("YSZ", "12mol", "Yttria-stabilized zirconia (12 mol% Y2O3)", "Zr0.88Y0.24O2.12", [_p("ZrO2-Y2O3", "Wood", "cubic, single crystal")],
            "stabilized oxide", note="12.0 mol% Y2O3 (the page), 25 degC: (ZrO2)0.88(Y2O3)0.12"),
    _series("YSH", "9.8mol", "Yttria-stabilized hafnia (9.8 mol% Y2O3)", "Hf0.902Y0.196O2.098", [_p("HfO2-Y2O3", "Wood", "cubic, single crystal")],
            "stabilized oxide", note="9.8 mol% Y2O3 (the page), 20 degC: (HfO2)0.902(Y2O3)0.098"),
    # --- doped crystals and transparent conducting oxides: no exact composition on the page -> formula NULL
    _series("MgO-LiNbO3", "CLN-5mol", "Lithium niobate, congruent, 5 mol% MgO", None,
            [_p("MgO-LiNbO3", "Zelmon-o", axis="o"), _p("MgO-LiNbO3", "Zelmon-e", axis="e"),
             _p("MgO-LiNbO3", "Gayer-5-o", axis="o"), _p("MgO-LiNbO3", "Gayer-5-e", axis="e")], "doped crystal",
            note="congruent LiNbO3 (Li-deficient) doped with 5 mol% MgO: formula NULL (the dopant site occupancy is not stated)"),
    _series("MgO-LiNbO3", "SLN-1mol", "Lithium niobate, stoichiometric, 1 mol% MgO", None, [_p("MgO-LiNbO3", "Gayer-1-e", axis="e")],
            "doped crystal", note="stoichiometric LiNbO3 doped with 1 mol% MgO: formula NULL"),
    _series("Mg-LiTaO3", "CLT-8mol", "Lithium tantalate, congruent, 8 mol% Mg", None,
            [_p("Mg-LiTaO3", "Moutzouris-o", axis="o"), _p("Mg-LiTaO3", "Moutzouris-e", axis="e")], "doped crystal",
            note="8 mol% Mg-doped congruent LiTaO3: formula NULL. The '-o' page's comment and CONDITIONS say extraordinary (copied "
                 "from the '-e' page), but its coefficients differ and give n below the '-e' page's (2.1337 vs 2.1370 at 1 um: "
                 "LiTaO3's positive birefringence), so it is loaded as the ordinary ray"),
    _series("ITO", "ITO", "Indium tin oxide (ITO)", None,
            [_p("In2O3-SnO2", "Konig", "72 nm film on BK7"), _p("In2O3-SnO2", "Minenkov-glass", "110 nm film on glass"),
             _p("In2O3-SnO2", "Minenkov-wafer-top", "88 nm graded film on SiO2/Si, top"),
             _p("In2O3-SnO2", "Minenkov-wafer-bottom", "88 nm graded film on SiO2/Si, bottom"),
             _p("In2O3-SnO2", "Moerland", "17 nm film on D263M")], "transparent conducting oxide",
            note="commercial and sputtered films; the Sn content is not stated: formula NULL. Its optical constants depend on "
                 "deposition and carrier density: compare variants only knowingly"),
    _series("AZO", "AZO", "Aluminium-doped zinc oxide (AZO)", None, [_p("Al-ZnO", "Treharne", "sputtered film on soda-lime glass")],
            "transparent conducting oxide", note="approx. 2 wt% Al (the page): formula NULL"),
    # --- metal alloys. The pages give "% Cu" / "% Ni" without saying atomic or weight; for Cu-Zn and Ni-Fe the two readings differ
    # by < 1 at.% (near-equal atomic masses), so the formula is safe either way (tests/test_alloy_pipeline.py checks the bound).
    *[_series("CuZn", f"Cu{w}", f"Brass, {w} wt% Cu", f, [_p("Cu-Zn", f"Querry-Cu{w}Zn{100 - w}", "ingot")], "metal alloy",
              note=f"Querry 1985 'brass ingot ({w} Cu/{100 - w} Zn)': brass is specified by weight, converted to the atomic formula {f} "
                   "(read as atomic % instead it would differ by < 0.7 at.%)")
      for w, f in ((90, "Cu0.9026Zn0.0974"), (85, "Cu0.8536Zn0.1464"), (70, "Cu0.706Zn0.294"))],
    _series("NiFe", "Ni80Fe20", "Permalloy Ni80Fe20", "Ni0.8Fe0.2",
            [_p("Ni-Fe", "Tikuisis_bare150nm", "150 nm film, bare (2.3 nm oxide)"), _p("Ni-Fe", "Tikuisis_gold150nm", "150 nm film, 3 nm Au cap"),
             _p("Ni-Fe", "Tikuisis_bare10nm", "10 nm film, bare (4 nm oxide)"), _p("Ni-Fe", "Tikuisis_gold10nm", "10 nm film, 3 nm Au cap")],
            "metal alloy", note="ion-beam sputtered from a Ni80Fe20 target (Tikuisis 2017): the nominal target composition, not a measured "
                                "film composition; read as weight % it would be Ni0.792Fe0.208 (0.8 at.% apart). The 10 nm films' "
                                "constants are effective values of a thin film: compare the 150 nm variants with bulk"),
    *[_series("AlON", f"N{n}", f"Aluminium oxynitride (ALON), {n} at.% N", None, [_p("AlN-Al2O3", f"Hartnett-{n}")], "oxynitride ceramic",
              note=f"{n} at.% nitrogen (the page): formula NULL (Al:O not stated)")
      for n in ("5.88", "6.53", "6.69", "7.17")],
]

_END = "end member (x = {x}): the pure compound is already a material ({m})"
EXCLUDED_PAGES = {
    (_O, "AlAs-GaAs", "Aspnes-0"): _END.format(x=0, m="GaAs, with Aspnes 1986"),
    (_O, "AlAs-GaAs", "Papatryfonos-0"): _END.format(x=0, m="GaAs, with Papatryfonos 2021"),
    (_O, "AlAs-GaAs", "Gadras-0"): _END.format(x=0, m="GaAs, with Gadras 2025 at 600 degC"),
    (_O, "AlAs-GaAs", "Gadras-100"): _END.format(x=1, m="AlAs"),
    (_O, "AlAs-GaAs", "Perner-0"): _END.format(x=0, m="GaAs, with Perner 2023"),
    (_O, "AlAs-GaAs", "Gadras-90"): "composition contradicts itself: the page name says 90% Al, its comment x = 0.92",
    (_O, "AlSb-GaSb", "Ferrini-0"): _END.format(x=0, m="GaSb") + "; its comment calls it GaAs",
    (_O, "ZnO-CdO", "Aguilar-100"): _END.format(x=1, m="ZnO"),
    (_O, "GaP-InP", "Kaneko"): "composition not stated (GaInP films on GaAs, 580 and 851 nm)",
    (_O, "In2O3-SnO2", "Konig-EMA"): "a 2 nm surface-roughness layer (effective-medium model), not ITO",
    (_O, "Al-ZnO", "Shkondin"): "AZO nanopillars: an effective medium of a nanostructure, not the material",
}
OUT_OF_FAMILY = {
    "other/Au-Ag": "deferred: the pages do not say whether % is atomic or by weight, and for Au-Ag the readings differ by up to "
                   "15 at.% (Au50Ag50 by weight is Au0.354Ag0.646); every page is Rioux 2014's analytic model evaluated at a "
                   "composition (fitted to five measured films), not a measurement. The paper was not accessible to check",
    "other/CH3NH3PbI3 Leguy-hydrated": "see the perovskites family (the hydrate is a different compound)",
}
# ML splits: a series and its end members are one group (keys of materials in other families)
SERIES_END_MEMBERS = {
    "AlGaAs": ["semiconductors:GaAs", "semiconductors:AlAs"], "AlGaSb": ["semiconductors:GaSb", "semiconductors:AlSb"],
    "SiGe": ["pure_elements_50:Si@diamond cubic", "pure_elements_50:Ge@diamond cubic"],
    "InGaAs": ["semiconductors:InAs", "semiconductors:GaAs"], "GaInP": ["semiconductors:GaP", "semiconductors:InP"],
    "ZnCdO": ["oxides_50:ZnO@wurtzite"], "SiOx": ["oxides_50:SiO@amorphous", "oxides_50:SiO2@amorphous"],
    "KRS": ["halides:TlBr", "halides:TlCl"], "YSZ": [], "YSH": ["oxides_50:HfO2"],
    "MgO-LiNbO3": ["oxides_50:LiNbO3"], "Mg-LiTaO3": ["inorganic3:LiTaO3"], "ITO": [], "AZO": ["oxides_50:ZnO@wurtzite"],
    "AlON": [], "AgGaInS2": [], "CuZn": ["pure_elements_50:Cu@fcc", "pure_elements_50:Zn@hcp"],
    "NiFe": ["pure_elements_50:Ni@fcc", "pure_elements_50:Fe@bcc (alpha-Fe)"],
}
