#!/usr/bin/env python3
"""
scripts/fluoride_nitride_sulfide_material_list.py
====================================================
Batch 2 canonical material list: fluorides, nitrides, and binary-ish
sulfides from refractiveindex.info (pinned commit: see
src/materials_db/pipeline/refractiveindex_contract.py). Same discipline as
scripts/oxide_material_list.py -- one shared source of identity, RI.info
axis selection, and resolved judgment calls, imported by every downstream
script (build_batch2_csv.py, load_batch2_db.py, modalfit.py) so nothing
drifts or gets re-derived.

CORRECTION TO docs/batch2_scoping_report.md: that report counted 38
candidates (18 fluorides / 6 nitrides / 14 sulfides). Re-walking the pinned
catalog while assembling this list found the sulfide count was wrong -- the
actual binary-ish-sulfide set (after excluding TMDCs, ternary chalcopyrites,
CS2/SF6 gases, the CaSO4 sulfate, and the PBS buffer-solution misparse) is
8 books, not 14: As2S3, CdS, EuS, GaS, GeS2, HgS, PbS, ZnS. Verified against
the catalog directly (grep for "ulf" in BOOK/name fields under main+other),
not re-trusted from the earlier count. Corrected total: 18 + 6 + 8 = 32,
not 38.

Of those 32:
  - GdF3            -> NAMED EXCLUSION (terminal, see EXCLUSION_STATE)
  - Si3N4           -> UNRESOLVED (actionable, see EXCLUSION_STATE)
  - TiN, VN, EuS    -> DEFERRED (see EXCLUSION_STATE)
  - the other 28    -> MATERIALS_28 below, bulk-processed

A NEW trap surfaced beyond the original 8-material triage list while
assembling MATERIALS_28: HgS. The scoping report treated it as "confirmed
fine" from RI.info's page name alone ("Bond et al. 1967: α-HgS"). Cross-
checking that against Materials Project (the same discipline applied to
every polymorph pick in the oxide batch) found the lowest-energy_above_hull
MP entry is F-43m #216 (metacinnabar, the WRONG polymorph) -- the correct
trigonal cinnabar structure (P3_121 #152) is a distinct, ICSD-backed entry
further from the hull. Same TiO2-style shape as CeF3/BN. See
EXPECTED_SPACEGROUP below. This is exactly the kind of failure mode the
triage-before-bulk ordering was meant to catch -- found here, on this one
material, not silently reproduced across the rest of the batch.
"""

# ---------------------------------------------------------------------------
# Exclusion states -- three DISTINCT, queryable outcomes, not one "skipped"
# bucket. Each carries what's actually blocking it and who owns unblocking
# it, so a later batch can find its work automatically instead of
# rediscovering it from scratch.
# ---------------------------------------------------------------------------

NAMED_EXCLUSION = "named_exclusion"  # terminal: no correct structure, no alternative
UNRESOLVED = "unresolved"            # actionable now: a source read would settle it
DEFERRED = "deferred"                # blocked on machinery that doesn't exist yet

