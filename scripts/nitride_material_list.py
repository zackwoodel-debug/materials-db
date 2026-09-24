#!/usr/bin/env python3
"""
scripts/nitride_material_list.py
=================================
Canonical candidate list for the nitride family run (18 candidates). One shared source of identity for
match_ri_info_nitrides.py and build_nitrides_csv.py.

Five candidates (AlN, GaN, h-BN, TiN, VN) were already processed in batches 2/3b; their RI.info axis
selections were made by a human then and are CARRIED OVER from fluoride_nitride_sulfide_material_list.MATERIALS_31,
not re-picked. Si3N4 is UNRESOLVED there (amorphous vs crystalline) and stays unselected here.
"""

CANDIDATES = [
    dict(name="Aluminium nitride", formula="AlN", polymorph_hint="wurtzite", pubchem_name="Aluminum nitride", ri_aliases=["AlN"]),
    dict(name="Gallium nitride", formula="GaN", polymorph_hint="wurtzite", pubchem_name="Gallium nitride", ri_aliases=["GaN"]),
    dict(name="Indium nitride", formula="InN", polymorph_hint="wurtzite", pubchem_name="Indium nitride", ri_aliases=["InN"]),
    dict(name="Silicon nitride", formula="Si3N4", polymorph_hint="optical: amorphous film; density/SLD: calculated crystalline beta (mp-988)", pubchem_name="Silicon nitride", ri_aliases=["Si3N4", "SiN"]),
    dict(name="Boron nitride (cubic)", formula="BN", polymorph_hint="cubic (c-BN)", pubchem_name="Boron nitride",
         ri_aliases=["cBN", "c-BN"], selection_key="BN-cubic"),
    dict(name="Boron nitride (hexagonal)", formula="BN", polymorph_hint="h-BN", pubchem_name="Boron nitride",
         ri_aliases=["BN", "h-BN", "hBN"], selection_key="BN-hex"),
    dict(name="Titanium nitride", formula="TiN", polymorph_hint="rock salt", pubchem_name="Titanium nitride", ri_aliases=["TiN"]),
    dict(name="Tantalum nitride", formula="TaN", polymorph_hint=None, pubchem_name="Tantalum nitride", ri_aliases=["TaN"]),
    dict(name="Niobium nitride", formula="NbN", polymorph_hint="rock salt", pubchem_name="Niobium nitride", ri_aliases=["NbN"]),
    dict(name="Vanadium nitride", formula="VN", polymorph_hint="rock salt", pubchem_name="Vanadium nitride", ri_aliases=["VN"]),
    dict(name="Chromium nitride", formula="CrN", polymorph_hint="rock salt", pubchem_name="Chromium nitride", ri_aliases=["CrN"]),
    dict(name="Zirconium nitride", formula="ZrN", polymorph_hint="rock salt", pubchem_name="Zirconium nitride", ri_aliases=["ZrN"]),
    dict(name="Hafnium nitride", formula="HfN", polymorph_hint="rock salt", pubchem_name="Hafnium nitride", ri_aliases=["HfN"]),
    dict(name="Tungsten nitride", formula="WN", polymorph_hint=None, pubchem_name="Tungsten nitride", ri_aliases=["WN"]),
    dict(name="Molybdenum nitride", formula="MoN", polymorph_hint=None, pubchem_name="Molybdenum nitride", ri_aliases=["MoN"]),
    dict(name="Scandium nitride", formula="ScN", polymorph_hint="rock salt", pubchem_name="Scandium nitride", ri_aliases=["ScN"]),
    dict(name="Copper(I) nitride", formula="Cu3N", polymorph_hint="anti-ReO3", pubchem_name="Copper nitride", ri_aliases=["Cu3N"]),
    dict(name="Magnesium nitride", formula="Mg3N2", polymorph_hint="anti-bixbyite", pubchem_name="Magnesium nitride", ri_aliases=["Mg3N2"]),
]

for _c in CANDIDATES:
    _c.setdefault("selection_key", _c["formula"])

# candidate selection_key -> formula of the batch2 MATERIALS_31 entry whose human-made RI selection is carried over
CARRY_OVER = {"AlN": "AlN", "GaN": "GaN", "BN-hex": "BN", "TiN": "TiN", "VN": "VN"}

# Human decisions made for this run (not auto-picked). Optical is the amorphous thin film; polymorph/axis go in
# dataset_label with the same convention as the carried-over nitrides (axis segment omitted when isotropic).
USER_SELECTIONS = {
    "Si3N4": dict(
        polymorph="amorphous", axis="isotropic",
        pages=[("Luke", "Luke2015"), ("Philipp", "Philipp1973")],  # primary first
        basis=("user decision: stoichiometric amorphous thin film. RI.info's own files state only '340 nm Si3N4 on 3.1 um "
               "thermal SiO2 on silicon' (Luke) and nothing (Philipp; Baak dispersion fit to Philipp's data); "
               "'stoichiometric'/'amorphous' are not stated in the RI.info files."),
    ),
}

# RI.info pages deliberately NOT loaded: non-stoichiometric SiNx. Logged in nitride_gaps.csv; no SiNx material rows (follow-up).
EXCLUDED_DATASETS = {
    "Si3N4": [("Kischkat", "Kischkat2012"), ("Beliaev", "Beliaev2022"), ("Vogt-1.91", "Vogt2015-1"),
              ("Vogt-2.09", "Vogt2015-2"), ("Vogt-2.13", "Vogt2015-3")],
}

# Si3N4 physical properties: the crystalline beta entry on the MP hull (calculated, DFT-derived). Others ignored this run.
SI3N4_MP_ID = "mp-988"
SI3N4_PHASE_NOTE = ("optical data is amorphous thin film; density/SLD are calculated for crystalline beta (mp-988). "
                    "Not the same phase.")
