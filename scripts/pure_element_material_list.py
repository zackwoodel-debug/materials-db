#!/usr/bin/env python3
"""
scripts/pure_element_material_list.py
========================================
Batch 3 canonical material list: pure elements from refractiveindex.info
(pinned commit: see src/materials_db/pipeline/refractiveindex_contract.py).
Same discipline as oxide_material_list.py / fluoride_nitride_sulfide_
material_list.py -- one shared source of identity, RI.info axis selection,
and resolved judgment calls.

STATUS: 50 of 54 solid pure-element books resolved and processed. Carbon,
Tin, and Boron remain deferred to batch 3b (each combines a polymorph trap
WITH a process-condition/amorphous question at once -- see
docs/batch3_scoping_report.md). Mercury is EXCLUDED, not deferred: its
only RI.info page (Inagaki et al. 1981) states directly "Liquid mercury at
room temperature" -- this DB is for thin-film/solid-state modeling, and Hg
is the one "pure element" in the corpus that is not a solid at all, the
same exclusion logic as the noble-gas/diatomic-gas books. 54 - 3 (C/Sn/B
deferred) - 1 (Hg excluded) = 50 processed.

Corrected corpus count (see docs/batch3_scoping_report.md Part A): 54
books / 359 pages of solid pure elements (not the recalled 59/420) after
excluding noble gases and diatomic gas elements. The "remaining ~42" figure
used when this batch was approved was also off: 54 - 3 (Au/Se/Te, resolved
first) - 3 (C/Sn/B, deferred) = 48, then - 1 (Hg, excluded here) = 47
actually processed in this pass. Corrected here, not silently used.

======================================================================
TRIAGE SET (resolved first, reported before the rest ran)
======================================================================

  Au (gold) -- the flagship process-condition validation case. Zero
  polymorph ambiguity (always fcc, MP-confirmed mp-81 Fm-3m #225,
  Ehull=0.00000) but the richest process-condition breadth in the whole
  corpus: 38 pages spanning deposition method (evaporated/single-crystal/
  template-stripped/sputtered), explicit film thickness (4nm-117nm across
  four independent papers), and measurement temperature (25/225/350 C).
  Default dataset (Johnson and Christy 1972, the classic reference) states
  only "Room temperature" -- no deposition method, no density. Density:
  BULK_ELEMENTAL_APPROXIMATION (no gold entry in the corpus states a
  measured film density at all, including the default).

  Se (selenium) -- CONFIRMED TRAP. MP's lowest-energy_above_hull entry
  (mp-570481, monoclinic P2_1/c #14, Ehull=0.00000) is NOT the standard
  trigonal "grey selenium" structure the RI.info data was measured on:
  Campel and Johnson 1969's page states "Single-crystal selenium" directly
  and reports o/e (ordinary/extraordinary) data, which requires a uniaxial
  (trigonal/hexagonal) crystal -- monoclinic is biaxial and physically
  cannot produce an o/e pair. The correct trigonal entry (mp-14, P3_121
  #152) is a near-degenerate tie at only +1.08 meV/atom. Density: VERIFIED
  (MP_DFT) -- "Single-crystal" is an explicit, stated bulk-sample claim.

  Te (tellurium) -- lowest-hull entry (mp-19, trigonal P3_121 #152,
  Ehull=0.00000) already matches the standard trigonal tellurium structure
  directly; pinned rather than left to coincidence. Density: VERIFIED
  (MP_DFT), with a recorded caveat that the bulk/single-crystal evidence
  is weaker than Se's (o/e notation implies it; the paper doesn't state it
  outright).

======================================================================
THE REMAINING 47 -- a MUCH higher trap rate than any prior batch
======================================================================

Applying the corrected triage rule (docs/PIPELINE_PRINCIPLES.md rule 1a:
search the FULL MP candidate set, treat a large energy_above_hull gap as
a signal to investigate, not grounds to trust lowest-hull OR to exclude)
found **16 of 47 elements (34%)** where MP's lowest-hull entry is NOT the
well-documented room-temperature structure. This is a real, systematic
pattern, not scattered noise: it is heavily concentrated in the ALKALI
METALS (Li, Na, K, Rb, Cs -- all 5 present in this batch, all 5 wrong at
lowest-hull) and several LANTHANIDES (Ce[correct]/Pr/Eu/Er/Lu/Yb -- 4 of 6
present here wrong at lowest-hull), plus isolated cases (Ag, Co, In, Sr,
Ta, Ti). The alkali-metal pattern has a known physical explanation: DFT
(0K, no vibrational/entropic corrections) correctly finds the
LOW-TEMPERATURE ground state, which for Li and Na specifically undergoes a
well-documented bcc -> close-packed martensitic transition below ~70-80K
-- but real optical measurements are done at or near room temperature,
where bcc is the actually-correct phase for all five alkali metals. The
lanthanide/isolated cases are individually attributed below, mostly to
known small hcp/fcc/bcc energy differences that are sensitive to magnetic
ordering and DFT exchange-correlation functional choice (the same shape
as VN's rock-salt-vs-theoretical-ground-state issue in batch 2).

Every override below states the specific alternative MP entry and the
gap, per the corrected rule -- gaps here range from 0.74 meV/atom (Lu, a
true near-degenerate tie) up to 44.81 meV/atom (Sr), an order of magnitude
larger than anything seen in the oxide or fluoride/nitride/sulfide
batches, and are recorded as such rather than smoothed over.

Density: 12 elements (Ca, Ce, Er, Eu, Ho, Lu, Mg, Pr, Sc, Sr, Tm, Yb) have
a real, stated measured film density from a single systematic EUV/VUV
thin-film optical-constant research program (Fernandez-Perea/Larruquert/
Rodriguez-de_Marcos/Vidal-Dasilva/Garcia-Cortes) -- these get
EXPERIMENTAL_DENSITY_OVERRIDE with a real citation, DENSITY_VERIFIED. 3
more (Ag, Si, Ge) have an explicit "single crystal"/crystal-orientation
statement for their default dataset -- DENSITY_VERIFIED via MP_DFT/the
bulk value being correct for a genuine single crystal, no override needed.
The remaining 32 have neither -- DENSITY_BULK_APPROXIMATION.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from materials_db.pipeline.process_condition import format_process_condition  # noqa: E402


def _axis(page, data_path, source_label, axis=None, process_condition=None):
    return dict(page=page, data_path=data_path, source_label=source_label, axis=axis,
                process_condition=process_condition)


MATERIALS_PURE_ELEMENTS = [
    # ---- Triage set (idx 200-202), resolved and reported first ----
    dict(idx=200, name="Gold", formula="Au", polymorph=None,
         pubchem_name="Gold", ri_aliases=["Au"],
         ri_axes=[_axis("Johnson", "main/Au/nk/Johnson.yml", "Johnson1972")]),
    dict(idx=201, name="Selenium", formula="Se", polymorph="trigonal",
         pubchem_name="Selenium", ri_aliases=["Se"],
         ri_axes=[_axis("Campel-o", "main/Se/nk/Campel-o.yml", "Campel1969", axis="o-ray",
                        process_condition=format_process_condition(structure="single_crystal")),
                  _axis("Campel-e", "main/Se/nk/Campel-e.yml", "Campel1969", axis="e-ray",
                        process_condition=format_process_condition(structure="single_crystal"))]),
    dict(idx=202, name="Tellurium", formula="Te", polymorph="trigonal",
         pubchem_name="Tellurium", ri_aliases=["Te"],
         ri_axes=[_axis("Sherman-o", "main/Te/nk/Sherman-o.yml", "Sherman1970", axis="o-ray"),
                  _axis("Sherman-e", "main/Te/nk/Sherman-e.yml", "Sherman1970", axis="e-ray")]),

    # ---- The remaining 47 (idx 210+), same rigor, real MP checks per element ----
    dict(idx=210, name="Silver", formula="Ag", polymorph="fcc",
         pubchem_name="Silver", ri_aliases=["Ag"],
         ri_axes=[_axis("Choi", "main/Ag/nk/Choi.yml", "Choi2023",
                        process_condition=format_process_condition(deposition="single_crystal"))]),
    dict(idx=211, name="Aluminium", formula="Al", polymorph="fcc",
         pubchem_name="Aluminum", ri_aliases=["Al"],
         ri_axes=[_axis("Hagemann", "main/Al/nk/Hagemann.yml", "Hagemann1975")]),
    dict(idx=212, name="Beryllium", formula="Be", polymorph="hcp",
         pubchem_name="Beryllium", ri_aliases=["Be"],
         ri_axes=[_axis("Svechnikov", "main/Be/nk/Svechnikov.yml", "Svechnikov1968")]),
    dict(idx=213, name="Bismuth", formula="Bi", polymorph="rhombohedral (A7)",
         pubchem_name="Bismuth", ri_aliases=["Bi"],
         ri_axes=[_axis("Hagemann", "main/Bi/nk/Hagemann.yml", "Hagemann1975")]),
    dict(idx=214, name="Calcium", formula="Ca", polymorph="fcc",
         pubchem_name="Calcium", ri_aliases=["Ca"],
         ri_axes=[_axis("Rodriguez-de_Marcos", "main/Ca/nk/Rodriguez-de Marcos.yml", "RodriguezDeMarcos2015")]),
    dict(idx=215, name="Cerium", formula="Ce", polymorph="fcc (gamma-Ce)",
         pubchem_name="Cerium", ri_aliases=["Ce"],
         ri_axes=[_axis("Fernandez-Perea", "main/Ce/nk/Fernandez-Perea.yml", "FernandezPerea2008")]),
    dict(idx=216, name="Cobalt", formula="Co", polymorph="hcp",
         pubchem_name="Cobalt", ri_aliases=["Co"],
         ri_axes=[_axis("Werner", "main/Co/nk/Werner.yml", "Werner2009")]),
    dict(idx=217, name="Chromium", formula="Cr", polymorph="bcc",
         pubchem_name="Chromium", ri_aliases=["Cr"],
         ri_axes=[_axis("Sytchkova", "main/Cr/nk/Sytchkova.yml", "Sytchkova2020",
                        process_condition=format_process_condition(deposition="sputtered", thickness="12nm"))]),
    dict(idx=218, name="Cesium", formula="Cs", polymorph="bcc",
         pubchem_name="Cesium", ri_aliases=["Cs"],
         ri_axes=[_axis("Smith", "main/Cs/nk/Smith.yml", "Smith1985")]),
    dict(idx=219, name="Copper", formula="Cu", polymorph="fcc",
         pubchem_name="Copper", ri_aliases=["Cu"],
         ri_axes=[_axis("Hagemann", "main/Cu/nk/Hagemann.yml", "Hagemann1975")]),
    dict(idx=220, name="Erbium", formula="Er", polymorph="hcp",
         pubchem_name="Erbium", ri_aliases=["Er"],
         ri_axes=[_axis("Larruquert", "main/Er/nk/Larruquert.yml", "Larruquert2011")]),
    dict(idx=221, name="Europium", formula="Eu", polymorph="bcc",
         pubchem_name="Europium", ri_aliases=["Eu"],
         ri_axes=[_axis("Fernandez-Perea", "main/Eu/nk/Fernandez-Perea.yml", "FernandezPerea2008b")]),
    dict(idx=222, name="Iron", formula="Fe", polymorph="bcc (alpha-Fe)",
         pubchem_name="Iron", ri_aliases=["Fe"],
         ri_axes=[_axis("Ordal", "main/Fe/nk/Ordal.yml", "Ordal1988")]),
    dict(idx=223, name="Germanium", formula="Ge", polymorph="diamond cubic",
         pubchem_name="Germanium", ri_aliases=["Ge"],
         ri_axes=[_axis("Aspnes", "main/Ge/nk/Aspnes.yml", "Aspnes1983",
                        process_condition=format_process_condition(deposition="single_crystal"))]),
    dict(idx=224, name="Hafnium", formula="Hf", polymorph="hcp",
         pubchem_name="Hafnium", ri_aliases=["Hf"],
         ri_axes=[_axis("Windt", "main/Hf/nk/Windt.yml", "Windt1988")]),
    dict(idx=225, name="Holmium", formula="Ho", polymorph="hcp",
         pubchem_name="Holmium", ri_aliases=["Ho"],
         ri_axes=[_axis("Fernandez-Perea", "main/Ho/nk/Fernandez-Perea.yml", "FernandezPerea2011")]),
    dict(idx=226, name="Indium", formula="In", polymorph="face-centered tetragonal",
         pubchem_name="Indium", ri_aliases=["In"],
         ri_axes=[_axis("Golovashkin-295K", "main/In/nk/Golovashkin-295K.yml", "Golovashkin1965")]),
    dict(idx=227, name="Iridium", formula="Ir", polymorph="fcc",
         pubchem_name="Iridium", ri_aliases=["Ir"],
         ri_axes=[_axis("Schmitt-ALD", "main/Ir/nk/Schmitt-ALD.yml", "Schmitt2018",
                        process_condition=format_process_condition(deposition="ALD"))]),
    dict(idx=228, name="Potassium", formula="K", polymorph="bcc",
         pubchem_name="Potassium", ri_aliases=["K"],
         ri_axes=[_axis("Althoff", "main/K/nk/Althoff.yml", "Althoff1983")]),
    dict(idx=229, name="Lithium", formula="Li", polymorph="bcc",
         pubchem_name="Lithium", ri_aliases=["Li"],
         ri_axes=[_axis("Rasigni", "main/Li/nk/Rasigni.yml", "Rasigni1977")]),
    dict(idx=230, name="Lutetium", formula="Lu", polymorph="hcp",
         pubchem_name="Lutetium", ri_aliases=["Lu"],
         ri_axes=[_axis("Garcia-Cortes", "main/Lu/nk/Garcia-Cortes.yml", "GarciaCortes2010")]),
    dict(idx=231, name="Magnesium", formula="Mg", polymorph="hcp",
         pubchem_name="Magnesium", ri_aliases=["Mg"],
         ri_axes=[_axis("Vidal-Dasilva", "main/Mg/nk/Vidal-Dasilva.yml", "VidalDasilva2010",
                        process_condition=format_process_condition(deposition="sputtered"))]),
    dict(idx=232, name="Manganese", formula="Mn", polymorph="alpha-Mn (complex cubic)",
         pubchem_name="Manganese", ri_aliases=["Mn"],
         ri_axes=[_axis("Querry", "main/Mn/nk/Querry.yml", "Querry1985")]),
    dict(idx=233, name="Molybdenum", formula="Mo", polymorph="bcc",
         pubchem_name="Molybdenum", ri_aliases=["Mo"],
         ri_axes=[_axis("Querry", "main/Mo/nk/Querry.yml", "Querry1985")]),
    dict(idx=234, name="Sodium", formula="Na", polymorph="bcc",
         pubchem_name="Sodium", ri_aliases=["Na"],
         ri_axes=[_axis("Althoff", "main/Na/nk/Althoff.yml", "Althoff1983")]),
    dict(idx=235, name="Niobium", formula="Nb", polymorph="bcc",
         pubchem_name="Niobium", ri_aliases=["Nb"],
         ri_axes=[_axis("Golovashkin-293K", "main/Nb/nk/Golovashkin-293K.yml", "Golovashkin1965b")]),
    dict(idx=236, name="Nickel", formula="Ni", polymorph="fcc",
         pubchem_name="Nickel", ri_aliases=["Ni"],
         ri_axes=[_axis("Ordal", "main/Ni/nk/Ordal.yml", "Ordal1988")]),
    dict(idx=237, name="Osmium", formula="Os", polymorph="hcp",
         pubchem_name="Osmium", ri_aliases=["Os"],
         ri_axes=[_axis("Nemoshkalenko-o", "main/Os/nk/Nemoshkalenko-o.yml", "Nemoshkalenko", axis="o-ray")]),
    dict(idx=238, name="Lead", formula="Pb", polymorph="fcc",
         pubchem_name="Lead", ri_aliases=["Pb"],
         ri_axes=[_axis("Ordal", "main/Pb/nk/Ordal.yml", "Ordal1988")]),
    dict(idx=239, name="Palladium", formula="Pd", polymorph="fcc",
         pubchem_name="Palladium", ri_aliases=["Pd"],
         ri_axes=[_axis("Werner", "main/Pd/nk/Werner.yml", "Werner2009")]),
    dict(idx=240, name="Praseodymium", formula="Pr", polymorph="dhcp",
         pubchem_name="Praseodymium", ri_aliases=["Pr"],
         ri_axes=[_axis("Fernandez-Perea", "main/Pr/nk/Fernandez-Perea.yml", "FernandezPerea2008c")]),
    dict(idx=241, name="Platinum", formula="Pt", polymorph="fcc",
         pubchem_name="Platinum", ri_aliases=["Pt"],
         ri_axes=[_axis("Werner", "main/Pt/nk/Werner.yml", "Werner2009")]),
    dict(idx=242, name="Rubidium", formula="Rb", polymorph="bcc",
         pubchem_name="Rubidium", ri_aliases=["Rb"],
         ri_axes=[_axis("Smith", "main/Rb/nk/Smith.yml", "Smith1985")]),
    dict(idx=243, name="Rhenium", formula="Re", polymorph="hcp",
         pubchem_name="Rhenium", ri_aliases=["Re"],
         ri_axes=[_axis("Windt", "main/Re/nk/Windt.yml", "Windt1988")]),
    dict(idx=244, name="Rhodium", formula="Rh", polymorph="fcc",
         pubchem_name="Rhodium", ri_aliases=["Rh"],
         ri_axes=[_axis("Weaver", "main/Rh/nk/Weaver.yml", "Weaver1976")]),
    dict(idx=245, name="Ruthenium", formula="Ru", polymorph="hcp",
         pubchem_name="Ruthenium", ri_aliases=["Ru"],
         ri_axes=[_axis("Windt", "main/Ru/nk/Windt.yml", "Windt1988b")]),
    dict(idx=246, name="Scandium", formula="Sc", polymorph="hcp",
         pubchem_name="Scandium", ri_aliases=["Sc"],
         ri_axes=[_axis("Larruquert", "main/Sc/nk/Larruquert.yml", "Larruquert2004")]),
    dict(idx=247, name="Silicon", formula="Si", polymorph="diamond cubic",
         pubchem_name="Silicon", ri_aliases=["Si"],
         ri_axes=[_axis("Aspnes", "main/Si/nk/Aspnes.yml", "Aspnes1983b",
                        process_condition=format_process_condition(deposition="single_crystal"))]),
    dict(idx=248, name="Strontium", formula="Sr", polymorph="fcc",
         pubchem_name="Strontium", ri_aliases=["Sr"],
         ri_axes=[_axis("Rodriguez-de_Marcos", "main/Sr/nk/Rodriguez-de Marcos.yml", "RodriguezDeMarcos2012")]),
    dict(idx=249, name="Tantalum", formula="Ta", polymorph="bcc",
         pubchem_name="Tantalum", ri_aliases=["Ta"],
         ri_axes=[_axis("Ordal", "main/Ta/nk/Ordal.yml", "Ordal1988")]),
    dict(idx=250, name="Titanium", formula="Ti", polymorph="hcp",
         pubchem_name="Titanium", ri_aliases=["Ti"],
         ri_axes=[_axis("Ordal", "main/Ti/nk/Ordal.yml", "Ordal1988")]),
    dict(idx=251, name="Thulium", formula="Tm", polymorph="hcp",
         pubchem_name="Thulium", ri_aliases=["Tm"],
         ri_axes=[_axis("Vidal-Dasilva", "main/Tm/nk/Vidal-Dasilva.yml", "VidalDasilva2009")]),
    dict(idx=252, name="Vanadium", formula="V", polymorph="bcc",
         pubchem_name="Vanadium", ri_aliases=["V"],
         ri_axes=[_axis("Werner", "main/V/nk/Werner.yml", "Werner2009")]),
    dict(idx=253, name="Tungsten", formula="W", polymorph="bcc",
         pubchem_name="Tungsten", ri_aliases=["W"],
         ri_axes=[_axis("Ordal", "main/W/nk/Ordal.yml", "Ordal1988")]),
    dict(idx=254, name="Ytterbium", formula="Yb", polymorph="fcc",
         pubchem_name="Ytterbium", ri_aliases=["Yb"],
         ri_axes=[_axis("Larruquert", "main/Yb/nk/Larruquert.yml", "Larruquert2003")]),
    dict(idx=255, name="Zinc", formula="Zn", polymorph="hcp",
         pubchem_name="Zinc", ri_aliases=["Zn"],
         ri_axes=[_axis("Querry", "main/Zn/nk/Querry.yml", "Querry1985b")]),
    dict(idx=256, name="Zirconium", formula="Zr", polymorph="hcp",
         pubchem_name="Zirconium", ri_aliases=["Zr"],
         ri_axes=[_axis("Querry", "main/Zr/nk/Querry.yml", "Querry1985c")]),
]

# Named alternates for gold, demonstrating process_condition against the
# richest real breadth in the corpus (not the default pick -- available
# for a caller who wants a specific condition):
AU_ALTERNATE_PAGES = [
    _axis("Olmon-ev", "main/Au/nk/Olmon-ev.yml", "Olmon2012",
          process_condition=format_process_condition(deposition="evaporated")),
    _axis("Olmon-sc", "main/Au/nk/Olmon-sc.yml", "Olmon2012",
          process_condition=format_process_condition(deposition="single_crystal")),
    _axis("Olmon-ts", "main/Au/nk/Olmon-ts.yml", "Olmon2012",
          process_condition=format_process_condition(deposition="template_stripped")),
    _axis("Magnozzi-25C", "main/Au/nk/Magnozzi-25C.yml", "Magnozzi2019",
          process_condition=format_process_condition(temperature="25C")),
    _axis("Magnozzi-225C", "main/Au/nk/Magnozzi-225C.yml", "Magnozzi2019",
          process_condition=format_process_condition(temperature="225C")),
    _axis("Magnozzi-350C", "main/Au/nk/Magnozzi-350C.yml", "Magnozzi2019",
          process_condition=format_process_condition(temperature="350C")),
    _axis("Yakubovsky-25nm", "main/Au/nk/Yakubovsky-25nm.yml", "Yakubovsky2017",
          process_condition=format_process_condition(thickness="25nm")),
    _axis("Yakubovsky-53nm", "main/Au/nk/Yakubovsky-53nm.yml", "Yakubovsky2017",
          process_condition=format_process_condition(thickness="53nm")),
    _axis("Yakubovsky-117nm", "main/Au/nk/Yakubovsky-117nm.yml", "Yakubovsky2017",
          process_condition=format_process_condition(thickness="117nm")),
]

# ---------------------------------------------------------------------------
# MP space-group overrides -- the EXPECTED_SPACEGROUP pattern, extended to
# the full 50-element pure-element set. Entries with gap=0 are defensive
# pins (already correct at lowest-hull, pinned so a future MP update can't
# silently drift them); entries with a real gap are CONFIRMED TRAPS, per
# docs/PIPELINE_PRINCIPLES.md rule 1a -- every gap stated explicitly, none
# smoothed over.
# ---------------------------------------------------------------------------

EXPECTED_SPACEGROUP = {
    "Au": ([225], "fcc -- already the lowest-hull MP match (mp-81), Ehull=0.00000. Pinned "
                   "explicitly, no polymorph ambiguity, but the richest process-condition "
                   "breadth in the corpus (see module docstring)."),
    "Se": ([152, 154], "trigonal ('grey selenium') -- CONFIRMED TRAP. MP's lowest-hull entry "
                        "(mp-570481, monoclinic P2_1/c #14, Ehull=0.00000) cannot be what the "
                        "default RI.info dataset measured: Campel and Johnson 1969 explicitly "
                        "states 'Single-crystal selenium' and reports o/e data, which requires "
                        "a UNIAXIAL crystal -- monoclinic is biaxial, physically incompatible "
                        "with an o/e pair. The correct trigonal entry (mp-14, P3_121 #152) is "
                        "a near-degenerate tie at only +1.08 meV/atom, the same wrong-one-"
                        "sorts-first shape as CeF3/BN/HgS/ZnS."),
    "Te": ([152, 154], "trigonal -- already the lowest-hull MP match (mp-19, P3_121 #152, "
                        "Ehull=0.00000). Pinned explicitly; weaker direct evidence than Se "
                        "that the default dataset is genuinely bulk/single-crystal (Sherman "
                        "and Fan 1970's COMMENTS say only 'Ordinary ray', not 'single "
                        "crystal' outright) -- o/e notation itself requires an oriented "
                        "anisotropic crystal, not a random/polycrystalline film, but this is "
                        "inferred from measurement TYPE, not an explicit sample statement."),

    "Ag": ([225], "fcc -- CONFIRMED TRAP. Lowest-hull (mp-8566, P6_3/mmc #194) is a "
                   "near-degenerate hcp polytype; the correct fcc entry (mp-124) is only "
                   "+2.13 meV/atom away. Textbook fcc silver, matches the default dataset's "
                   "explicit 'single crystalline' claim."),
    "Al": ([225], "fcc -- already the lowest-hull MP match (mp-134). Pinned defensively."),
    "Be": ([194], "hcp -- already the lowest-hull MP match (mp-87). Pinned defensively."),
    "Bi": ([166], "rhombohedral A7 -- already the lowest-hull MP match (mp-23152). Pinned defensively."),
    "Ca": ([225], "fcc -- already the lowest-hull MP match (mp-45). Pinned defensively."),
    "Ce": ([225], "fcc (gamma-Ce, the standard ambient phase) -- already the lowest-hull "
                   "MP match (mp-28). Pinned defensively; cerium has other high-pressure/"
                   "low-temperature polymorphs (alpha/beta/delta) not relevant at ambient "
                   "conditions."),
    "Co": ([194], "hcp -- CONFIRMED TRAP. Lowest-hull (mp-102, Fm-3m #225) is fcc; cobalt's "
                   "real room-temperature phase is hcp, and the hcp/fcc energy difference "
                   "for cobalt is well known to be small and magnetic-ordering-sensitive in "
                   "DFT. Correct entry (mp-1183710) is at +10.62 meV/atom."),
    "Cr": ([229], "bcc -- already the lowest-hull MP match (mp-90). Pinned defensively."),
    "Cs": ([229], "bcc -- CONFIRMED TRAP, same alkali-metal pattern as Li/Na/K/Rb. Lowest-hull "
                   "(mp-1949606, I4/mmm #139) is a low-temperature-favored tetragonal phase; "
                   "the correct bcc entry (mp-1) is at +19.34 meV/atom."),
    "Cu": ([225], "fcc -- already the lowest-hull MP match (mp-30). Pinned defensively."),
    "Er": ([194], "hcp -- CONFIRMED TRAP. Lowest-hull (mp-1184115, R-3m #166) is rhombohedral; "
                   "erbium's real room-temperature phase is hcp, standard for heavy "
                   "lanthanides. Correct entry (mp-99) is at +12.44 meV/atom."),
    "Eu": ([229], "bcc -- CONFIRMED TRAP. Lowest-hull (mp-21462, P6_3/mmc #194) is hcp; "
                   "europium is anomalous among lanthanides (divalent character, like Yb) "
                   "and its real room-temperature phase is bcc. Correct entry (mp-20071) is "
                   "at +41.44 meV/atom -- a large gap, flagged rather than smoothed over."),
    "Fe": ([229], "bcc (alpha-Fe) -- already the lowest-hull MP match (mp-13). Pinned defensively."),
    "Ge": ([227], "diamond cubic -- already the lowest-hull MP match (mp-32). Pinned defensively."),
    "Hf": ([194], "hcp -- already the lowest-hull MP match (mp-103). Pinned defensively."),
    "Ho": ([194], "hcp -- already the lowest-hull MP match (mp-144). Pinned defensively."),
    "In": ([139], "face-centered tetragonal (a slightly distorted fcc, indium's real textbook "
                   "structure) -- CONFIRMED TRAP. Lowest-hull (mp-85, Fm-3m #225) is pure "
                   "cubic fcc; the correct tetragonal entry (mp-1055994, I4/mmm #139) is at "
                   "+4.49 meV/atom."),
    "Ir": ([225], "fcc -- already the lowest-hull MP match (mp-101). Pinned defensively."),
    "K": ([229], "bcc -- CONFIRMED TRAP, alkali-metal pattern. Lowest-hull (mp-1184804, Cmce "
                  "#64) is a low-temperature-favored orthorhombic phase; the correct bcc "
                  "entry (mp-58) is at +15.21 meV/atom."),
    "Li": ([229], "bcc -- CONFIRMED TRAP. Lowest-hull (mp-1018134, R-3m #166) is the "
                   "low-temperature 9R martensitic phase lithium is well documented to adopt "
                   "below ~70-80K; real room-temperature Li is bcc. Correct entry (mp-135) "
                   "is at +9.65 meV/atom. The clearest physically-explained case in this "
                   "whole alkali-metal pattern."),
    "Lu": ([194], "hcp -- CONFIRMED TRAP, but a true near-degenerate tie (the closest gap in "
                   "this batch). Lowest-hull (mp-973571, R-3m #166) is rhombohedral; correct "
                   "hcp entry (mp-145) is at only +0.74 meV/atom."),
    "Mg": ([194], "hcp -- already the lowest-hull MP match (mp-153). Pinned defensively."),
    "Mn": ([217], "alpha-Mn (complex 58-atom cubic structure) -- already the lowest-hull MP "
                   "match (mp-35). This unusual structure is genuinely correct for manganese, "
                   "not a trap -- pinned to document that it was checked, not assumed odd."),
    "Mo": ([229], "bcc -- already the lowest-hull MP match (mp-129). Pinned defensively."),
    "Na": ([229], "bcc -- CONFIRMED TRAP, same alkali-metal pattern as Li. Lowest-hull "
                   "(mp-10172, P6_3/mmc #194) is a low-temperature-favored hcp phase; correct "
                   "bcc entry (mp-127) is at +15.77 meV/atom."),
    "Nb": ([229], "bcc -- already the lowest-hull MP match (mp-75). Pinned defensively."),
    "Ni": ([225], "fcc -- already the lowest-hull MP match (mp-23). Pinned defensively."),
    "Os": ([194], "hcp -- already the lowest-hull MP match (mp-49). Pinned defensively."),
    "Pb": ([225], "fcc -- already the lowest-hull MP match (mp-20483). Pinned defensively."),
    "Pd": ([225], "fcc -- already the lowest-hull MP match (mp-2). Pinned defensively."),
    "Pr": ([194], "dhcp (double-hcp, praseodymium's real room-temperature phase) -- CONFIRMED "
                   "TRAP, but only partially resolvable by this mechanism: dhcp and simple hcp "
                   "share the SAME space-group NUMBER (194) with a different unit-cell "
                   "multiplicity (Z=4 vs Z=2), which an override keyed on space-group number "
                   "alone cannot distinguish. Lowest-hull (mp-97, Fm-3m #225, fcc) is wrong "
                   "regardless -- fcc gamma-Pr only exists at high pressure. Picked mp-38 "
                   "(#194, +14.57 meV/atom from a differently-referenced hull) as the correct "
                   "structural FAMILY; flagged as not fully resolved at the Z-multiplicity "
                   "level, a genuine limitation of this override mechanism, not asserted as "
                   "fully verified."),
    "Pt": ([225], "fcc -- already the lowest-hull MP match (mp-126). Pinned defensively."),
    "Rb": ([229], "bcc -- CONFIRMED TRAP, alkali-metal pattern. Lowest-hull (mp-1179656, C2/c "
                   "#15) is a low-temperature-favored monoclinic phase; correct bcc entry "
                   "(mp-70) is at +9.21 meV/atom."),
    "Re": ([194], "hcp -- already the lowest-hull MP match (mp-1186901). Pinned defensively."),
    "Rh": ([225], "fcc -- already the lowest-hull MP match (mp-74). Pinned defensively."),
    "Ru": ([194], "hcp -- already the lowest-hull MP match (mp-33). Pinned defensively."),
    "Sc": ([194], "hcp -- already the lowest-hull MP match (mp-67). Pinned defensively."),
    "Si": ([227], "diamond cubic -- already the lowest-hull MP match (mp-149). Pinned defensively."),
    "Sr": ([225], "fcc -- CONFIRMED TRAP, the largest gap in this batch besides Eu. Lowest-hull "
                   "(mp-139, P6_3/mmc #194) is hcp, which is strontium's correct HIGH-"
                   "temperature phase (above ~215C) -- real room-temperature Sr is fcc. "
                   "Correct entry (mp-76) is at +44.81 meV/atom, flagged explicitly rather "
                   "than smoothed over."),
    "Ta": ([229], "bcc -- CONFIRMED TRAP. Lowest-hull (mp-569794, P4_2/mnm #136) is a distorted "
                   "tetragonal beta-Ta-like structure; real room-temperature Ta is bcc "
                   "(alpha-Ta). Correct entry (mp-50) is at +9.15 meV/atom."),
    "Ti": ([194], "hcp -- CONFIRMED TRAP. Lowest-hull (mp-72, P6/mmm #191) lacks the "
                   "characteristic c-glide/screw-axis stacking of real hcp titanium. Correct "
                   "entry (mp-46, #194) is at +15.17 meV/atom."),
    "Tm": ([194], "hcp -- already the lowest-hull MP match (mp-143). Pinned defensively."),
    "V": ([229], "bcc -- already the lowest-hull MP match (mp-146). Pinned defensively."),
    "W": ([229], "bcc -- already the lowest-hull MP match (mp-91). Pinned defensively."),
    "Yb": ([225], "fcc -- CONFIRMED case, but NOT resolvable via energy_above_hull at all: MP "
                   "reports Ehull=None for every single Yb entry (likely an f-electron "
                   "DFT+U data-availability gap for this element specifically) -- a third, "
                   "distinct resolution shape from both the near-degenerate-tie and "
                   "large-gap cases above. Picked mp-162 (Fm-3m #225) from known "
                   "crystallography (ytterbium is anomalous among lanthanides, divalent "
                   "character like Eu, and its real room-temperature phase is fcc), not from "
                   "a hull comparison that doesn't exist for this element."),
    "Zn": ([194], "hcp -- already the lowest-hull MP match (mp-79). Pinned defensively."),
    "Zr": ([194], "hcp -- already the lowest-hull MP match (mp-131). Pinned defensively."),
}

# ---------------------------------------------------------------------------
# Density: 12 elements with a real stated measured film density (a single
# systematic EUV/VUV research program), replacing MP_DFT with the cited
# experimental value -- DENSITY_VERIFIED via a real citation, same
# EXPERIMENTAL_DENSITY_OVERRIDE mechanism as the oxide batch's CaGdAlO4.
# ---------------------------------------------------------------------------

EXPERIMENTAL_DENSITY_OVERRIDE = {
    "Ca": (1.55, "literature: Ca film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1364/AO.54.001910",
                title="Transmittance and optical constants of Ca films in the 4-1000 eV spectral range",
                authors="Rodriguez-de Marcos, L.; Larruquert, J.I.; Vidal-Dasilva, M.; Aznarez, J.A.; et al.",
                journal="Applied Optics", year=2015)),
    "Ce": (6.771, "literature: Ce film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.2901137",
                title="Transmittance and optical constants of Ce films in the 6-1200eV spectral range",
                authors="Fernandez-Perea, M.; Aznarez, J.A.; Larruquert, J.I.; et al.",
                journal="Journal of Applied Physics", year=2008)),
    "Er": (9.066, "literature: Er film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1364/AO.50.002211",
                title="Transmittance and optical constants of erbium films in the 3.25-1580 eV spectral range",
                authors="Larruquert, J.I.; Frassetto, F.; Garcia-Cortes, S.; Vidal-Dasilva, M.; et al.",
                journal="Applied Optics", year=2011)),
    "Eu": (5.25, "literature: Eu film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.2982391",
                title="Transmittance and optical constants of Eu films from 8.3 to 1400 eV",
                authors="Fernandez-Perea, M.; Vidal-Dasilva, M.; Aznarez, J.A.; et al.",
                journal="Journal of Applied Physics", year=2008)),
    "Ho": (8.33, "literature: Ho film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.3556451",
                title="Transmittance and optical constants of Ho films in the 3-1340 eV spectral range",
                authors="Fernandez-Perea, M.; Larruquert, J.I.; Aznarez, J.A.; et al.",
                journal="Journal of Applied Physics", year=2011)),
    "Lu": (9.84, "literature: Lu film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.3481062",
                title="Transmittance and optical constants of Lu films in the 3-1800 eV spectral range",
                authors="Garcia-Cortes, S.; Rodriguez-de Marcos, L.; Larruquert, J.I.; et al.",
                journal="Journal of Applied Physics", year=2010)),
    "Mg": (1.738, "literature: Mg film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.3481457",
                title="Optical constants of magnetron-sputtered magnesium films in the 25-1300 eV energy range",
                authors="Vidal-Dasilva, M.; Aquila, A.L.; Gullikson, E.M.; Salmassi, F.; Larruquert, J.I.",
                journal="Journal of Applied Physics", year=2010)),
    "Pr": (6.773, "literature: Pr film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.2939269",
                title="Transmittance and optical constants of Pr films in the 4-1600 eV spectral range",
                authors="Fernandez-Perea, M.; Vidal-Dasilva, M.; Aznarez, J.A.; et al.",
                journal="Journal of Applied Physics", year=2008)),
    "Sc": (2.84, "literature: Sc film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1364/AO.43.003271",
                title="Optical properties of scandium films in the far and the extreme ultraviolet",
                authors="Larruquert, J.I.; Aznarez, J.A.; Mendez, J.A.; Malvezzi, A.M.; Poletto, L.; Covini, S.",
                journal="Applied Optics", year=2004)),
    "Sr": (2.58, "literature: Sr film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.4729487",
                title="Transmittance and optical constants of Sr films in the 6-1220 eV spectral range",
                authors="Rodriguez-de Marcos, L.; Larruquert, J.I.; Aznarez, J.A.; et al.",
                journal="Journal of Applied Physics", year=2012)),
    "Tm": (9.33, "literature: Tm film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1063/1.3129507",
                title="Transmittance and optical constants of Tm films in the 2.75-1600 eV spectral range",
                authors="Vidal-Dasilva, M.; Fernandez-Perea, M.; Aznarez, J.A.; et al.",
                journal="Journal of Applied Physics", year=2009)),
    "Yb": (6.81, "literature: Yb film, density stated directly in RI.info's COMMENTS field.",
           dict(doi="10.1364/AO.42.004566",
                title="Optical properties of ytterbium films in the far and the extreme ultraviolet",
                authors="Larruquert, J.I.; Aznarez, J.A.; Mendez, J.A.; Calvo-Angos, J.",
                journal="Applied Optics", year=2003)),
}

# formulas whose RI.info default dataset is genuinely bulk/single-crystal
# (explicitly stated, or strongly implied by an o/e polarization-resolved
# measurement, which a random/polycrystalline film cannot produce) --
# MP_DFT bulk density IS the correct, verified value for these, NOT an
# approximation.
VERIFIED_BULK_SAMPLE_FORMULAS = {
    "Se", "Te",  # triage set: o/e (Se explicit "single-crystal"; Te inferred)
    "Ag",  # "Epitaxially grown, atomically smooth, single crystalline thick Ag film"
    "Si",  # Aspnes and Studna: "Crystal orientation: <111>" -- a bulk single-crystal wafer
    "Ge",  # Aspnes and Studna: "Crystal orientation: <111>" -- a bulk single-crystal wafer
    "C",  # batch 3b: BOTH C materials are genuinely bulk/single-crystal defaults --
          # Diamond's Taylor page states "Single-crystal CVD" directly; Graphite's
          # Djurisic o/e pair requires a uniaxial (oriented) crystal, same o/e logic
          # as Se/Te. Applies to both rows sharing this formula; Graphite additionally
          # gets a name-keyed EXPERIMENTAL_DENSITY_OVERRIDE below since its MP_DFT
          # value (1.939 g/cm3) diverges ~14% from real crystalline graphite.
}

# =============================================================================
# BATCH 3b: Carbon, Tin, Boron -- held back from the main pass because each
# combines a polymorph trap WITH a process-condition/amorphous question at
# once. See docs/batch3_scoping_report.md Part H for the full resolution
# writeup; summarized here as the code comments justifying each choice.
#
# Carbon needs TWO separate `materials` rows sharing formula "C" (Diamond,
# Graphite) -- genuinely different allotropes, not "the same material, pick
# one". This requires _find_material() to raise on formula ambiguity
# (fixed, src/materials_db/export/modalfit.py) and EXPECTED_SPACEGROUP to
# support a name-keyed lookup alongside the formula-keyed one (fixed,
# scripts/build_oxides_csv.py's fetch_mp()) -- both were real gaps this
# batch exposed, not pre-existing machinery.
#
# A THIRD root cause for a large energy_above_hull gap, distinct from both
# rule 1a's DFT-functional-sensitivity cases (VN, Co, Ag, Sr, Ti, In, Ta)
# and rule 1b's genuine-low-temperature-phase cases (the alkali metals):
# KINETIC METASTABILITY. Diamond (Fd-3m #227, mp-66, +112.26 meV/atom) is
# NOT a DFT error and NOT a temperature-driven phase mismatch -- graphite
# genuinely is more thermodynamically stable at all normal conditions, a
# well-known fact, and DFT correctly says so. Diamond persists at room
# temperature only because the diamond-to-graphite transformation has an
# enormous kinetic barrier, not because it's the ground state. The
# measured material is still diamond -- multiple RI.info pages explicitly
# say so -- kinetic stability is a completely legitimate reason to trust a
# phase MP ranks far from the hull, but it is a DIFFERENT reason than "the
# gap reflects a DFT/functional artifact" and should not be filed as one.
# Tin's beta phase (see below) is the same root cause.
# =============================================================================

MATERIALS_PURE_ELEMENTS += [
    dict(idx=260, name="Diamond", formula="C", polymorph="diamond cubic",
         pubchem_name="Diamond", ri_aliases=["C"],
         ri_axes=[_axis("Taylor", "main/C/nk/Taylor.yml", "Taylor2023",
                        process_condition=format_process_condition(deposition="single_crystal"))]),
    dict(idx=261, name="Graphite", formula="C", polymorph="graphite",
         pubchem_name="Graphite", ri_aliases=["C"],
         ri_axes=[_axis("Djurisic-o", "main/C/nk/Djurisic-o.yml", "Djurisic1999", axis="o-ray"),
                  _axis("Djurisic-e", "main/C/nk/Djurisic-e.yml", "Djurisic1999", axis="e-ray")]),
    dict(idx=262, name="Tin", formula="Sn", polymorph="beta-Sn (tetragonal)",
         pubchem_name="Tin", ri_aliases=["Sn"],
         ri_axes=[_axis("Golovashkin-293K", "main/Sn/nk/Golovashkin-293K.yml", "Golovashkin1964",
                        process_condition=format_process_condition(temperature="293K"))]),
    dict(idx=263, name="Boron", formula="B", polymorph="amorphous",
         pubchem_name="Boron", ri_aliases=["B"],
         ri_axes=[_axis("Fernandez-Perea", "main/B/nk/Fernandez-Perea.yml", "FernandezPerea2007",
                        process_condition=format_process_condition(deposition="evaporated"))]),
]

# Named alternates, demonstrating the corpus's real breadth without being
# the default pick:
C_ALTERNATE_PAGES = [
    _axis("Phillip", "main/C/nk/Phillip.yml", "Phillip1964"),  # diamond, no stated condition
    _axis("Dore", "main/C/nk/Dore.yml", "Dore1998",
          process_condition=format_process_condition(structure="polycrystalline")),  # CVD diamond
]
SN_ALTERNATE_PAGES = [
    _axis("Golovashkin-78K", "main/Sn/nk/Golovashkin-78K.yml", "Golovashkin1964",
          process_condition=format_process_condition(temperature="78K")),
    _axis("Golovashkin-4.2K", "main/Sn/nk/Golovashkin-4.2K.yml", "Golovashkin1964",
          process_condition=format_process_condition(temperature="4.2K")),
]

EXPERIMENTAL_DENSITY_OVERRIDE.update({
    # Name-keyed (fetch_mp() now checks name before formula for this dict
    # too -- build_oxides_csv.py): applying this via formula "C" would
    # incorrectly also override Diamond's already-correct MP_DFT density.
    "Graphite": (2.267, "literature: MP_DFT's graphite density (1.939 g/cm3, mp-48) deviates "
                         "~14% from the well-established theoretical density of ideal "
                         "AB-stacked hexagonal graphite (a=2.464 A, c=6.711 A), computed here "
                         "as 2.267 g/cm3 -- a real, checkable discrepancy per the density-"
                         "crosscheck discipline (docs/PIPELINE_PRINCIPLES.md), not smoothed "
                         "over as 'close enough'.",
                 dict(doi="10.1103/PhysRevB.71.205214",
                      title="First-principles determination of the structural, vibrational and "
                             "thermodynamic properties of diamond, graphite, and derivatives",
                      authors="Mounet, N.; Marzari, N.",
                      journal="Physical Review B", year=2005)),
})

EXPECTED_SPACEGROUP.update({
    # Name-keyed (fetch_mp() checks name before formula -- see
    # build_oxides_csv.py): "C" alone is ambiguous between these two.
    "Diamond": ([227], "diamond cubic -- CONFIRMED, at a KINETIC-METASTABILITY gap (mp-66, "
                        "+112.26 meV/atom), not a DFT error: graphite genuinely is more stable "
                        "at all normal conditions, but the diamond-to-graphite transformation "
                        "has an enormous kinetic barrier, so diamond persists indefinitely at "
                        "room temperature. Multiple RI.info pages explicitly state 'Diamond' or "
                        "'Single-crystal CVD' -- the measured material is not in question, only "
                        "why MP ranks it far from the hull."),
    "Graphite": ([194], "hexagonal graphite (AB-stacked) -- lowest-hull entry (mp-3347313, "
                         "C2/m #12) is a closely related rhombohedral/monoclinic stacking "
                         "variant at only +0.79 meV/atom above the correct hexagonal entry "
                         "(mp-48) -- a genuine near-degenerate stacking-polytype tie, the SAME "
                         "shape as h-BN/ZnS's stacking-polytype zoos, not the kinetic-"
                         "metastability shape diamond has. Djurisic and Li 1999's o/e data "
                         "requires a uniaxial hexagonal crystal, matching P6_3/mmc directly."),
    "Sn": ([141], "beta-Sn (white tin, tetragonal I4_1/amd) -- CONFIRMED at the LARGEST "
                   "kinetic-metastability gap found in this whole project after diamond "
                   "(mp-84, +120.18 meV/atom above alpha-Sn's diamond-cubic ground state, "
                   "mp-117). This is the textbook 'tin pest' transition (13.2 C, alpha stable "
                   "below, beta above) -- but unlike the alkali metals (rule 1b), where the "
                   "low-temperature phase transition genuinely occurs on ordinary cooling, tin "
                   "pest is famously KINETICALLY HINDERED without deliberate seeding or "
                   "prolonged cold exposure (historically took YEARS to manifest in affected "
                   "artifacts). Golovashkin and Motulevich 1964 measured the SAME sample's "
                   "temperature-dependent optical constants at 293/78/4.2 K -- almost certainly "
                   "all beta-Sn throughout (a metal cooled in a cryostat for an optics "
                   "measurement, not deliberately held for the tin-pest transformation to "
                   "occur), NOT a genuine phase change partway through the series. This is an "
                   "ASSUMPTION based on well-documented metallurgical kinetics, not a "
                   "certainty -- recorded as such, not silently treated as equally solid as a "
                   "directly-stated phase."),
})

# Boron: no MP structure used at all -- the RI.info-stated film density
# (2.10 g/cm3) is BELOW every crystalline boron candidate MP offers
# (2.30-2.57 g/cm3 across multiple genuine rhombohedral/tetragonal boron
# allotropes), consistent with amorphous boron -- the well-known typical
# state of a room-temperature-evaporated boron film, since boron is
# notoriously difficult to crystallize without high-temperature annealing.
# Density is VERIFIED via the RI.info-stated value itself (a real
# measured film density, same evidentiary bar as the 12 lanthanide/
# alkaline-earth elements' EXPERIMENTAL_DENSITY_OVERRIDE entries).
FORCE_NO_MP_BATCH_3B = {"B"}
LITERATURE_DENSITY_BATCH_3B = {
    "B": (2.10,
          "literature: B film, density stated directly in RI.info's COMMENTS field, below "
          "every crystalline boron candidate -- consistent with amorphous boron.",
          dict(doi="10.1364/JOSAA.24.003800",
               title="Optical constants of electron-beam evaporated boron films in the "
                      "6.8-900eV photon energy range",
               authors="Fernandez-Perea, M.; Larruquert, J.I.; Aznarez, J.A.; et al.",
               journal="Journal of the Optical Society of America A", year=2007)),
}
