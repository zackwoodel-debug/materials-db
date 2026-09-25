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


def _c(key, name, group, ri_books=(), include_re=None, exclude_re=None, blocked=False, note=None, citations=None,
       materialclass="polymer", excluded_pages=()):
    return dict(key=key, name=name, group=group, ri_books=list(ri_books), include_re=include_re, exclude_re=exclude_re,
                blocked=blocked, note=note, citations=citations or [], materialclass=materialclass,
                excluded_pages=[list(x) for x in excluded_pages])


ORG, OTH = "organic", "other"
# Datasets of the split families that are deliberately NOT loaded: (shelf, book, page, reason). The % figures are re-derived from source
# at test time (tests/test_polymer_pipeline.py), never trusted from this text.
PMMA_EXCLUDED = [
    (ORG, "poly_methyl_methacrylate", "Sultanova", "bulk n-only 0.437-1.052 um, inside both Zhang ranges; differs +0.38% (Tomson) / -0.14% (Mitsubishi) at 633 nm; deferred to dataset-comparison PR"),
    (ORG, "poly_methyl_methacrylate", "Beadie", "bulk n-only 0.42-1.62 um; differs +0.53% (Tomson) / +0.00% (Mitsubishi) at 633 nm; deferred to dataset-comparison PR"),
    (ORG, "poly_methyl_methacrylate", "Szczurowski", "bulk n-only 0.405-1.08 um; differs +0.39% (Tomson) / -0.13% (Mitsubishi) at 633 nm; deferred to dataset-comparison PR"),
    (ORG, "poly_methyl_methacrylate", "Nyakuchena", "polymer microspheres: a particle sample, not a bulk material constant"),
    (ORG, "poly_methyl_methacrylate", "Bodurov", "20 um film on glass (thin film), not a bulk sample; deferred"),
    (ORG, "poly_methyl_methacrylate", "Tsuda", "MicroChem PMMA resist, Mw 950,000, baked: resist grade, not bulk; deferred"),
    (ORG, "poly_methyl_methacrylate", "Tsuda-LD", "MicroChem PMMA resist (950k) Lorentz-Drude model fit: resist grade, not bulk; deferred"),
    (ORG, "poly_methyl_methacrylate", "Tsuda-BB", "MicroChem PMMA resist (950k) Brendel-Bormann model fit: resist grade, not bulk; deferred"),
    (OTH, "Microchem495", "specs", "Microchem 495 PMMA resist spec sheet: resist grade (not bulk); deferred"),
    (OTH, "Microchem950", "specs", "Microchem 950 PMMA resist spec sheet: resist grade (not bulk); deferred"),
]
PDMS_EXCLUDED = [
    (ORG, "polydimethylsiloxane", "Schneider-RTV615", "product-specific dataset (RTV 615, Bayer/Momentive; n only 0.35-0.70 um) overlapping the Zhang rows; deferred"),
    (ORG, "polydimethylsiloxane", "Schneider-Sylgard184", "product-specific dataset (Sylgard 184, Dow; n only 0.35-0.70 um) overlapping the Zhang rows; deferred"),
    (ORG, "polydimethylsiloxane", "Gupta", "source comment reads 'Polydimethylphenylsiloxane (PDMS) substrate', hardener (Sylgard 184) to PDMS ratio 1:10: a different chemistry per the source; deferred"),
    (ORG, "polydimethylsiloxane", "Gupta-UV", "UV-curable polydimethylphenylsiloxane: a different chemistry from the Zhang thermally cured PDMS"),
    (ORG, "polydimethylsiloxane", "Querry-NIR", "SF-96 polydimethylsiloxane FLUID (uncrosslinked), not a cured elastomer"),
    (ORG, "polydimethylsiloxane", "Querry-IR", "SF-96 polydimethylsiloxane FLUID (uncrosslinked), not a cured elastomer"),
]

