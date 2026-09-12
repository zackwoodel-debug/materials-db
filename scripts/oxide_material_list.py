#!/usr/bin/env python3
"""
scripts/oxide_material_list.py
================================
Single canonical source of the 50 oxide materials' identity (idx, name,
formula, polymorph, pubchem lookup name, RI.info search aliases).

This collapses two independent, never-reconciled lists that used to live
separately in match_ri_info_oxides.py (TARGETS) and build_oxides_csv.py
(MATERIALS) -- their polymorph fields drifted apart over the course of this
project (22 materials disagreed at one point), which caused
optical_dispersion and physical_properties to use different dataset_label
polymorph prefixes for 16 of them (e.g. BeO: physical_properties said
"wurtzite | density_MP_DFT", optical_dispersion said just "Edwards1991 |
o-ray", no prefix at all). Both steps now import MATERIALS_50 from here, so
that can't happen again.

Three materials are DELIBERATELY left with polymorph=None here even though
scripts/build_oxides_csv.py's own physical-properties selection has since
verified a specific phase for them (VO2: "M1 (insulating)", TeO2:
"paratellurite", Ta2O5: "amorphous") -- see PENDING_TRIAGE_PHYSICAL_POLYMORPH
below. The question of whether the RI.info OPTICAL measurement for each is
the SAME phase as the physical-properties pick is a claim that needs
checking per-material, not backfilled by string-matching; until that's
resolved, the optical side stays unlabeled (None) here rather than assuming
agreement. Do not add these three to MATERIALS_50's polymorph field until
that triage is explicitly resolved.
"""

