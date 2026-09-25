#!/usr/bin/env python3
"""
scripts/liquid_material_list.py
================================
Candidate list for the liquids and biomolecules family: pure substances that refractiveindex.info measured as liquids near room
temperature (water, heavy water, carbon disulfide, mercury, organic solvents), small biomolecules (L-tyrosine, urea, lactose
monohydrate) and biomacromolecules (DNA, silk fibroin). A CHECKLIST: scripts/match_ri_info_liquids.py scans the catalog.

One materials row is one compound (one InChIKey). Several refractiveindex.info books hold more than one compound, so a candidate may
name the exact `pages` it owns:
  * H2O book: water and heavy water (D2O);
  * propanol / butanol / pentanol / pentane / octane books: different isomers on different pages (read from each page's own text).
Water's pages are labelled with the phase each page states (liquid, supercooled liquid, ice, amorphous ice, crystalline ice).
Every other multi-paper book loads all its papers as separate datasets (standing rule, as for SiC, halides, chalcogenides).
"""


def _c(key, name, formula, book, shelf="organic", materialclass="liquid", pubchem_name=None, pages=None, page_phase=None, note=None):
    """pubchem_name: None -> look up by `name`; False -> no PubChem lookup (no single compound)."""
    return dict(key=key, name=name, formula=formula, book=book, shelf=shelf, materialclass=materialclass,
                pubchem_name=name if pubchem_name is None else (pubchem_name or None), pages=pages, page_phase=page_phase or {}, note=note)


_WATER_PHASE = {
    **{p: "liquid" for p in ("Hale", "Kedenburg", "Daimon-19.0C", "Daimon-20.0C", "Daimon-21.5C", "Daimon-24.0C", "Bashkatov", "Segelstein", "Asfar-H2O")},
    **{p: "supercooled liquid" for p in ("Rowe-240K", "Rowe-253K", "Rowe-263K", "Rowe-273K")},
    **{p: "ice" for p in ("Warren-2008", "Warren-1984")},
    **{p: "amorphous ice" for p in ("Kofman-10K", "Kofman-30K", "Kofman-50K", "Kofman-70K", "Kofman-90K", "Kofman-110K", "Kofman-130K")},
    "Kofman-150K": "crystalline ice",
}
_D2O_PAGES = ("Kedenburg-D2O", "Sarkar-D2O", "Wang-D2O", "Asfar-D2O")

