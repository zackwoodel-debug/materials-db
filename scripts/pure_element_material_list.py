#!/usr/bin/env python3
"""
scripts/pure_element_material_list.py
========================================
Batch 3 canonical material list: pure elements from refractiveindex.info
(pinned commit: see src/materials_db/pipeline/refractiveindex_contract.py).
Same discipline as oxide_material_list.py / fluoride_nitride_sulfide_
material_list.py -- one shared source of identity, RI.info axis selection,
and resolved judgment calls.

STATUS: triage set only (Au, Se, Te), per the explicit instruction to
resolve triage and report BEFORE the other ~42 pure elements run. Carbon,
Tin, and Boron are deferred to batch 3b (each combines a polymorph trap
WITH a process-condition/amorphous question at once -- see
docs/batch3_scoping_report.md). The remaining ~42 "clean" elements are not
in this file yet -- they are the batch this list explicitly gates on
approval of the triage below.

Corrected corpus count (see docs/batch3_scoping_report.md Part A): 54
books / 359 pages of solid pure elements (not the recalled 59/420) after
excluding noble gases and diatomic gas elements.

Triage resolutions (the VO2/TeO2/Ta2O5 equivalents for this batch):

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
  #152) is a near-degenerate tie at only +1.08 meV/atom, the same
  wrong-one-sorts-first shape as CeF3/BN/HgS/ZnS. Density: VERIFIED
  (MP_DFT) -- "Single-crystal" is an explicit, stated bulk-sample claim,
  not an approximation.

  Te (tellurium) -- lowest-hull entry (mp-19, trigonal P3_121 #152,
  Ehull=0.00000) already matches the standard trigonal tellurium structure
  directly; pinned rather than left to coincidence. Weaker evidence than
  Se that the default dataset (Sherman and Fan 1970) is genuinely bulk/
  single-crystal -- its COMMENTS say only "Ordinary ray", not "single
  crystal" outright, though o/e notation itself requires an oriented
  anisotropic crystal, not a random/polycrystalline film. Density:
  VERIFIED (MP_DFT), with that weaker-evidence caveat recorded rather than
  silently treated as equally certain as Se's explicit statement.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from materials_db.pipeline.process_condition import format_process_condition  # noqa: E402


def _axis(page, data_path, source_label, axis=None, process_condition=None):
    return dict(page=page, data_path=data_path, source_label=source_label, axis=axis,
                process_condition=process_condition)


MATERIALS_ELEMENT_TRIAGE = [
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
# MP space-group overrides -- the EXPECTED_SPACEGROUP pattern, extended.
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
}

# formulas whose RI.info default dataset is genuinely bulk/single-crystal
# (explicitly stated, or strongly implied by an o/e polarization-resolved
# measurement, which a random/polycrystalline film cannot produce) --
# MP_DFT bulk density IS the correct, verified value for these, NOT an
# approximation. Au is deliberately absent: no gold entry states a
# measured density, and gold's default (Johnson 1972) states only "Room
# temperature" -- no deposition method, no basis to call it verified.
VERIFIED_BULK_SAMPLE_FORMULAS = {"Se", "Te"}
