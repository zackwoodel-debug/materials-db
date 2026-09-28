#!/usr/bin/env python3
"""
scripts/release_descriptors.py
===============================
Builds one chemical_descriptors row per material for the release DB (schema frozen: the RDKit-style columns, morgan_fp and a
free-form descriptor_json). Every material gets a row. A descriptor that does not apply, or whose input is missing, is NULL in
its column and explained in descriptor_json -- never guessed, never zero-filled.

descriptor_json sections:
  compositional  element-property statistics of the formula (pymatgen element data), for every material with a usable formula
                 (polymers: per repeat unit).
  structural     crystal-structure descriptors of the Materials Project entry the family build already chose (cached by
                 scripts/fetch_mp_structure_descriptors.py). 'applies_to' says whether that entry IS the material or is only a
                 crystalline reference for a film / amorphous / non-bulk sample.
  molecular      RDKit descriptors of a molecule (liquids and biomolecules: PubChem's SMILES) or of a polymer repeat unit
                 (data/descriptors/polymer_repeat_units.csv, each checked against the source formula). Not computed for extended inorganic solids: a PubChem SMILES such as [Na+].[Cl-] is formula-unit
                 notation, and TPSA / logP / H-bond counts of it describe no property of the solid. 'extended' (v2) adds the
                 Crippen molar refractivity (an estimate of polarizability from structure alone, never from a measured n),
                 sp3 fraction, valence electrons, ring / heteroatom / aromatic-atom counts, charge and topological indices.
  chemistry      (v2, inorganic compounds) Pauling ionic character of the most polar bond, and pymatgen's oxidation-state
                 guess WITH the number of charge-balanced alternatives: a guess, not a determination (Ge2Sb2Te5's top guess
                 Ge+4/Sb+1 is chemically wrong), so it is for reading, not a feature.

exact_mass and heavy_atom_count are defined for any formula unit, so inorganic materials get them from the formula
(most-common-isotope masses, as RDKit's ExactMolWt uses).
"""
import csv
import json
import math
import re
import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
MP_CACHE = _ROOT / "data" / "descriptors" / "mp_structural.json"
MP_EXTRAS = _ROOT / "data" / "descriptors" / "mp_structure_extras.json"  # v2: local environment + elastic moduli per entry
REPEAT_UNITS = _ROOT / "data" / "descriptors" / "polymer_repeat_units.csv"
FORMULA_ISSUES = _ROOT / "data" / "descriptors" / "formula_issues.csv"  # recorded formulas that are known to be wrong
SCHEMA_TAG = "materials-db descriptors v2"  # v2: more element properties, extended molecular block, chemistry block
MORGAN_RADIUS, MORGAN_BITS = 2, 2048  # same as scripts/populate_chemical_descriptors.py

NOBLE_GAS_Z = {"He": 2, "Ne": 10, "Ar": 18, "Kr": 36, "Xe": 54, "Rn": 86}


def valence_electrons(el, orbital=None):
    """Electrons outside the noble-gas core ('[Xe].4f14.5d10.6s2.6p2' -> f 14, d 10, s 2, p 2; 28 in all), the convention of
    the Magpie element features. orbital: 's' / 'p' / 'd' / 'f', or None for all of them."""
    parts = str(el.electronic_structure).split(".")
    if parts[0].startswith("["):
        parts = parts[1:]
    total = 0
    for p in parts:
        m = re.fullmatch(r"\d+([spdf])(\d+)", p)
        if m is None:
            raise ValueError(f"unparsed electronic structure {el.electronic_structure!r}")
        if orbital is None or m.group(1) == orbital:
            total += int(m.group(2))
    return total