MATERIALS_50 = [
    dict(idx=1, name="Aluminium oxide / sapphire", formula="Al2O3", polymorph="corundum/sapphire",
         pubchem_name="Aluminum oxide", ri_aliases=["Al2O3"]),
    dict(idx=2, name="Beryllium oxide", formula="BeO", polymorph="wurtzite",
         pubchem_name="Beryllium oxide", ri_aliases=["BeO"]),
    dict(idx=3, name="Chrysoberyl", formula="BeAl2O4", polymorph="chrysoberyl",
         pubchem_name="Beryllium aluminate", ri_aliases=["BeAl2O4"]),
    dict(idx=4, name="Beryllium hexaaluminate", formula="BeAl6O10", polymorph=None,
         pubchem_name="Beryllium hexaaluminate", ri_aliases=["BeAl6O10"]),
    dict(idx=5, name="Calcium gadolinium aluminate", formula="CaGdAlO4", polymorph="K2NiF4-type",
         pubchem_name="Calcium gadolinium aluminate", ri_aliases=["CaGdAlO4"]),
    dict(idx=6, name="Calcium yttrium aluminate", formula="CaYAlO4", polymorph="K2NiF4-type",
         pubchem_name="Calcium yttrium aluminate", ri_aliases=["CaYAlO4"]),
    dict(idx=7, name="Spinel", formula="MgAl2O4", polymorph="spinel",
         pubchem_name="Magnesium aluminate", ri_aliases=["MgAl2O4"]),
    dict(idx=8, name="Lanthanum aluminate", formula="LaAlO3", polymorph=None,
         pubchem_name="Lanthanum aluminate", ri_aliases=["LaAlO3"]),
    dict(idx=9, name="Barium borate (BBO)", formula="BaB2O4", polymorph="beta-BBO",
         pubchem_name="Barium borate", ri_aliases=["BaB2O4", "BBO"]),
    dict(idx=10, name="Bismuth triborate (BiBO)", formula="BiB3O6", polymorph="alpha-BiBO",
         pubchem_name="Bismuth borate", ri_aliases=["BiB3O6", "BiBO3"]),
    dict(idx=11, name="Lithium triborate (LBO)", formula="LiB3O5", polymorph=None,
         pubchem_name="Lithium triborate", ri_aliases=["LiB3O5", "LBO"]),
    dict(idx=12, name="Cesium lithium borate (CLBO)", formula="CsLiB6O10", polymorph=None,
         pubchem_name="Cesium lithium borate", ri_aliases=["CsLiB6O10", "CLBO"]),
    dict(idx=13, name="Lutetium aluminium borate", formula="LuAl3(BO3)4", polymorph=None,
         pubchem_name="Lutetium aluminum borate", ri_aliases=["LuAl3(BO3)4", "LuAl3B4O12"]),
    dict(idx=14, name="Calcite", formula="CaCO3", polymorph="calcite",
         pubchem_name="Calcium carbonate", ri_aliases=["CaCO3"]),
    dict(idx=15, name="Copper(II) oxide", formula="CuO", polymorph="tenorite",
         pubchem_name="Copper(II) oxide", ri_aliases=["CuO"]),
    dict(idx=16, name="Copper(I) oxide", formula="Cu2O", polymorph="cuprite",
         pubchem_name="Copper(I) oxide", ri_aliases=["Cu2O"]),
    dict(idx=17, name="Dysprosium oxide", formula="Dy2O3", polymorph="bixbyite",
         pubchem_name="Dysprosium oxide", ri_aliases=["Dy2O3"]),
    dict(idx=18, name="Hematite", formula="Fe2O3", polymorph="hematite",
         pubchem_name="Iron(III) oxide", ri_aliases=["Fe2O3"]),
    dict(idx=19, name="Magnetite", formula="Fe3O4", polymorph="magnetite",
         pubchem_name="Iron(II,III) oxide", ri_aliases=["Fe3O4"]),
    dict(idx=20, name="Germanium dioxide", formula="GeO2", polymorph=None,
         pubchem_name="Germanium dioxide", ri_aliases=["GeO2"]),
    dict(idx=21, name="Bismuth germanate", formula="Bi12GeO20", polymorph="BGO",
         pubchem_name="Bismuth germanium oxide", ri_aliases=["Bi12GeO20", "BGO"]),
    dict(idx=22, name="Lead germanate", formula="Pb5Ge3O11", polymorph=None,
         pubchem_name="Lead germanate", ri_aliases=["Pb5Ge3O11"]),
    dict(idx=23, name="Hafnium dioxide", formula="HfO2", polymorph=None,
         pubchem_name="Hafnium oxide", ri_aliases=["HfO2"]),
    dict(idx=24, name="Lithium iodate", formula="LiIO3", polymorph=None,
         pubchem_name="Lithium iodate", ri_aliases=["LiIO3"]),
    dict(idx=25, name="Lutetium oxide", formula="Lu2O3", polymorph="bixbyite",
         pubchem_name="Lutetium oxide", ri_aliases=["Lu2O3"]),
    dict(idx=26, name="LuAG", formula="Lu3Al5O12", polymorph="garnet",
         pubchem_name="Lutetium aluminum garnet", ri_aliases=["Lu3Al5O12", "LuAG"]),
    dict(idx=27, name="Magnesium oxide", formula="MgO", polymorph="rock salt",
         pubchem_name="Magnesium oxide", ri_aliases=["MgO"]),
    dict(idx=28, name="Molybdenum dioxide", formula="MoO2", polymorph=None,
         pubchem_name="Molybdenum dioxide", ri_aliases=["MoO2"]),
    dict(idx=29, name="Molybdenum trioxide", formula="MoO3", polymorph=None,
         pubchem_name="Molybdenum trioxide", ri_aliases=["MoO3"]),
    dict(idx=30, name="Calcium molybdate", formula="CaMoO4", polymorph="scheelite",
         pubchem_name="Calcium molybdate", ri_aliases=["CaMoO4"]),
    dict(idx=31, name="Lead molybdate", formula="PbMoO4", polymorph="scheelite/wulfenite",
         pubchem_name="Lead molybdate", ri_aliases=["PbMoO4"]),
    dict(idx=32, name="Strontium molybdate", formula="SrMoO4", polymorph="scheelite",
         pubchem_name="Strontium molybdate", ri_aliases=["SrMoO4"]),
    dict(idx=33, name="Niobium pentoxide", formula="Nb2O5", polymorph="amorphous",
         pubchem_name="Niobium pentoxide", ri_aliases=["Nb2O5"]),
    dict(idx=34, name="Potassium niobate", formula="KNbO3", polymorph=None,
         pubchem_name="Potassium niobate", ri_aliases=["KNbO3"]),
    dict(idx=35, name="Lithium niobate", formula="LiNbO3", polymorph=None,
         pubchem_name="Lithium niobate", ri_aliases=["LiNbO3"]),
    dict(idx=36, name="Scandium oxide", formula="Sc2O3", polymorph="bixbyite",
         pubchem_name="Scandium oxide", ri_aliases=["Sc2O3"]),
    dict(idx=37, name="Silicon monoxide", formula="SiO", polymorph="amorphous",
         pubchem_name="Silicon monoxide", ri_aliases=["SiO"]),
    dict(idx=38, name="Silicon dioxide / quartz", formula="SiO2", polymorph="amorphous",
         pubchem_name="Silicon dioxide", ri_aliases=["SiO2"]),
    dict(idx=39, name="Tantalum pentoxide", formula="Ta2O5", polymorph=None,
         pubchem_name="Tantalum pentoxide", ri_aliases=["Ta2O5"]),
    dict(idx=40, name="TGG", formula="Tb3Ga5O12", polymorph="garnet",
         pubchem_name="Terbium gallium garnet", ri_aliases=["Tb3Ga5O12", "TGG"]),
    dict(idx=41, name="Tellurium dioxide", formula="TeO2", polymorph=None,
         pubchem_name="Tellurium dioxide", ri_aliases=["TeO2"]),
    dict(idx=42, name="Titanium dioxide (rutile / anatase)", formula="TiO2", polymorph="rutile",
         pubchem_name="Titanium dioxide", ri_aliases=["TiO2"]),
    dict(idx=43, name="Barium titanate", formula="BaTiO3", polymorph=None,
         pubchem_name="Barium titanate", ri_aliases=["BaTiO3"]),
    dict(idx=44, name="Strontium titanate", formula="SrTiO3", polymorph=None,
         pubchem_name="Strontium titanate", ri_aliases=["SrTiO3"]),
    dict(idx=45, name="Vanadium dioxide", formula="VO2", polymorph=None,
         pubchem_name="Vanadium dioxide", ri_aliases=["VO2"]),
    dict(idx=46, name="Yttrium orthovanadate", formula="YVO4", polymorph="zircon",
         pubchem_name="Yttrium vanadate", ri_aliases=["YVO4"]),
    dict(idx=47, name="Tungsten trioxide", formula="WO3", polymorph=None,
         pubchem_name="Tungsten trioxide", ri_aliases=["WO3"]),
    dict(idx=48, name="Yttrium oxide", formula="Y2O3", polymorph="bixbyite",
         pubchem_name="Yttrium oxide", ri_aliases=["Y2O3"]),
    dict(idx=49, name="YAG", formula="Y3Al5O12", polymorph="garnet",
         pubchem_name="Yttrium aluminum garnet", ri_aliases=["Y3Al5O12", "YAG"]),
    dict(idx=50, name="Zinc oxide", formula="ZnO", polymorph="wurtzite",
         pubchem_name="Zinc oxide", ri_aliases=["ZnO"]),
]

# Pending optical-source triage (see conversation history / PR description):
# these 3 materials' PHYSICAL PROPERTIES polymorph has already been verified
# independently (via the MP structure pick), but whether the RI.info OPTICAL
# measurement is the same phase has not been confirmed to the same standard
# as everything else in MATERIALS_50 -- so it's kept out of the shared list
# and applied only on the physical-properties side (scripts/build_oxides_csv.py)
# until triage resolves. Do not use this to backfill optical_dispersion.
PENDING_TRIAGE_PHYSICAL_POLYMORPH = {
    "VO2": "M1 (insulating)",     # Beaini et al., 70nm film @ 25C (below the ~68C MIT) -- reads as M1, unconfirmed to canonical standard
    "TeO2": "paratellurite",       # Uchida 1971 title says "paratellurite" explicitly -- strong match, unconfirmed to canonical standard
    "Ta2O5": "amorphous",          # Bright et al. comments say "Amorphous thin film" explicitly -- strong match, unconfirmed to canonical standard
}
