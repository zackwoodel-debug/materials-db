"""Resolved optical-source citations: the evidence behind each phase label that had to be verified against the optical
source's own stated measurement condition. Carried into every exported layer's provenance (materials_db.export.modalfit).

Moved here verbatim from scripts/oxide_material_list.py (VO2 / TeO2 / Ta2O5) and
scripts/fluoride_nitride_sulfide_material_list.py (As2S3 / HgS) so the installed package does not import from scripts/;
both scripts re-export their table under its old name, RESOLVED_OPTICAL_SOURCE_CITATION.
"""

# ---- oxide batch (from scripts/oxide_material_list.py) ----------------------

# Optical-source triage resolution record (formerly PENDING_TRIAGE_PHYSICAL_
# POLYMORPH, held out of MATERIALS_50 pending per-material verification --
# now resolved and folded into the list above). Each phase call was checked
# against the specific measurement condition stated in the optical source
# itself, not inferred from the physical-properties pick:
#   VO2   -> M1 (insulating): Beaini et al., 70nm film measured at 25 C,
#            below VO2's ~68 C metal-insulator transition -- monoclinic M1.
#   TeO2  -> paratellurite: Uchida 1971 paper title states this directly
#            ("Optical properties of single-crystal paratellurite (TeO2)").
#   Ta2O5 -> amorphous: Bright et al.'s RI.info COMMENTS field states
#            "Amorphous thin film" explicitly -- NOT a crystalline phase name.
# Full citations below, carried into each exported layer's provenance
# (materials_db.export.modalfit) so a future reader can see the phase label
# was verified against a stated measurement condition, not inferred.
OXIDE_RESOLVED_OPTICAL_SOURCE_CITATION = {
    "VO2": dict(
        doi="10.1016/j.solmat.2019.110260",
        title="Thermochromic VO2-based smart radiator devices with ultralow "
              "refractive index cavities for increased performance",
        authors="Beaini, R.; Baloukas, B.; Loquai, S.; Klemberg-Sapieha, J.E.; Martinu, L.",
        journal="Solar Energy Materials and Solar Cells", year=2020,
        verification_note="70nm film measured at 25 C, below VO2's ~68 C metal-insulator "
                           "transition -- confirms monoclinic M1 (insulating) phase.",
    ),
    "TeO2": dict(
        doi="10.1103/PhysRevB.4.3736",
        title="Optical properties of single-crystal paratellurite (TeO2)",
        authors="Uchida, N.",
        journal="Physical Review B", year=1971,
        verification_note="Paper title explicitly names the measured phase: paratellurite.",
    ),
    "Ta2O5": dict(
        doi="10.1063/1.4819325",
        title="Infrared optical properties of amorphous and nanocrystalline Ta2O5 thin films",
        authors="Bright, T.J.; Watjen, J.I.; Zhang, Z.M.; Muratore, C.; Voevodin, A.A.; "
                "Koukis, D.I.; Tanner, D.B.; Arenas, D.J.",
        journal="Journal of Applied Physics", year=2013,
        verification_note="RI.info's COMMENTS field for this dataset states \"Amorphous thin "
                           "film\" explicitly -- not a crystalline phase name.",
    ),
}


# ---- fluoride / nitride / sulfide batch (from scripts/fluoride_nitride_sulfide_material_list.py) ----

# ---------------------------------------------------------------------------
# RESOLVED_OPTICAL_SOURCE_CITATION -- the exact pattern from
# scripts/oxide_material_list.py (VO2/TeO2/Ta2O5), extended here so a future
# batch (e.g. metals, or a TMDC/layer-count batch) doesn't re-litigate what
# this one settled.
# ---------------------------------------------------------------------------

BATCH2_RESOLVED_OPTICAL_SOURCE_CITATION = {
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


# Single merged lookup across every batch -- a later batch extends this rather than starting its own dict.
RESOLVED_OPTICAL_SOURCE_CITATION = {**OXIDE_RESOLVED_OPTICAL_SOURCE_CITATION, **BATCH2_RESOLVED_OPTICAL_SOURCE_CITATION}