# (json key, pymatgen Element attribute or function of the Element, unit)
ELEMENT_PROPERTIES = [
    ("atomic_number", "Z", None), ("atomic_mass", "atomic_mass", "u"), ("electronegativity_pauling", "X", None),
    ("period", "row", None), ("group", "group", None), ("mendeleev_number", "mendeleev_no", None),
    ("atomic_radius", "atomic_radius", "angstrom"),
    # v2
    ("first_ionization_energy", lambda e: e.ionization_energies[0] if e.ionization_energies else None, "eV"),
    ("electron_affinity", "electron_affinity", "eV"),  # negative where the anion is unbound (noble gases)
    ("molar_volume", "molar_volume", "cm3/mol"),  # of the element in its standard state
    ("van_der_waals_radius", "van_der_waals_radius", "angstrom"),
    ("valence_electrons", valence_electrons, None),
    ("valence_s_electrons", lambda e: valence_electrons(e, "s"), None),
    ("valence_p_electrons", lambda e: valence_electrons(e, "p"), None),
    ("valence_d_electrons", lambda e: valence_electrons(e, "d"), None),
    ("valence_f_electrons", lambda e: valence_electrons(e, "f"), None),
]
MOLECULAR_COLUMNS = ["tpsa", "logp", "rotatable_bonds", "hbond_donors", "hbond_acceptors", "aromatic_rings", "morgan_fp"]


def repeat_formula(formula):
    """'(C8H8)n' -> 'C8H8'. Returns (formula, None) or (None, reason)."""
    if formula is None or (isinstance(formula, float) and math.isnan(formula)) or not str(formula).strip():
        return None, "composition not stated by the source (proprietary or unspecified formulation)"
    f = str(formula).strip()
    if re.search(r"\)[nm]\s*-\s*\(", f):
        return None, f"copolymer '{f}': the comonomer ratio is not stated, so there is no single repeat-unit composition"
    m = re.fullmatch(r"\((.+)\)n", f)
    return (m.group(1) if m else f), None


def compositional(formula):
    from pymatgen.core import Composition, Element
    comp = Composition(formula)
    fracs = {el.symbol: comp.get_atomic_fraction(el) for el in comp.elements}
    out = dict(formula_unit=formula, n_elements=len(fracs), atoms_per_formula_unit=round(comp.num_atoms, 6),
               element_fractions={k: round(v, 6) for k, v in sorted(fracs.items())},
               stoichiometry_l2_norm=round(sum(f ** 2 for f in fracs.values()) ** 0.5, 6),
               stoichiometry_l3_norm=round(sum(f ** 3 for f in fracs.values()) ** (1 / 3), 6))
    missing = []
    for key, attr, unit in ELEMENT_PROPERTIES:
        vals = {}
        for el in comp.elements:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                v = attr(el) if callable(attr) else getattr(el, attr, None)
            v = None if v is None else float(v)
            if v is None or math.isnan(v):
                missing.append(f"{key}:{el.symbol}")
                vals = None
                break
            vals[el.symbol] = v
        if vals is None:
            continue
        mean = sum(fracs[e] * v for e, v in vals.items())
        out[key] = dict(mean=round(mean, 6), min=round(min(vals.values()), 6), max=round(max(vals.values()), 6),
                        range=round(max(vals.values()) - min(vals.values()), 6),
                        mean_abs_deviation=round(sum(fracs[e] * abs(v - mean) for e, v in vals.items()), 6), unit=unit)
    if missing:
        out["unavailable_element_data"] = missing
    blocks = {b: 0.0 for b in "spdf"}
    for el, f in fracs.items():
        blocks[Element(el).block] += f
    out["block_fractions"] = {b: round(v, 6) for b, v in blocks.items()}  # atom fraction of s-, p-, d- and f-block elements
    return out


def _formula_amounts(formula):
    from pymatgen.core import Composition
    return list(Composition(formula).values())


