#!/usr/bin/env python3
"""
scripts/polymer_material_list.py
=================================
Candidate pool for the polymer family run. This is a CHECKLIST, not a promise: scripts/match_ri_info_polymers.py
scans the RI.info catalog and is authoritative -- a candidate the scan does not find is a gap, never padded.

ri_books   : (shelf, book) pairs on RI.info that may hold this polymer (chosen from the Phase 0 scan of the whole catalog,
             not only shelf=organic / 3d).
include_re / exclude_re : page filters (matched on RI page id + title + COMMENTS) for identity: e.g. HDPE vs LDPE, CR-39 polymer vs monomer.
blocked    : identity undefined without composition/doping/cure state -> never auto-loaded (needs_specific_formulation).
citations  : literature ALREADY RECORDED IN THIS REPO for a dispersion that is not on RI.info (Tier 2: cite only, do not transcribe).
No external literature search was done for this run; Tier 2 is therefore limited to citations that already exist in the repo.
"""


def _c(key, name, group, ri_books=(), include_re=None, exclude_re=None, blocked=False, note=None, citations=None):
    return dict(key=key, name=name, group=group, ri_books=list(ri_books), include_re=include_re, exclude_re=exclude_re,
                blocked=blocked, note=note, citations=citations or [])


ORG, OTH = "organic", "other"
CANDIDATES = [
    # ---- Commodity
    _c("PE-LDPE", "Low-density polyethylene (LDPE)", "commodity", [(ORG, "polyethylene")], include_re=r"(?<![Ll])LDPE",
       note="RI.info's only low-density page is LLDPE (linear), a distinct polymer; not substituted"),
    _c("PE-HDPE", "High-density polyethylene (HDPE)", "commodity", [(ORG, "polyethylene")], include_re=r"HDPE"),
    _c("PP", "Polypropylene", "commodity"),
    _c("PVC", "Polyvinyl chloride", "commodity", [(ORG, "polyvinil_chloride")]),
    _c("PS", "Polystyrene", "commodity", [(ORG, "polystyrene")]),
    _c("PMMA", "Poly(methyl methacrylate)", "commodity",
       [(ORG, "poly_methyl_methacrylate"), (OTH, "Microchem495"), (OTH, "Microchem950")]),
    _c("PC", "Polycarbonate", "commodity", [(ORG, "polycarbonate")]),
    _c("PET", "Polyethylene terephthalate", "commodity", [(ORG, "polyethylene_terephthalate")]),
    _c("PEN", "Polyethylene naphthalate", "commodity"),
    _c("PVA", "Polyvinyl alcohol", "commodity", [(ORG, "polyvinyl_alcohol")]),
    _c("PVAc", "Polyvinyl acetate", "commodity"),
    _c("PVP", "Polyvinylpyrrolidone", "commodity", [(ORG, "polyvinylpyrrolidone")]),
    _c("PTFE", "Polytetrafluoroethylene", "commodity", note="in-DB legacy row has an unreferenced density and single-point n; not traceable"),
    _c("PVDF", "Polyvinylidene fluoride", "commodity"),
    _c("PVDC", "Polyvinylidene chloride", "commodity"),
    _c("PVF", "Polyvinyl fluoride", "commodity"),
    _c("FEP", "Fluorinated ethylene propylene", "commodity"),
    _c("PFA", "Perfluoroalkoxy alkane", "commodity"),
    _c("ETFE", "Ethylene tetrafluoroethylene", "commodity"),
    # ---- Engineering
    _c("PA6", "Polyamide 6", "engineering"),
    _c("PA66", "Polyamide 66", "engineering", note="in-DB legacy 'Nylon66' row has an unreferenced density and single-point n; not traceable"),
    _c("PA12", "Polyamide 12", "engineering"),
    _c("POM", "Polyoxymethylene", "engineering"),
    _c("PBT", "Polybutylene terephthalate", "engineering"),
    _c("PEEK", "Polyether ether ketone", "engineering", note="in-DB legacy row has an unreferenced density and single-point n; not traceable"),
    _c("PEI", "Polyetherimide (PEI)", "engineering", [(ORG, "polyetherimide")],
       note="NAME COLLISION: the DB's existing 'PEI' row is (C2H5N)n = polyethylenimine, a different polymer"),
    _c("PSU", "Polysulfone", "engineering"),
    _c("PES", "Polyethersulfone", "engineering"),
    _c("PPSU", "Polyphenylsulfone", "engineering"),
    _c("PPS", "Polyphenylene sulfide", "engineering"),
    _c("PPO", "Polyphenylene oxide", "engineering"),
    _c("PAI", "Polyamide-imide", "engineering"),
    _c("PBI", "Polybenzimidazole", "engineering"),
    _c("PAR", "Polyarylate", "engineering"),
    _c("ABS", "Acrylonitrile butadiene styrene", "engineering"),
    _c("SAN", "Styrene-acrylonitrile copolymer", "engineering", [(OTH, "C8H8_n-C3H3N_m")]),
    _c("NAS", "NAS (generic styrene-methyl methacrylate copolymer)", "engineering",
       note="only the NAS-21 grade exists on RI.info; generic NAS not substituted"),
    # ---- Optical / micro
    _c("PDMS", "Polydimethylsiloxane", "optical", [(ORG, "polydimethylsiloxane")]),
    _c("SU-8", "SU-8 epoxy photoresist", "optical", [(OTH, "Microchem_SU8_2000"), (OTH, "Microchem_SU8_3000")]),
    _c("COP-Zeonex-E48R", "Zeonex E48R (cyclo olefin polymer)", "optical", [(OTH, "ZeonexE48R")]),
    _c("COC-Topas", "Topas (cyclic olefin copolymer)", "optical"),
    _c("Optorez-1330", "Optorez 1330", "optical", [(OTH, "Optorez1330")]),
    _c("NAS-21", "NAS-21", "optical", [(OTH, "NAS-21")]),
    _c("PMP", "Polymethylpentene (TPX)", "optical", [(ORG, "C6H12_n - polymethylpentene")]),
    _c("Rexolite", "Rexolite", "optical"),
    _c("CR-39", "CR-39 (polymer)", "optical", [(OTH, "CR-39")], exclude_re=r"Monomer",
       note="RI.info's other CR-39 page is the monomer, a different material; excluded"),
    _c("Parylene-C", "Parylene C", "optical"),
    _c("Parylene-N", "Parylene N", "optical"),
    _c("Kapton", "Kapton (polyimide film)", "optical", [(OTH, "Kapton")]),
    # ---- Bio / other
    _c("PLA", "Poly(D-lactic acid) (PDLA)", "bio", [(ORG, "polylactic_acid")],
       note="the only RI.info dataset is PDLA (poly-D-lactic acid), narrower than generic PLA; stereochemistry not generalized"),
    _c("PGA", "Polyglycolic acid", "bio"),
    _c("PCL", "Polycaprolactone", "bio"),
    _c("PAN", "Polyacrylonitrile", "bio"),
    _c("cellulose", "Cellulose", "bio", [(ORG, "cellulose")]),
    _c("cellulose-acetate", "Cellulose acetate", "bio"),
    _c("cellulose-nitrate", "Cellulose nitrate", "bio"),
    _c("chitosan", "Chitosan", "bio"),
    _c("PEG", "Polyethylene glycol / oxide (PEO/PEG)", "bio",
       citations=["Shah et al., Surf. Sci. Spectra 27, 016001 (2020); MW 285-315 g/mol (150 optical points, in materials_normalized.db)",
                  "Brandrup et al., Polymer Handbook 4th ed. (1999) (single point, 589 nm, in materials_normalized.db)"],
       note="in-DB 'PEG' row carries formula C2H6O2 (ethylene glycol), not a repeat unit"),
    _c("PVB", "Polyvinyl butyral", "bio"),
    # ---- BLOCKED: identity undefined without composition / doping / cure state
    _c("PU", "Polyurethane", "blocked", blocked=True),
    _c("TPU", "Thermoplastic polyurethane", "blocked", blocked=True),
    _c("LCP", "Liquid crystal polymer", "blocked", blocked=True),
    _c("EVA", "Ethylene-vinyl acetate", "blocked", [(OTH, "EVASKY_S87"), (OTH, "EVASKY_S88")], blocked=True,
       note="RI.info has EVASKY S87/S88 (specific products); a generic EVA identity is still undefined"),
    _c("PLGA", "Poly(lactic-co-glycolic acid)", "blocked", blocked=True),
    _c("EVOH", "Ethylene vinyl alcohol", "blocked", blocked=True),
    _c("PANI", "Polyaniline", "blocked", blocked=True),
    _c("PPy", "Polypyrrole", "blocked", blocked=True),
    _c("PEDOT-PSS", "PEDOT:PSS", "blocked", [(OTH, "PEDOT-PSS")], blocked=True,
       note="RI.info has one PEDOT:PSS page; composition/doping not defined"),
    _c("epoxy", "Epoxy (generic)", "blocked", blocked=True),
    _c("polyimide", "Polyimide (generic)", "blocked", blocked=True,
       note="Kapton is a specific product and is handled as its own candidate"),
]