EXCLUSION_STATE = {
    "GdF3": dict(
        state=NAMED_EXCLUSION,
        reason=(
            "MP's only entry (mp-972965, Fm-3m #225) is theoretical=True with no ICSD "
            "backing (confirmed via MP provenance API) and does not match GdF3's "
            "documented room-temperature structure (orthorhombic Pnma, beta-YF3-type -- "
            "same structural family as YbF3, which correctly matches in this batch's own "
            "MP spot-check). No alternative MP entry exists to fall back to (worse than "
            "CeF3/BN, same shape as BeAl6O10 and LuAl3(BO3)4 in the oxide batch). "
            "Timeboxed per instruction: no cleanly citable primary source for an "
            "experimental lattice-parameter density was found within the allotted effort."
        ),
        blocking_on=None,  # terminal -- nothing will unblock this without new primary evidence
    ),
    "Si3N4": dict(
        state=UNRESOLVED,
        reason=(
            "Amorphous-vs-crystalline is not settled. RI.info's own COMMENTS/REFERENCES "
            "for both candidate datasets (Philipp 1973, Luke 2015) don't state either way, "
            "unlike Ta2O5's explicit 'Amorphous thin film' COMMENTS. Philipp 1973's freely "
            "accessible abstract (IOPscience) describes the deposition method (SiH4+NH3 "
            "pyrolysis) but not crystallinity. MP has two near-degenerate crystalline "
            "polymorphs (beta P6_3/m #176 at the hull, alpha P31c #159 at +3.54 meV/atom) "
            "that only matter if the optical data is actually crystalline -- unconfirmed."
        ),
        blocking_on="si3n4_amorphous_vs_crystalline_source_read",
    ),
    "TiN": dict(
        state=DEFERRED,
        reason=(
            "No bulk single-crystal reference dataset in RI.info at all -- every entry is "
            "a thin film distinguished by deposition method (sputtering vs. ALD) or anneal "
            "temperature (700/800/900 C), not crystal phase. Rock-salt structure isn't in "
            "question; what's missing is a descriptor for the axis that actually varies "
            "(process condition), which the polymorph field is the wrong shape for."
        ),
        blocking_on="process_condition_field",
    ),
    "VN": dict(
        state=DEFERRED,
        reason="Same shape as TiN -- deposition-method/anneal-only entries, no bulk "
               "single-crystal reference, rock-salt structure not in question.",
        blocking_on="process_condition_field",
    ),
    "EuS": dict(
        state=DEFERRED,
        reason="Same shape as TiN/VN -- deposition-method-only entries, no bulk "
               "single-crystal reference, rock-salt structure not in question.",
        blocking_on="process_condition_field",
    ),
}


def materials_blocked_on(blocking_field: str) -> list:
    """Query: 'what's waiting on <blocking_field>?' -- e.g.
    materials_blocked_on('process_condition_field') returns ['TiN', 'VN', 'EuS'],
    so the batch that builds that field can pick them up automatically instead
    of rediscovering them. Returns [] for a field nothing is blocked on."""
    return sorted(f for f, v in EXCLUSION_STATE.items() if v["blocking_on"] == blocking_field)


def materials_in_state(state: str) -> list:
    """Query all materials currently in a given exclusion state
    (NAMED_EXCLUSION / UNRESOLVED / DEFERRED)."""
    return sorted(f for f, v in EXCLUSION_STATE.items() if v["state"] == state)


# ---------------------------------------------------------------------------
# MATERIALS_28 -- the bulk-processable set (32 candidates minus the 4 in
# EXCLUSION_STATE that aren't NAMED_EXCLUSION; GdF3 IS included here since a
# named exclusion still gets processed through the normal pipeline with its
# density deliberately forced to None, same treatment as LuAl3(BO3)4 in the
# oxide batch -- Si3N4/TiN/VN/EuS are NOT included, since UNRESOLVED/DEFERRED
# means "not ready to process", not "process with a placeholder".)
#
# ri_axes entries use the exact dataset_label axis-vocabulary modalfit.py's
# _resolve_optical_axis already recognizes: "o-ray"/"e-ray" (uniaxial),
# "alpha-axis"/"beta-axis"/"gamma-axis" (biaxial), or no suffix (isotropic/
# single dataset). Author+year source labels use the "AuthorYYYY" form
# established by the oxide batch (e.g. "Malitson1964").
# ---------------------------------------------------------------------------

def _axis(page, data_path, source_label, axis=None):
    return dict(page=page, data_path=data_path, source_label=source_label, axis=axis)