CANDIDATES = [
    # --- inorganic liquids (main shelf)
    _c("H2O", "Water", "H2O", "H2O", shelf="main", pages=list(_WATER_PHASE) + ["Wang"], page_phase=_WATER_PHASE,
       note="one compound, several phases: each dataset is labelled with the phase its page states"),
    _c("D2O", "Heavy water (D2O)", "D2O", "H2O", shelf="main", pubchem_name="Deuterium oxide", pages=list(_D2O_PAGES),
       page_phase={p: "liquid" for p in _D2O_PAGES}, note="its pages sit in the H2O book; a different compound (different InChIKey)"),
    _c("CS2", "Carbon disulfide", "CS2", "CS2", shelf="main"),
    _c("Hg", "Mercury (liquid)", "Hg", "Hg", shelf="main", pubchem_name="Mercury", note="liquid metal at room temperature"),
    # --- alkanes, haloalkanes, alkenes
    _c("n-C5H12", "n-Pentane", "C5H12", "pentane", pubchem_name="Pentane", pages=["Kerl-293K", "Kerl-313K", "Kerl-333K"]),
    _c("i-C5H12", "Isopentane (2-methylbutane)", "C5H12", "pentane", pubchem_name="Isopentane", pages=["Anderson"]),
    _c("n-C6H14", "n-Hexane", "C6H14", "hexane", pubchem_name="Hexane", pages=["Kozma", "Kerl-293K", "Kerl-313K", "Kerl-333K"]),
    _c("n-C7H16", "n-Heptane", "C7H16", "heptane", pubchem_name="Heptane"),
    _c("n-C8H18", "n-Octane", "C8H18", "octane", pubchem_name="Octane", pages=["Kerl-293K", "Kerl-313K", "Kerl-333K", "Myers"]),
    _c("i-C8H18", "Isooctane (2,2,4-trimethylpentane)", "C8H18", "octane", pubchem_name="2,2,4-Trimethylpentane", pages=["Anderson"]),
    _c("CHBr3", "Bromoform", "CHBr3", "bromoform"),
    _c("CH2Cl2", "Dichloromethane", "CH2Cl2", "dichloromethane"),
    _c("CHCl3", "Chloroform", "CHCl3", "chloroform"),
    _c("CCl4", "Carbon tetrachloride", "CCl4", "carbon_tetrachloride"),
    _c("CBrCl3", "Bromotrichloromethane", "CBrCl3", "bromotrichloromethane"),
    _c("C6F14", "Perfluorohexane", "C6F14", "perfluorohexane", pubchem_name="Tetradecafluorohexane"),
    _c("C2Cl4", "Tetrachloroethylene", "C2Cl4", "tetrachloroethylene"),
    # --- cyclic compounds
    _c("C6H6", "Benzene", "C6H6", "benzene"),
    _c("C4H8OS", "1,4-Oxathiane", "C4H8OS", "oxathiane"),
    _c("C5H5N", "Pyridine", "C5H5N", "pyridine"),
    _c("C6H12", "Cyclohexane", "C6H12", "cyclohexane"),
    _c("C7H8", "Toluene", "C7H8", "toluene"),
    _c("C8H8", "Styrene", "C8H8", "styrene"),
    _c("p-C8H10", "p-Xylene", "C8H10", "xylene"),
    _c("C6H3Cl3", "1,2,4-Trichlorobenzene", "C6H3Cl3", "trichlorobenzene"),
    _c("C6H5NO2", "Nitrobenzene", "C6H5NO2", "nitrobenzene"),
    _c("C7F5N", "Pentafluorobenzonitrile", "C7F5N", "pentafluorobenzonitrile"),
    _c("C8H11N", "N,N-Dimethylaniline", "C8H11N", "dimethylaniline"),
    # --- alcohols
    _c("CH3OH", "Methanol", "CH3OH", "methanol"),
    _c("C2H5OH", "Ethanol", "C2H5OH", "ethanol"),
    _c("2-C3H7OH", "2-Propanol (isopropanol)", "C3H7OH", "propanol", pubchem_name="Isopropyl alcohol",
       pages=["Kozma", "Wang-20C", "Wang-50C", "Wang-70C", "Myers", "Sani", "Sani-formula"]),
    _c("1-C3H7OH", "1-Propanol", "C3H7OH", "propanol", pages=["Chang", "Moutzouris"]),
    _c("1-C4H9OH", "1-Butanol", "C4H9OH", "butanol", pages=["Chang", "Wang-20C", "Wang-60C", "Wang-90C", "Moutzouris-n"]),
    _c("i-C4H9OH", "Isobutanol (2-methyl-1-propanol)", "C4H9OH", "butanol", pubchem_name="Isobutanol", pages=["Moutzouris-iso"]),
    _c("1-C5H11OH", "1-Pentanol", "C5H11OH", "pentanol", pages=["Moutzouris-normal"]),
    _c("i-C5H11OH", "Isoamyl alcohol (3-methyl-1-butanol)", "C5H11OH", "pentanol", pubchem_name="Isoamyl alcohol", pages=["Moutzouris-iso"]),
    _c("C8H17OH", "1-Octanol", "C8H17OH", "octanol"),
    _c("C2H4(OH)2", "Ethylene glycol", "C2H4(OH)2", "ethylene_glycol"),
    _c("C3H6(OH)2", "Propylene glycol", "C3H6(OH)2", "propylene_glycol"),
    _c("C5H10(OH)2", "1,5-Pentanediol", "C5H10(OH)2", "pentanediol"),
    _c("C3H5(OH)3", "Glycerol", "C3H5(OH)3", "glycerol"),
    # --- ethers, ketones, acids, anhydrides, esters, amines, nitriles, others
    _c("C4H8O", "Tetrahydrofuran", "C4H8O", "tetrahydrofuran"),
    _c("C4H8O2-dioxane", "1,4-Dioxane", "C4H8O2", "dioxane"),
    _c("C3H6O", "Acetone", "C3H6O", "acetone"),
    _c("C2H4O2", "Acetic acid", "C2H4O2", "acetic_acid"),
    _c("C5H10O2-valeric", "Valeric acid", "C5H10O2", "valeric_acid"),
    _c("C6H12O2", "Caproic acid (hexanoic acid)", "C6H12O2", "caproic_acid", pubchem_name="Hexanoic acid"),
    _c("C7H14O2", "Enanthic acid (heptanoic acid)", "C7H14O2", "enanthic_acid", pubchem_name="Heptanoic acid"),
    _c("C8H16O2", "Caprylic acid (octanoic acid)", "C8H16O2", "caprylic_acid", pubchem_name="Octanoic acid"),
    _c("C9H18O2", "Pelargonic acid (nonanoic acid)", "C9H18O2", "pelargonic_acid", pubchem_name="Nonanoic acid"),
    _c("C18H34O2", "Oleic acid", "C18H34O2", "oleic_acid", note="measured as ~1 um droplets / aerosol, i.e. liquid"),
    _c("C4F6O3", "Trifluoroacetic anhydride", "(CF3CO)2O", "trifluoroacetic_anhydride"),
    _c("C4H8O2-etac", "Ethyl acetate", "C4H8O2", "ethyl_acetate"),
    _c("C5H10O2-ipac", "Isopropyl acetate", "C5H10O2", "propyl_acetate",
       note="the book is titled 'Propyl acetate (PAC, IPAC)' and its name list starts with n-propyl acetate, but its only page states isopropyl acetate"),
    _c("C8H8O3", "Methyl salicylate", "C8H8O3", "methyl_salicylate"),
    _c("C9H10O3", "Ethyl salicylate", "C9H10O3", "ethyl_salicylate"),
    _c("C11H12O2", "Ethyl cinnamate", "C11H12O2", "ethyl_cinnamate"),
    _c("C12H14O4", "Diethyl phthalate", "C12H14O4", "diethyl_phthalate"),
    _c("C8H19NO", "2-(Diisopropylamino)ethanol", "C8H19NO", "diisopropylaminoethanol",
       note="the book's about.yml lists ethanol's names and formula (a copy error); the catalog title, folder and data are DIPA "
            "(n = 1.43 at 2 um, where the same paper's ethanol page gives 1.31)"),
    _c("C2H3N", "Acetonitrile", "C2H3N", "acetonitrile"),
    _c("C2Cl3N", "Trichloroacetonitrile", "C2Cl3N", "trichloroacetonitrile"),
    _c("C2H6OS", "Dimethyl sulfoxide", "C2H6OS", "dimethyl_sulfoxide"),
    _c("C3H7NO", "N,N-Dimethylformamide", "C3H7NO", "dimethylformamide"),
    _c("C3H9O3P", "Dimethyl methylphosphonate", "C3H9O3P", "dimethyl_methylphosphonate"),
    _c("C4H10O3S", "Diethyl sulfite", "C4H10O3S", "diethyl_sulfite"),
    _c("C7H17O3P", "Diisopropyl methylphosphonate", "C7H17O3P", "diisopropyl_methylphosphonate"),
    _c("C9H8O", "Cinnamaldehyde", "C9H8O", "cinnamaldehyde"),
    # --- biomolecules
    _c("C9H11NO3", "L-Tyrosine", "C9H11NO3", "tyrosine", materialclass="biomolecule", note="measured as a film"),
    _c("CH4N2O", "Urea", "CH4N2O", "urea", materialclass="biomolecule", note="single crystal, uniaxial (o/e)"),
    _c("C12H24O12", "Lactose monohydrate", "C12H24O12", "lactose_monohydrate", materialclass="biomolecule", note="measured as a powder"),
    _c("DNA", "DNA (sodium salt, calf thymus)", None, "DNA", shelf="other", materialclass="biomacromolecule", pubchem_name=False,
       note="dry film; a biopolymer with no single molecular formula"),
    _c("silk-Bm", "Silk fibroin (Bombyx mori)", None, "Bombyx_mori", shelf="other", materialclass="biomacromolecule", pubchem_name=False,
       note="fibroin films; a protein with no single molecular formula"),
    _c("silk-Am", "Silk fibroin (Antheraea mylitta)", None, "Antheraea_mylitta", shelf="other", materialclass="biomacromolecule", pubchem_name=False),
    _c("silk-Sr", "Silk fibroin (Samia ricini)", None, "Samia_ricini", shelf="other", materialclass="biomacromolecule", pubchem_name=False),
    _c("silk-Aa", "Silk fibroin (Antheraea assamensis)", None, "Antheraea_assamensis", shelf="other", materialclass="biomacromolecule", pubchem_name=False),
]