# ---------------------------------------------------------------------------------------------------------------------
# Phase 3 scope decisions (user, this run). Anything not listed here and not auto-selected stays out of the load.
# ---------------------------------------------------------------------------------------------------------------------
# (shelf, book, page) datasets chosen among a multi-match; `excluded` = (book-or-page, reason) recorded as gap rows.
RESOLUTIONS = {
    "PC": dict(pages=[(ORG, "polycarbonate", "Zhang")], name=None,
               excluded=[("Sultanova", "subset of Zhang range, disagrees ~0.4% at 633 nm, deferred to dataset-comparison PR")],
               basis="Zhang only (user decision): Sultanova (0.437-1.052 um) lies entirely inside Zhang (0.4-19.94 um)"),
    "cellulose": dict(pages=[(ORG, "cellulose", "Sultanova")], name=None,
                      excluded=[("Juntunen", "microcrystalline Avicel PH102 powder: powder n is a packing artifact (user decision)")],
                      basis="Sultanova bulk only (user decision)"),
    "SU-8": dict(pages=[(OTH, "Microchem_SU8_3000", "specs")], name="SU-8 3000 (epoxy photoresist)",
                 excluded=[("Microchem_SU8_2000", "source states 'Uncured'; uncured resist n is not a material constant (user decision)")],
                 basis="3000 series only, one row (user decision)"),
}
# Deferred entirely: no material row, no dataset picked, not claimed by this PR.
DEFERRED = {
    "PS": "5 datasets (bulk, powder, microspheres, two n+k); no dataset chosen this PR",
    "PMMA": "12 datasets (bulk, thin film, microspheres, 950k resist grade, Microchem 495/950); grades not resolved",
    "PDMS": "10 datasets that are likely distinct materials (cure ratios 5:1-20:1, RTV615/Sylgard 184, UV-curable, SF-96 fluid)",
    "Kapton": "8 loadable datasets across products (H/HN/DuPont sheet) and non-overlapping ranges; product not chosen",
    "PVA": "2 different films (10 um on glass vs thin film on Si); not resolved",
}
# Grade-specific commercial materials have NO formula on RI.info: formula stays NULL (valid for a polymer row; no placeholder token).
# No `grade` column (withdrawn; no schema change): the grade is a single "grade: <name>" line in the notes field.
GRADE_NOTES = {"COP-Zeonex-E48R": "Zeonex E48R", "Optorez-1330": "Optorez 1330", "NAS-21": "NAS-21", "SU-8": "SU-8 3000"}