MATERIALS_28 = [
    # ---- Fluorides (16 processable; CeF3 has an MP override, GdF3 excluded
    # separately below but still enrichment-processed) ----
    dict(idx=51, name="Barium fluoride", formula="BaF2", polymorph=None,
         pubchem_name="Barium fluoride", ri_aliases=["BaF2"],
         ri_axes=[_axis("Malitson", "main/BaF2/nk/Malitson.yml", "Malitson1964")]),
    dict(idx=52, name="Calcium fluoride", formula="CaF2", polymorph=None,
         pubchem_name="Calcium fluoride", ri_aliases=["CaF2"],
         ri_axes=[_axis("Malitson", "main/CaF2/nk/Malitson.yml", "Malitson1963")]),
    dict(idx=53, name="Cadmium fluoride", formula="CdF2", polymorph=None,
         pubchem_name="Cadmium fluoride", ri_aliases=["CdF2"],
         ri_axes=[_axis("Bosomworth-300K", "main/CdF2/nk/Bosomworth-300K.yml", "Bosomworth1967")]),
    dict(idx=54, name="Cerium(III) fluoride", formula="CeF3", polymorph="tysonite",
         pubchem_name="Cerium(III) fluoride", ri_aliases=["CeF3"],
         ri_axes=[_axis("Rodriguez-de_Marcos", "main/CeF3/nk/Rodriguez-de Marcos.yml", "RodriguezDeMarcos2017")]),
    dict(idx=55, name="Cesium fluoride", formula="CsF", polymorph=None,
         pubchem_name="Cesium fluoride", ri_aliases=["CsF"],
         ri_axes=[_axis("Li", "main/CsF/nk/Li.yml", "Li1976")]),
    dict(idx=56, name="Gadolinium(III) fluoride", formula="GdF3", polymorph=None,
         pubchem_name="Gadolinium fluoride", ri_aliases=["GdF3"],
         ri_axes=[_axis("Franta", "main/GdF3/nk/Franta.yml", "Franta2023")]),
    dict(idx=57, name="Potassium fluoride", formula="KF", polymorph=None,
         pubchem_name="Potassium fluoride", ri_aliases=["KF"],
         ri_axes=[_axis("Li", "main/KF/nk/Li.yml", "Li1976")]),
    dict(idx=58, name="Lanthanum fluoride", formula="LaF3", polymorph="tysonite",
         pubchem_name="Lanthanum fluoride", ri_aliases=["LaF3"],
         ri_axes=[_axis("Laihoa-o", "main/LaF3/nk/Laihoa-o.yml", "Laihoa1983", axis="o-ray"),
                  _axis("Laihoa-e", "main/LaF3/nk/Laihoa-e.yml", "Laihoa1983", axis="e-ray")]),
    dict(idx=59, name="Lithium calcium aluminum fluoride (LiCAF)", formula="LiCaAlF6", polymorph="colquiriite",
         pubchem_name="Lithium calcium aluminum fluoride", ri_aliases=["LiCaAlF6", "LiCAF"],
         ri_axes=[_axis("Woods-o", "main/LiCaAlF6/nk/Woods-o.yml", "Woods1991", axis="o-ray"),
                  _axis("Woods-e", "main/LiCaAlF6/nk/Woods-e.yml", "Woods1991", axis="e-ray")]),
    dict(idx=60, name="Lithium fluoride", formula="LiF", polymorph=None,
         pubchem_name="Lithium fluoride", ri_aliases=["LiF"],
         ri_axes=[_axis("Li", "main/LiF/nk/Li.yml", "Li1976")]),
    dict(idx=61, name="Magnesium fluoride", formula="MgF2", polymorph="rutile",
         pubchem_name="Magnesium fluoride", ri_aliases=["MgF2"],
         ri_axes=[_axis("Li-o", "main/MgF2/nk/Li-o.yml", "Li1980", axis="o-ray"),
                  _axis("Li-e", "main/MgF2/nk/Li-e.yml", "Li1980", axis="e-ray")]),
    dict(idx=62, name="Sodium fluoride", formula="NaF", polymorph=None,
         pubchem_name="Sodium fluoride", ri_aliases=["NaF"],
         ri_axes=[_axis("Li", "main/NaF/nk/Li.yml", "Li1976")]),
    dict(idx=63, name="Lead(II) fluoride", formula="PbF2", polymorph=None,
         pubchem_name="Lead(II) fluoride", ri_aliases=["PbF2"],
         ri_axes=[_axis("Malitson", "main/PbF2/nk/Malitson.yml", "Malitson1969")]),
    dict(idx=64, name="Rubidium fluoride", formula="RbF", polymorph=None,
         pubchem_name="Rubidium fluoride", ri_aliases=["RbF"],
         ri_axes=[_axis("Li", "main/RbF/nk/Li.yml", "Li1976")]),
    dict(idx=65, name="Strontium fluoride", formula="SrF2", polymorph=None,
         pubchem_name="Strontium fluoride", ri_aliases=["SrF2"],
         ri_axes=[_axis("Li", "main/SrF2/nk/Li.yml", "Li1980")]),
    dict(idx=66, name="Thorium(IV) fluoride", formula="ThF4", polymorph=None,
         pubchem_name="Thorium(IV) fluoride", ri_aliases=["ThF4"],
         ri_axes=[_axis("Heitmann", "main/ThF4/nk/Heitmann.yml", "Heitmann1976")]),
    dict(idx=67, name="Yttrium lithium fluoride (YLF)", formula="YLiF4", polymorph="scheelite",
         pubchem_name="Yttrium lithium fluoride", ri_aliases=["YLiF4", "YLF"],
         ri_axes=[_axis("Barnes-o", "main/YLiF4/nk/Barnes-o.yml", "Barnes1980", axis="o-ray"),
                  _axis("Barnes-e", "main/YLiF4/nk/Barnes-e.yml", "Barnes1980", axis="e-ray")]),
    dict(idx=68, name="Ytterbium(III) fluoride", formula="YbF3", polymorph="YF3-type",
         pubchem_name="Ytterbium(III) fluoride", ri_aliases=["YbF3"],
         ri_axes=[_axis("Amotchkina", "main/YbF3/nk/Amotchkina.yml", "Amotchkina2020")]),

    # ---- Nitrides (3 processable; Si3N4/TiN/VN excluded, see EXCLUSION_STATE) ----
    dict(idx=69, name="Aluminium nitride", formula="AlN", polymorph="wurtzite",
         pubchem_name="Aluminum nitride", ri_aliases=["AlN"],
         ri_axes=[_axis("Pastrnak-o", "main/AlN/nk/Pastrnak-o.yml", "Pastrnak1966", axis="o-ray"),
                  _axis("Pastrnak-e", "main/AlN/nk/Pastrnak-e.yml", "Pastrnak1966", axis="e-ray")]),
    dict(idx=70, name="Boron nitride (hexagonal)", formula="BN", polymorph="h-BN",
         pubchem_name="Boron nitride", ri_aliases=["BN", "h-BN"],
         ri_axes=[_axis("Zotev-o", "main/BN/nk/Zotev-o.yml", "Zotev2023", axis="o-ray"),
                  _axis("Zotev-e", "main/BN/nk/Zotev-e.yml", "Zotev2023", axis="e-ray")]),
    dict(idx=71, name="Gallium nitride", formula="GaN", polymorph="wurtzite",
         pubchem_name="Gallium nitride", ri_aliases=["GaN"],
         ri_axes=[_axis("Barker-o", "main/GaN/nk/Barker-o.yml", "Barker1973", axis="o-ray"),
                  _axis("Barker-e", "main/GaN/nk/Barker-e.yml", "Barker1973", axis="e-ray")]),

    # ---- Sulfides (7 processable; EuS excluded, see EXCLUSION_STATE) ----
    dict(idx=72, name="Arsenic trisulfide", formula="As2S3", polymorph="amorphous",
         pubchem_name="Arsenic trisulfide", ri_aliases=["As2S3"],
         ri_axes=[_axis("Rodney", "main/As2S3/nk/Rodney.yml", "Rodney1958")]),
    dict(idx=73, name="Cadmium sulfide", formula="CdS", polymorph="greenockite",
         pubchem_name="Cadmium sulfide", ri_aliases=["CdS"],
         ri_axes=[_axis("Ninomiya-o", "main/CdS/nk/Ninomiya-o.yml", "Ninomiya1995", axis="o-ray"),
                  _axis("Ninomiya-e", "main/CdS/nk/Ninomiya-e.yml", "Ninomiya1995", axis="e-ray")]),
    dict(idx=74, name="Gallium sulfide", formula="GaS", polymorph="beta-GaS (2H)",
         pubchem_name="Gallium sulfide", ri_aliases=["GaS"],
         ri_axes=[_axis("Kato-o", "main/GaS/nk/Kato-o.yml", "Kato2011", axis="o-ray"),
                  _axis("Kato-e", "main/GaS/nk/Kato-e.yml", "Kato2011", axis="e-ray")]),
    dict(idx=75, name="Germanium disulfide", formula="GeS2", polymorph=None,
         pubchem_name="Germanium disulfide", ri_aliases=["GeS2"],
         ri_axes=[_axis("Slavich-alpha", "main/GeS2/nk/Slavich-alpha.yml", "Slavich1989", axis="alpha-axis"),
                  _axis("Slavich-beta", "main/GeS2/nk/Slavich-beta.yml", "Slavich1989", axis="beta-axis"),
                  _axis("Slavich-gamma", "main/GeS2/nk/Slavich-gamma.yml", "Slavich1989", axis="gamma-axis")]),
    dict(idx=76, name="Mercury(II) sulfide (cinnabar)", formula="HgS", polymorph="cinnabar",
         pubchem_name="Mercury sulfide", ri_aliases=["HgS"],
         ri_axes=[_axis("Bond-o", "main/HgS/nk/Bond-o.yml", "Bond1967", axis="o-ray"),
                  _axis("Bond-e", "main/HgS/nk/Bond-e.yml", "Bond1967", axis="e-ray")]),
    dict(idx=77, name="Lead(II) sulfide (galena)", formula="PbS", polymorph="rock salt",
         pubchem_name="Lead sulfide", ri_aliases=["PbS"],
         ri_axes=[_axis("Zemel", "main/PbS/nk/Zemel.yml", "Zemel1965")]),
    dict(idx=78, name="Zinc sulfide", formula="ZnS", polymorph="sphalerite",
         pubchem_name="Zinc sulfide", ri_aliases=["ZnS"],
         ri_axes=[_axis("Ozaki", "main/ZnS/nk/Ozaki.yml", "Ozaki1993")]),
]