def chemistry(formula):
    """Inorganic compounds: Pauling ionic character of the most polar pair, and the oxidation-state guess (a guess)."""
    from pymatgen.core import Composition
    comp = Composition(formula)
    xs = [el.X for el in comp.elements]
    out = dict(basis="formula unit; pymatgen element data and oxidation-state guesses")
    if all(x is not None and not math.isnan(x) for x in xs):
        dx = max(xs) - min(xs)
        out["max_electronegativity_difference"] = round(dx, 6)
        out["pauling_ionic_character"] = round(1 - math.exp(-dx ** 2 / 4), 6)  # Pauling: 1 - exp(-(dX)^2 / 4)
    if any(abs(v - round(v)) > 1e-9 for v in comp.values()):
        out["oxidation_state_guess"] = None
        out["oxidation_state_note"] = ("not attempted: a fractional composition (solid solution); its end members' oxidation "
                                       "states apply")
        return out
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        guesses = comp.oxi_state_guesses()
    out["n_oxidation_state_guesses"] = len(guesses)
    if guesses:
        out["oxidation_state_guess"] = {k: round(float(v), 6) for k, v in sorted(guesses[0].items())}
        out["oxidation_state_note"] = ("pymatgen's most probable charge-balanced assignment (ICSD statistics); a guess, not a "
                                       "determination" + ("; other assignments also balance" if len(guesses) > 1 else ""))
    else:
        out["oxidation_state_guess"] = None
        out["oxidation_state_note"] = "no charge-balanced assignment from common oxidation states (metallic / intermetallic?)"
    return out


def formula_mass_and_heavy_atoms(formula):
    """Monoisotopic formula-unit mass (most common isotope, as RDKit ExactMolWt) and non-H atom count."""
    from pymatgen.core import Composition
    from rdkit import Chem
    pt = Chem.GetPeriodicTable()
    comp = Composition(formula)
    if any(abs(n - round(n)) > 1e-9 for n in comp.values()):
        return None, None  # non-integer stoichiometry: no discrete formula unit
    mass = sum(pt.GetMostCommonIsotopeMass(el.symbol) * n for el, n in comp.items())
    heavy = int(sum(n for el, n in comp.items() if el.symbol != "H"))
    return round(mass, 6), heavy


def molecular(smiles):
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdFingerprintGenerator, rdMolDescriptors
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"unparseable SMILES {smiles!r}")
    # bit-identical to AllChem.GetMorganFingerprintAsBitVect(radius=2, nBits=2048), the call populate_chemical_descriptors.py uses
    fp = rdFingerprintGenerator.GetMorganGenerator(radius=MORGAN_RADIUS, fpSize=MORGAN_BITS).GetFingerprint(mol)
    return dict(exact_mass=round(Descriptors.ExactMolWt(mol), 6), heavy_atom_count=mol.GetNumHeavyAtoms(),
                tpsa=round(Descriptors.TPSA(mol), 4), logp=round(Descriptors.MolLogP(mol), 4),
                rotatable_bonds=int(rdMolDescriptors.CalcNumRotatableBonds(mol)), hbond_donors=int(rdMolDescriptors.CalcNumHBD(mol)),
                hbond_acceptors=int(rdMolDescriptors.CalcNumHBA(mol)), aromatic_rings=int(rdMolDescriptors.CalcNumAromaticRings(mol)),
                morgan_fp=fp.ToBitString())


def molecular_extended(smiles):
    """v2 molecular descriptors (in descriptor_json only; the table's columns are frozen). A polymer repeat unit's [*]
    attachment atoms contribute nothing (Crippen gives them 0 and they carry no hydrogens), so values are per repeat unit."""
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, GraphDescriptors, rdMolDescriptors
    mol = Chem.MolFromSmiles(smiles)
    heavy = [a for a in mol.GetAtoms() if a.GetAtomicNum() > 1]
    r = lambda v: round(float(v), 6)  # noqa: E731
    return dict(
        molar_refractivity_crippen=r(Crippen.MolMR(mol)),  # cm3/mol; Wildman & Crippen 1999 atomic contributions
        average_mol_weight=r(Descriptors.MolWt(mol)), valence_electrons=int(Descriptors.NumValenceElectrons(mol)),
        fraction_csp3=r(rdMolDescriptors.CalcFractionCSP3(mol)), heteroatoms=int(rdMolDescriptors.CalcNumHeteroatoms(mol)),
        rings=int(rdMolDescriptors.CalcNumRings(mol)),
        aromatic_atom_fraction=r(sum(a.GetIsAromatic() for a in heavy) / len(heavy)) if heavy else 0.0,
        formal_charge=int(Chem.GetFormalCharge(mol)), labute_asa=r(rdMolDescriptors.CalcLabuteASA(mol)),
        bertz_ct=r(GraphDescriptors.BertzCT(mol)), balaban_j=r(GraphDescriptors.BalabanJ(mol)),
        kappa1=r(rdMolDescriptors.CalcKappa1(mol)), kappa2=r(rdMolDescriptors.CalcKappa2(mol)),
        kappa3=r(rdMolDescriptors.CalcKappa3(mol)), chi0v=r(rdMolDescriptors.CalcChi0v(mol)), chi1v=r(rdMolDescriptors.CalcChi1v(mol)),
        units=dict(molar_refractivity_crippen="cm3/mol", average_mol_weight="g/mol", labute_asa="angstrom2"))