CANDIDATES = [
    # ---- Commodity
    _c("PE-LDPE", "Low-density polyethylene (LDPE)", "commodity", [(ORG, "polyethylene")], include_re=r"(?<![Ll])LDPE",
       note="RI.info's only low-density page is LLDPE (linear), a distinct polymer; not substituted"),
    _c("PE-HDPE", "High-density polyethylene (HDPE)", "commodity", [(ORG, "polyethylene")], include_re=r"HDPE"),
    _c("PP", "Polypropylene", "commodity"),
    _c("PVC", "Polyvinyl chloride", "commodity", [(ORG, "polyvinil_chloride")]),
    _c("PS", "Polystyrene", "commodity", [(ORG, "polystyrene")]),
    # PMMA is split per supplier (Zhang 2020 Tomson vs Mitsubishi differ by -0.52% at 633 nm: different suppliers = different materials).
    _c("PMMA-Tomson", "Poly(methyl methacrylate) (Tomson)", "commodity", [(ORG, "poly_methyl_methacrylate")], include_re=r"Zhang-Tomson",
       note="Zhang 2020 bulk sample, manufacturer Tomson (China); n differs -0.52% from the Mitsubishi row at 633 nm",
       excluded_pages=PMMA_EXCLUDED),
    _c("PMMA-Mitsubishi", "Poly(methyl methacrylate) (Mitsubishi)", "commodity", [(ORG, "poly_methyl_methacrylate")],
       include_re=r"Zhang-Mitsubishi", note="Zhang 2020 bulk sample, manufacturer Mitsubishi (Japan)"),
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
    # PDMS is split per cure ratio (n depends on it): Zhang 2020, Dow Corning, mass ratio main agent : curing agent.
    _c("PDMS-5-1", "Polydimethylsiloxane (Dow Corning, 5:1 mass ratio)", "optical", [(ORG, "polydimethylsiloxane")],
       include_re=r"Zhang-5-1\b", excluded_pages=PDMS_EXCLUDED),
    _c("PDMS-10-1", "Polydimethylsiloxane (Dow Corning, 10:1 mass ratio)", "optical", [(ORG, "polydimethylsiloxane")], include_re=r"Zhang-10-1\b"),
    _c("PDMS-15-1", "Polydimethylsiloxane (Dow Corning, 15:1 mass ratio)", "optical", [(ORG, "polydimethylsiloxane")], include_re=r"Zhang-15-1\b"),
    _c("PDMS-20-1", "Polydimethylsiloxane (Dow Corning, 20:1 mass ratio)", "optical", [(ORG, "polydimethylsiloxane")], include_re=r"Zhang-20-1\b"),
    _c("SU-8", "SU-8 epoxy photoresist", "optical", [(OTH, "Microchem_SU8_2000"), (OTH, "Microchem_SU8_3000")], materialclass="photoresist"),
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
    _c("Kapton", "Kapton HN (polyimide film)", "optical", [(OTH, "Kapton")]),
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
    # ---- Batch 2: RI.info polymers that were outside the original pool
    _c("PE-LLDPE", "Linear low-density polyethylene (LLDPE)", "batch2", [(ORG, "polyethylene")], include_re=r"LLDPE",
       note="David 2022: spin-coated ~270 nm film from toluene (2-12.3 um); a distinct polymer from LDPE/HDPE, does not fill the LDPE gap"),
    _c("PCTFE", "Polychlorotrifluoroethylene (PCTFE)", "batch2", [(ORG, "C2ClF3_n - polychlorotrifluoroethylene")]),
    _c("PNIPAM", "Poly(N-isopropylacrylamide) (PNIPAM)", "batch2", [(ORG, "poly_N-isopropylacrylamide")],
       note="thermoresponsive polymer: the source states no temperature or swelling state"),
    _c("Surlyn-A1601", "Surlyn A-1601 (DuPont ionomer resin)", "batch2", [(OTH, "SurlynA1601")]),
    _c("MDMO-PPV", "MDMO-PPV", "batch2", [(ORG, "MDMO-PPV")], materialclass="organic_semiconductor"),
    _c("ZZ50", "ZZ50", "batch2", [(ORG, "ZZ50")], materialclass="organic_semiconductor"),
    _c("F8BT", "F8BT", "batch2", [(ORG, "F8BT")], materialclass="organic_semiconductor"),
    _c("PTB7", "PTB7", "batch2", [(ORG, "PTB7")], materialclass="organic_semiconductor"),
    _c("PDCBT", "PDCBT", "batch2", [(ORG, "PDCBT")], materialclass="organic_semiconductor"),
    _c("PBDB-T-2F", "PBDB-T-2F", "batch2", [(ORG, "PBDB-T-2F")], materialclass="organic_semiconductor"),
    _c("maN-1407", "Micro resist ma-N 1407 (negative resist)", "batch2", [(OTH, "microresist_ma-N1407")], materialclass="photoresist",
       note="Sarkar 2019: thin film, 1000 nm on glass"),
    _c("EpoClad", "Micro resist EpoClad (negative photoresist)", "batch2", [(OTH, "microresistEpoClad")], materialclass="photoresist"),
    _c("EpoCore", "Micro resist EpoCore (negative photoresist)", "batch2", [(OTH, "microresistEpoCore")], materialclass="photoresist"),
    _c("Microchem-8.5mEL", "Microchem 8.5 mEL (copolymer resist)", "batch2", [(OTH, "Microchem85mEL")], materialclass="photoresist",
       note="the source does not state which copolymer"),
    _c("IP-S", "Nanoscribe IP-S (cured)", "batch2", [(OTH, "Nanoscribe_IP-S")], include_re=r"Mavrona-cured", materialclass="photoresist",
       note="far-IR / THz data (200-998 um)",
       excluded_pages=[(OTH, "Nanoscribe_IP-S", "Mavrona-uncured", "source states 'Uncured'; uncured resist n is not a material constant (same rule as SU-8 2000)")]),
    _c("IP-Dip", "Nanoscribe IP-Dip (cured)", "batch2", [(OTH, "Nanoscribe_IP-Dip")], include_re=r"Mavrona-cured", materialclass="photoresist",
       note="far-IR / THz data (200-998 um)",
       excluded_pages=[(OTH, "Nanoscribe_IP-Dip", "Mavrona-uncured", "source states 'Uncured'; uncured resist n is not a material constant (same rule as SU-8 2000)")]),
    _c("HPMC", "Hydroxypropyl methylcellulose (Pharmacoat 606)", "batch2", [(OTH, "Pharmacoat606")], materialclass="polymer"),
    _c("maN-405-T1050", "ma-N 405 : ma-T 1050 (1:1 mixture)", "batch2", [(OTH, "microresist_ma-N405_ma-T1050")], blocked=True, materialclass="photoresist",
       note="a 1:1 mixture of two components, not a single material"),
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
# Scope decisions (user). Anything not listed here and not auto-selected stays out of the load.
# ---------------------------------------------------------------------------------------------------------------------
# (shelf, book, page) datasets chosen among a multi-match; `axes` = one axis label per page (label becomes "<tag> | <axis>");
# `excluded` = (page, reason) recorded as gap rows.
KAMPTNER = "one paper (Kamptner 2024): ordinary and extraordinary rays of the same film, loaded as one material with two axes"
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
    "PS": dict(pages=[(ORG, "polystyrene", "Zhang")], name=None,
               excluded=[("Sultanova", "subset of Zhang range, disagrees ~0.1% at 633 nm, deferred to dataset-comparison PR"),
                         ("Juntunen", "powder: powder n is a packing artifact (same rule as cellulose Juntunen)"),
                         ("Nyakuchena", "polymer microspheres: a particle sample, not a bulk material constant"),
                         ("Myers", "not selected: overlaps Zhang (1.28-25 um); the source comment reads 'Isopropanol', sample state unclear; deferred")],
               basis="Zhang only (user decision, default accepted): it covers Sultanova's range plus the IR"),
    "PVA": dict(pages=[(ORG, "polyvinyl_alcohol", "Schnepf")], name=None,
                excluded=[("Bodurov", "not selected: a different film (10 um on glass) from Schnepf's thin film on Si; deferred")],
                basis="Schnepf only (user decision, default accepted): the wider range (0.3-1.5 um)"),
    "Kapton": dict(pages=[(OTH, "Kapton", "French")], name="Kapton HN (polyimide film)",
                   excluded=[("Cunningham", "different sample/range (DuPont sheet, 30-490 um far-IR); deferred"),
                             ("Sahin", "Kapton HN 125 um film, THz 160-3000 um (also beyond the 2000 um loader window); deferred"),
                             ("Kumar", "Kapton-H (a different product from HN), n 0.41-0.65 / k 0.49-0.78 um; deferred"),
                             ("Kawka", "polyimide films on substrates, FTIR 1.44-4.98 um; deferred"),
                             ("Zhang", "Lorentz-Drude model fit 1.67-20 um; deferred"),
                             ("Arakawa", "Kapton type H (a different product from HN); deferred"),
                             ("Smith", "far-IR 28.6-182 um; deferred"),
                             ("Philipp", "k-only page (no n) for a different polyimide (Pyralin PI-2540); deferred"),
                             ("Brannon", "k-only page (no n), 'chemically identical to Kapton' thin films; deferred")],
                   basis="Kapton HN, French only (user decision, default accepted): one product, one range"),
}
for _k in ("MDMO-PPV", "ZZ50", "F8BT", "PTB7", "PDCBT", "PBDB-T-2F"):
    RESOLUTIONS[_k] = dict(pages=[(ORG, _k, "Kamptner-o"), (ORG, _k, "Kamptner-e")], axes=("o-ray", "e-ray"), name=None, excluded=[], basis=KAMPTNER)

# Candidates with a usable dataset that are deliberately NOT loaded (no material row): key -> reason.
EXCLUDED_CANDIDATES = {
    "HPMC": "the Pharmacoat 606 page states 'Powder. 23 C': powder n is a packing artifact (same rule as cellulose Juntunen)",
}
# Deferred entirely: no material row, no dataset picked (mechanism kept; nothing is deferred at present).
DEFERRED = {}
# Grade-specific commercial materials have NO formula on RI.info: formula stays NULL (valid for a polymer row; no placeholder token).
# No `grade` column (withdrawn; no schema change): the grade is a single "grade: <name>" line in the notes field.
GRADE_NOTES = {"COP-Zeonex-E48R": "Zeonex E48R", "Optorez-1330": "Optorez 1330", "NAS-21": "NAS-21", "SU-8": "SU-8 3000",
               "Kapton": "Kapton HN", "Surlyn-A1601": "Surlyn A-1601", "maN-1407": "ma-N 1407", "EpoClad": "EpoClad", "EpoCore": "EpoCore",
               "Microchem-8.5mEL": "Microchem 8.5 mEL", "IP-S": "Nanoscribe IP-S", "IP-Dip": "Nanoscribe IP-Dip"}