# ---------------------------------------------------------------------------
# MP space-group overrides -- the EXPECTED_SPACEGROUP pattern from
# scripts/build_oxides_csv.py, extended for this batch's "pick the right
# entry" cases (CeF3, BN, HgS -- distinct from GdF3's named-exclusion shape).
# ---------------------------------------------------------------------------

EXPECTED_SPACEGROUP = {
    "CeF3": ([165], "tysonite (P-3c1) -- matches its light-lanthanide-trifluoride "
                     "family (LaF3); MP's lowest-hull entry (Cmcm #63) is tied at "
                     "Ehull=0.00 with the correct P-3c1 entry (mp-510560), and the "
                     "wrong one sorts first."),
    "BN": ([194], "hexagonal h-BN (P6_3/mmc) -- every RI.info page for this book is "
                   "explicitly labeled 'h-BN'. MP's lowest-hull entry (P-6m2 #187) is "
                   "a different, non-standard stacking polytype; the correct P6_3/mmc "
                   "entry (mp-629015) is at only +1.75 meV/atom, a well-documented "
                   "near-degenerate BN stacking situation, not a DFT artifact."),
    "HgS": ([152, 154], "trigonal cinnabar (P3_121 or its enantiomorphic setting P3_221) "
                         "-- RI.info's page states 'Bond et al. 1967: alpha-HgS' directly "
                         "(alpha-HgS = cinnabar, the stable RT phase). MP's lowest-hull "
                         "entry (mp-1123, F-43m #216) is metacinnabar (beta-HgS), a "
                         "DIFFERENT, higher-temperature polymorph -- the wrong one. Both "
                         "trigonal candidates (mp-634 #152, mp-9252 #154) are real, "
                         "ICSD-backed cinnabar entries (confirmed via provenance API), not "
                         "a DFT artifact -- enantiomorphic settings of the same physical "
                         "structure, so either is an acceptable pick; density is overridden "
                         "below regardless of which one is chosen."),
    "ZnS": ([216], "cubic sphalerite (F-43m) -- two of five RI.info pages explicitly say "
                    "'Cubic ZnS' (Debenham 1984, Ozaki 1993). MP has a dense cluster of "
                    "near-degenerate stacking polytypes right at the hull (P3m1 #156, "
                    "several entries within 0.0001 eV/atom of each other) -- the SAME "
                    "polytype-zoo shape as h-BN's stacking variants, just with more of "
                    "them -- and the true cubic entry (mp-10695, F-43m #216) sorts behind "
                    "them at Ehull=0.00015. Densities are all ~4.14 g/cm3 regardless of "
                    "stacking (this cluster barely affects density), but the space-group "
                    "provenance would otherwise be wrong."),
    "AlN": ([186], "wurtzite -- already the lowest-hull MP match (mp-661); pinned "
                    "explicitly so a future MP update can't silently drift this one, same "
                    "as EXPECTED_SPACEGROUP entries in the oxide batch that documented an "
                    "already-correct match rather than leaving it to coincidence."),
    "GaN": ([186], "wurtzite -- already the lowest-hull MP match (mp-804); pinned "
                    "explicitly, same reasoning as AlN above."),
    "CdS": ([186], "greenockite (wurtzite-type) -- already the lowest-hull MP match "
                    "(mp-672); pinned explicitly, same reasoning as AlN above."),
    "GaS": ([194], "beta-GaS (2H, P6_3/mmc) -- already the lowest-hull MP match (mp-2507); "
                    "no RI.info metadata states the polytype, but this matches GaS's "
                    "standard/common commercial form. Pinned explicitly rather than left "
                    "to coincidence, same reasoning as AlN above."),

    # The following six were NOT cleared by a page-name/COMMENTS phase claim
    # (unlike ZnS/GaN/BN/HgS above) -- their polymorph label came from
    # general crystallographic knowledge, with no EXPECTED_SPACEGROUP pin at
    # first. Added after the batch-2 audit that followed the HgS finding:
    # freshly re-queried MP for each (not re-trusting the original spot-check
    # alone) specifically looking for a close, wrong-sorting competitor at
    # the hull, the same shape of trap HgS/ZnS/BN had. None found -- all six
    # were already correct at lowest-hull -- but they're pinned now rather
    # than left to depend on that staying true by coincidence.
    "LaF3": ([165], "tysonite (P-3c1) -- lowest-hull mp-905, Ehull=0.00000. Nearest "
                     "competitor mp-334 (P6_3cm #185) is close (+0.90 meV/atom) but P-3c1 "
                     "is LaF3's well-documented room-temperature structure, matching its "
                     "light-lanthanide-trifluoride family (same family as CeF3's correct "
                     "phase). Re-checked fresh, not re-trusted from the original spot-check."),
    "MgF2": ([136], "rutile-type (P4_2/mnm) -- lowest-hull mp-1249, Ehull=0.00000, isostructural "
                     "with TiO2 rutile, MgF2's undisputed ambient structure. Nearest competitor "
                     "mp-1072956 (Pnnm #58) at +2.47 meV/atom. Re-checked fresh."),
    "YbF3": ([62], "YF3-type (Pnma) -- lowest-hull mp-22072, Ehull=0.00000, matching the "
                    "heavy-lanthanide-trifluoride family (same family as GdF3's expected, but "
                    "absent, phase). Nearest competitor is +352 meV/atom -- not remotely close, "
                    "no ambiguity. Re-checked fresh."),
    "LiCaAlF6": ([163], "colquiriite (P-31c) -- MP's only entry (mp-6134), Ehull=0.00000. "
                         "Independently confirmed via Materials Data on LiCaAlF6/LiSrAlF6 "
                         "(Le Fur et al., J. Solid State Chem., synchrotron single-crystal "
                         "diffraction): trigonal P-31c, colquiriite structure type."),
    "YLiF4": ([88], "scheelite-type (I4_1/a) -- lowest-hull mp-3700, Ehull=0.00000, the "
                     "well-documented YLF laser-host structure. Nearest competitor mp-556472 "
                     "(C2/c #15) at +0.32 meV/atom is close (same polytype-zoo shape as "
                     "ZnS/BN) but I4_1/a is the textbook-confirmed phase. Re-checked fresh, "
                     "pinned so a future near-tie doesn't silently flip this one."),
    "PbS": ([225], "rock-salt (Fm-3m) -- lowest-hull mp-21276, Ehull=0.00000, galena's only "
                    "known ambient-pressure phase (confirmed: PbS's only pressure-induced "
                    "transition is at 2.2 GPa, nowhere near ambient conditions). Nearest "
                    "competitor mp-1057015 (R3m #160) at +1.36 meV/atom is a DFT metastable "
                    "entry, not a documented ambient polymorph. Re-checked fresh."),
}