def load_inputs():
    mp = json.loads(MP_CACHE.read_text())
    extras = json.loads(MP_EXTRAS.read_text())
    if extras["mp_database_version"] != mp["mp_database_version"] or extras["volume_drift_vs_base_cache"]:
        raise ValueError("mp_structure_extras.json is from another MP database than mp_structural.json (or its structures drifted): "
                         "refetch both")
    mp["extras"] = {k: {kk: vv for kk, vv in v.items() if kk != "structure"} for k, v in extras["entries"].items()}
    with open(REPEAT_UNITS, newline="") as f:
        units = {r["material_name"]: r for r in csv.DictReader(f)}
    with open(FORMULA_ISSUES, newline="") as f:
        issues = {r["material_name"]: r for r in csv.DictReader(f)}
    return mp, units, issues


def _structural_scope(density_source, label_words):
    """Is the chosen MP entry the material itself, or only a crystalline reference for the measured sample?
    Optical labels that call the sample amorphous / film / glass win over the density rule: Si3N4's density is crystalline
    beta (mp-988) while its optical data are an amorphous film, so beta is a reference, not the sample."""
    ds = str(density_source or "")
    if label_words:
        return ("crystalline reference only: optical dataset(s) describe the sample as " + "/".join(sorted(label_words))
                + " (the density rows, if any, describe this crystalline entry)")
    if ds == "MP_DFT":
        return "the material (the family build chose this entry as the sample's phase)"
    if ds == "bulk_elemental_approximation":
        return "crystalline reference only: the measured sample is a film / non-bulk form (its density is a bulk approximation)"
    return "crystalline reference (the density comes from the literature or experimental lattice parameters, not from this entry)"


MOLECULAR_FAMILIES = {"liquids"}
GLASS_FAMILIES = {"glasses", "glass_catalogs"}  # multicomponent glasses: no single formula, no crystal structure
FORMULATION_FAMILIES = {"optical_media"}  # proprietary liquids / cured resins: no single formula, no crystal structure
BIO_FAMILIES = {"bio_media"}  # biological fluids, tissues and buffers: mixtures, no formula, no crystal structure
LC_FAMILIES = {"liquid_crystals"}
SERIES_FAMILIES = {"alloys", "perovskites"}  # solid solutions, doped crystals, TCOs and halide perovskites (v0.17.0)
GAS_FAMILIES = {"gases"}  # compound gases are molecules (PubChem SMILES); elemental gases are elements; air is a mixture  # single compounds are molecules (PubChem SMILES); the commercial mixtures are formulations  # families whose materials are discrete molecules (described by their PubChem SMILES)