# Pages inside a loaded book that are NOT loaded, with the reason.
EXCLUDED_PAGES = {
    ("organic", "hexane", "Chang"): "isomer not stated on the page (hexane); the book's other pages are n-hexane",
    ("organic", "butanol", "El-Kashef"): "isomer not stated on the page (butanol); the book holds both 1-butanol and isobutanol",
    ("main", "CS2", "Chemnitz"): ("the Sellmeier fit (stated for 0.3-12 um) has a pole inside its range at CS2's ~6.5 um absorption band: n^2 <= 0 "
                                  "from 6.477 to 6.592 um and n > 5 up to 6.605 um, which the pipeline would store as floored n ~1e-15. Same "
                                  "open decision as GaSe (load the fit with that window removed?); CS2's other three papers are loaded"),
}

# refractiveindex.info books in this area deliberately NOT in this family, with the reason.
_GAS = "gas at room temperature (a gases family)"
_MIX = "mixture with no single composition (needs a composition decision: a mixtures family)"
OUT_OF_FAMILY = {
    **{k: _GAS for k in ("organic/methane", "organic/ethane", "organic/ethylene", "organic/acetylene", "main/H2", "main/D2", "main/NH3")},
    **{k: "only a cryogenic or molten liquid page in a book of an element that is a gas or solid at room temperature"
       for k in ("main/Ar", "main/Kr", "main/Xe", "main/Na")},
    **{k: "solid inorganic hydride" for k in ("main/MgH2", "main/TiH2")},
    **{k: "organic molecular solid that is not a biomolecule (a molecular-solids family)" for k in (
        "organic/potassium_hydrogen_phthalate", "organic/SQIB", "organic/ProSQ-C16", "organic/rhodamine_6g")},
    "organic/acetaminophen": "powder dispersed in microcrystalline cellulose (a mixture), not the pure compound",
    **{k: "solid organic charge-transfer salt, not a liquid or biomolecule" for k in ("other/Cu-C12H4N4", "other/Li-C12H4N4")},
    **{k: _MIX for k in ("other/H2O-C3H5_OH_3", "other/D2O-C3H5_OH_3", "other/PBS", "other/BME", "other/Leica_Type_F", "other/Olympus_IMMOIL-F30CC",
                         "other/Sigma_Aldrich_M5904", "other/TherminolVP-1", "other/biodisel", "other/Eukitt", "other/FluorSave", "specs/Cargille")},
    **{k: "liquid crystal: anisotropic, temperature-dependent phases (a liquid-crystals family); E7, E44 and the MLC/TL grades are mixtures"
       for k in ("other/5CB", "other/5PCH", "other/E7", "other/E44", "other/MLC-6241-000", "other/MLC-6608", "other/MLC-9200-000",
                 "other/MLC-9200-100", "other/TL-216")},
    **{k: "biological tissue: a mixture with no single composition (a biological-tissues family)"
       for k in ("other/blood", "other/adipose_tissue", "other/liver", "other/colon")},
}