# ---------------------------------------------------------------------------
# Density overrides -- MP_DFT density for BOTH cinnabar candidates diverges
# substantially from the well-established experimental value (mp-634: 8.975
# g/cm3, +9.8%; mp-9252: 6.995 g/cm3, -14.4%), so this uses a literature
# citation instead of trusting either DFT relaxation, same discipline as
# CaGdAlO4/CaYAlO4 in the oxide batch.
# ---------------------------------------------------------------------------

EXPERIMENTAL_DENSITY_OVERRIDE = {
    "HgS": (
        8.176,
        "experimental (mineralogical): trigonal cinnabar, a=4.145(2) A, c=9.496(2) A, "
        "Z=3, specific gravity 8.176 (P3_121 #152 setting; mp-9252's P3_221 #154 is the "
        "enantiomorphic mirror of the same physical structure) -- both MP DFT relaxations "
        "diverge from this by 10-14%, so the citable experimental value is used instead.",
        dict(doi=None,
             title="Cinnabar: Mineral Data (Handbook of Mineralogy)",
             authors="Mineral Data Publishing",
             journal=None, year=2005,
             url="https://www.handbookofmineralogy.org/pdfs/cinnabar.pdf"),
    ),
}

# ---------------------------------------------------------------------------
# No-MP-match materials -- the FORCE_NO_MP pattern from build_oxides_csv.py.
# As2S3 gets a real literature density (AMTIR-6 datasheet). GdF3 gets NO
# density at all -- this is what makes it a true named exclusion rather than
# a low-confidence value: density_g_cm3 stays None end-to-end, same as
# LuAl3(BO3)4 in the oxide batch.
# ---------------------------------------------------------------------------