def descriptor_row(name, formula, family, csv_row, optical_labels, mp, units, issues, smiles=None):
    """Return (columns dict, descriptor_json dict) for one material."""
    cols = {c: None for c in ["exact_mass", "heavy_atom_count"] + MOLECULAR_COLUMNS}
    is_polymer = family == "polymers"
    rf, why = repeat_formula(formula)
    if name in issues:  # a recorded formula known to be wrong feeds nothing
        rf, why = None, "recorded formula is suspect: " + issues[name]["issue"]
    label_words = {w for lab in optical_labels for w in ("amorphous", "film", "glass") if w in lab.lower()}
    doc = dict(descriptor_schema=SCHEMA_TAG, family=family, material_class=(csv_row or {}).get("materialclass") or None)

    # molecular (polymer repeat units only)
    unit = units.get(name) if is_polymer else None
    if unit:
        m = molecular(unit["repeat_unit_smiles"])
        cols.update(m)
        doc["material_kind"] = "polymer"
        doc["molecular"] = dict(basis="polymer repeat unit ([*] = attachment points; values per repeat unit)",
                                smiles=unit["repeat_unit_smiles"], structure_basis=unit["structure_basis"], note=unit["note"] or None,
                                morgan_radius=MORGAN_RADIUS, morgan_bits=MORGAN_BITS, source="RDKit",
                                extended=molecular_extended(unit["repeat_unit_smiles"]))
    elif is_polymer:
        doc["material_kind"] = "polymer"
        doc["molecular"] = dict(unavailable=why or "repeat-unit structure not curated")
    elif family in MOLECULAR_FAMILIES | LC_FAMILIES | GAS_FAMILIES and rf and smiles and len(re.findall(r"[A-Z][a-z]?", rf)) > 1:
        cols.update(molecular(smiles))
        doc["material_kind"] = "molecule"
        doc["molecular"] = dict(basis="the molecule (PubChem isomeric SMILES; isotopes and stereochemistry as PubChem records them)",
                                smiles=smiles, morgan_radius=MORGAN_RADIUS, morgan_bits=MORGAN_BITS, source="RDKit",
                                extended=molecular_extended(smiles))
    elif family in LC_FAMILIES:
        doc["material_kind"] = "commercial formulation"
        doc["molecular"] = dict(unavailable="commercial liquid-crystal mixture: no single molecular structure")
    elif family in GAS_FAMILIES and rf:
        doc["molecular"] = dict(not_applicable="an elemental gas (single atoms or homonuclear molecules)")
    elif family in GAS_FAMILIES:
        doc["material_kind"] = "gas mixture"
        doc["molecular"] = dict(not_applicable="a gas mixture, not a single molecule")
    elif family in FORMULATION_FAMILIES | BIO_FAMILIES:
        doc["molecular"] = dict(not_applicable="a mixture (commercial formulation, biological fluid, tissue or buffer), not a single molecule")
    elif family in MOLECULAR_FAMILIES and not rf:
        doc["material_kind"] = "biomacromolecule"
        doc["molecular"] = dict(unavailable=why or "no single molecular structure")
    elif family in MOLECULAR_FAMILIES:
        doc["molecular"] = dict(not_applicable="a liquid element (metal), not a molecule")
    else:
        doc["molecular"] = dict(not_applicable="extended inorganic solid: molecular descriptors (TPSA, logP, H-bond counts, "
                                               "rotatable bonds, fingerprints) describe discrete molecules, not a crystal or glass")

    # compositional
    if rf:
        comp = compositional(rf)
        doc["compositional"] = comp
        if not is_polymer and doc.get("material_kind") != "molecule":
            doc["material_kind"] = "element" if comp["n_elements"] == 1 else "inorganic compound"
            if family in SERIES_FAMILIES:  # a fractional formula is a solid solution; C in a halide perovskite is its organic cation
                doc["material_kind"] = ("hybrid organic-inorganic perovskite" if "C" in comp["element_fractions"] else
                                        "solid solution" if any(abs(v - round(v)) > 1e-9 for v in _formula_amounts(rf)) else
                                        "inorganic compound")
        if cols["exact_mass"] is None:
            cols["exact_mass"], cols["heavy_atom_count"] = formula_mass_and_heavy_atoms(rf)
    elif family in GLASS_FAMILIES:
        doc["compositional"] = dict(unavailable="multicomponent glass: no single formula (composition proprietary or given as oxide ratios)")
        doc["material_kind"] = "glass"
    elif family in FORMULATION_FAMILIES | LC_FAMILIES:
        doc["compositional"] = dict(unavailable="proprietary commercial formulation: no single formula")
        doc["material_kind"] = "commercial formulation"
    elif family in GAS_FAMILIES:
        doc["compositional"] = dict(unavailable="a gas mixture (dry air): no single formula")
    elif family in BIO_FAMILIES:
        doc["compositional"] = dict(unavailable="biological fluid, tissue or buffer: a mixture, no single formula")
        doc["material_kind"] = "biological or buffer mixture"
    elif family in SERIES_FAMILIES:
        doc["compositional"] = dict(unavailable="doped crystal or conducting oxide: the source gives no exact composition "
                                                "(the dopant level is in the name)")
        doc["material_kind"] = "doped crystal or conducting oxide"
    else:
        doc["compositional"] = dict(unavailable=why or "no single molecular formula")
        doc.setdefault("material_kind", "polymer" if is_polymer else "unknown")

    # chemistry (v2): inorganic compounds and solid solutions only
    if doc.get("material_kind") in ("inorganic compound", "solid solution"):
        doc["chemistry"] = chemistry(rf)
    elif doc.get("material_kind") == "element":
        doc["chemistry"] = dict(not_applicable="an element: no bond polarity, oxidation state 0")
    elif rf:
        doc["chemistry"] = dict(not_applicable="a covalent molecule or polymer: formal oxidation states and ionic character are "
                                               "not descriptors of it (see the molecular block)")
    else:
        doc["chemistry"] = dict(unavailable="no single formula")

    # structural
    mp_id = (csv_row or {}).get("mp_id")
    mp_id = None if mp_id is None or (isinstance(mp_id, float) and math.isnan(mp_id)) else str(mp_id)
    if is_polymer:
        doc["structural"] = dict(not_applicable="polymer: no crystal structure (amorphous or semicrystalline solid)")
    elif family in MOLECULAR_FAMILIES and (csv_row or {}).get("materialclass") == "liquid":
        doc["structural"] = dict(not_applicable="liquid: no crystal structure (any ice / solid datasets of it are labelled by phase)")
    elif family in MOLECULAR_FAMILIES:
        doc["structural"] = dict(unavailable="molecular solid or biomolecule film/powder: no Materials Project entry is used for molecular crystals")
    elif family in GLASS_FAMILIES:
        doc["structural"] = dict(not_applicable="glass: amorphous, no crystal structure")
    elif family in FORMULATION_FAMILIES:
        doc["structural"] = dict(not_applicable="liquid or cured resin formulation: no crystal structure")
    elif family in LC_FAMILIES:
        doc["structural"] = dict(not_applicable="liquid crystal: no crystal structure")
    elif family in BIO_FAMILIES:
        doc["structural"] = dict(not_applicable="biological fluid, tissue or buffer: no crystal structure")
    elif family in GAS_FAMILIES:
        doc["structural"] = dict(not_applicable="gas (liquid / solid only at cryogenic temperatures): no crystal structure is used")
    elif mp_id and mp_id in mp["entries"]:
        e = dict(mp["entries"][mp_id])
        e.pop("space_group_number_recomputed", None)
        doc["structural"] = dict(source="Materials Project (DFT-calculated, not measured; CC BY 4.0)", mp_id=mp_id,
                                 mp_database_version=mp["mp_database_version"],
                                 applies_to=_structural_scope((csv_row or {}).get("density_source"), label_words), **e)
        x = mp.get("extras", {}).get(mp_id)
        if x is not None:  # v2 (scripts/fetch_mp_structure_extras.py): from the entry's own structure
            doc["structural"]["local_environment"] = {k: v for k, v in x.items() if k not in ("elastic", "volume_per_atom_angstrom3")}
            doc["structural"]["elastic"] = x["elastic"]
    else:
        doc["structural"] = dict(unavailable="no Materials Project entry was chosen for this material (amorphous/glass sample, or no "
                                             "entry passed the density-selection rules; see the family CSV flags)")
    for c in MOLECULAR_COLUMNS:
        if cols[c] is None:
            doc.setdefault("null_columns_reason", {})[c] = (doc["molecular"].get("not_applicable") and "not applicable") or "unavailable"
    return cols, doc