FORCE_NO_MP = {"As2S3", "GdF3"}

LITERATURE_DENSITY = {
    "As2S3": (
        3.2,
        "literature: AMTIR-6 (Amorphous Materials, Inc.) product datasheet for amorphous "
        "As40S60 glass -- 'Density 3.2 gms/cm3'. Cross-validated: the same datasheet cites "
        "'Malitson, Rodney, King, J. Opt. Soc. Amer. 48, 633 (1958)' for its own refractive "
        "index table -- the exact paper backing RI.info's 'Rodney' optical dataset used "
        "here, so density and optical constants trace to the same physical glass state.",
        dict(doi=None,
             title="AMTIR-6 (As2S3) product datasheet",
             authors="Amorphous Materials, Inc.",
             journal=None, year=None,
             url="https://refractiveindex.info/download/data/2012/AMTIR-6%20Information.pdf"),
    ),
    "GdF3": (
        None,
        "NAMED EXCLUSION -- see EXCLUSION_STATE['GdF3']. No experimental density obtainable "
        "within the timebox; MP's only entry is theoretical/unverified and structurally "
        "inconsistent with GdF3's documented room-temperature phase. Deliberately left as "
        "None, not backfilled with an untrustworthy MP value.",
        None,
    ),
}

# ---------------------------------------------------------------------------
# RESOLVED_OPTICAL_SOURCE_CITATION -- the exact pattern from
# scripts/oxide_material_list.py (VO2/TeO2/Ta2O5), extended here so a future
# batch (e.g. metals, or a TMDC/layer-count batch) doesn't re-litigate what
# this one settled.
# ---------------------------------------------------------------------------

RESOLVED_OPTICAL_SOURCE_CITATION = {
    "As2S3": dict(
        doi=None,
        title="AMTIR-6 (As2S3) product datasheet",
        authors="Amorphous Materials, Inc.",
        journal=None, year=None,
        verification_note=(
            "Reuses the SiO2 quartz-vs-fused-silica resolution verbatim. RI.info's "
            "'Slavich' dataset (biaxial alpha/beta/gamma) is necessarily CRYSTALLINE "
            "(orpiment) since biaxial optics require an ordered crystal -- switched "
            "default to 'Rodney' (Rodney, Malitson, King 1958), whose COMMENTS state "
            "'Arsenic trisulfide glass. 25 C' explicitly, meeting the same evidentiary bar "
            "as Ta2O5's 'Amorphous thin film' COMMENTS. Independently corroborated: "
            "'Synowicki' (2004) titles its dataset 'a-As2S3' (amorphous notation), "
            "contrasted directly against 'c-ZrO2'/'c-MgO' in the SAME paper."
        ),
    ),
    "HgS": dict(
        doi=None,
        title="Bond, W. L. et al. 1967 (RI.info page COMMENTS: 'alpha-HgS')",
        authors="Bond, W.L. et al.",
        journal=None, year=1967,
        verification_note=(
            "RI.info's own page name states the measured phase directly: 'Bond et al. "
            "1967: alpha-HgS' (cinnabar). Cross-checked against MP (not just trusted from "
            "the page name alone) -- MP's lowest-energy_above_hull entry is metacinnabar "
            "(F-43m #216, a DIFFERENT phase), so this needed the same EXPECTED_SPACEGROUP "
            "override treatment as CeF3/BN despite the RI.info metadata already stating "
            "the correct phase name."
        ),
    ),
}
