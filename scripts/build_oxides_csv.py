#!/usr/bin/env python3
"""
scripts/build_oxides_csv.py
============================
Step 2 of the 50-oxide task: build data/oxides_50.csv.

Pulls from:
  - PubChem PUG REST (name -> cid/formula/mw/smiles/inchikey; xrefs -> CAS)
  - Materials Project (mp-api) for mp_id / space group / energy_above_hull / density
  - periodictable for x-ray and neutron SLD (real + imag) from formula + density
  - refractiveindex.info YAML (already cloned in refractiveindex_db/) for n,k at 633nm,
    per optical axis, using the Step 1 selections in data/step1_selections.json

Every external response is cached raw (data/raw_cache/) before parsing. Malformed,
empty, or rate-limited responses are quarantined (data/quarantine/) with a reason
and NEVER used as if they were valid.
"""

import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
import materials_db.pipeline.fetch_optical_data as _fetch_optical_data  # noqa: E402
from materials_db.pipeline.fetch_optical_data import parse_file  # noqa: E402

# fetch_optical_data.py clips dispersion data to a 200-3000nm window tuned for
# its own SPR/soft-matter use case. We need the native full range so a
# dataset that simply doesn't extend to 633nm (e.g. CuO's Brimhall data,
# 10-35nm deep-UV only) returns "no coverage" via NaN instead of parse_file
# raising "No n data found in any DATA block".
_fetch_optical_data.WL_MIN_NM = 0.01
_fetch_optical_data.WL_MAX_NM = 2_000_000.0

load_dotenv(_ROOT / ".env")

RI_DATA_ROOT = _ROOT / "refractiveindex_db" / "database" / "data"
SELECTIONS_PATH = _ROOT / "data" / "step1_selections.json"
RAW_CACHE = _ROOT / "data" / "raw_cache"
QUARANTINE = _ROOT / "data" / "quarantine"
OUT_CSV = _ROOT / "data" / "oxides_50.csv"

XRAY_ENERGY_KEV = 8.048  # Cu K-alpha, 1.5406 A
NEUTRON_WAVELENGTH_A = 1.798  # standard reference (2200 m/s thermal neutron)

PUBCHEM_RATE_DELAY = 0.25  # ~4 req/s, under the 5 req/s limit

# ---- 50 target materials (name, formula, polymorph) --------------------------
# Canonical source: scripts/oxide_material_list.py (shared with
# match_ri_info_oxides.py so the two can't drift apart again -- see that
# module's docstring for why this consolidation happened).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oxide_material_list import MATERIALS_50  # noqa: E402

MATERIALS = [{k: v for k, v in m.items() if k != "ri_aliases"} for m in MATERIALS_50]

# Forced "no legitimate MP match" materials: either the RI.info default
# dataset is amorphous/glass (auto-detected in Step 1, SiO confirmed
# manually), or MP's only/best entries are verified to NOT match the
# experimentally-known structure (CaGdAlO4/CaYAlO4 -- MP has only a
# theoretical, ICSD-unbacked I4mm entry, but the compound is well
# documented as centrosymmetric I4/mmm K2NiF4-type; Nb2O5's Franta 2024
# dataset is an unannealed sputtered film, almost certainly amorphous).
# Density must come from literature/experimental-lattice-parameter
# calculation, not MP, for all of these.
FORCE_NO_MP = {"SiO", "SiO2", "GeO2", "Ta2O5", "CaGdAlO4", "CaYAlO4", "Nb2O5"}

LITERATURE_DENSITY = {
    # g/cm3, note, optional citation dict (doi/title/authors/journal/year)
    "SiO2": (2.20, "literature: fused silica, standard value", None),
    "SiO": (2.13, "literature: evaporated amorphous SiO film, commonly cited value", None),
    "GeO2": (3.65, "literature: fused (vitreous) GeO2, commonly cited value", None),
    "Ta2O5": (7.90, "literature: amorphous Ta2O5 thin film, commonly cited value (vs 8.37 crystalline)", None),
    "CaGdAlO4": (
        5.971787,
        "experimental lattice params: I4/mmm K2NiF4-type, a=3.65855 A, c=11.9787 A, Z=2 "
        "(MP's only entry is a theoretical, ICSD-unbacked I4mm approximation of this "
        "Ca/Gd site-disordered structure; MP density 5.860 g/cm3 is ~1.9% low)",
        dict(doi="10.1016/S0925-8388(99)00701-X",
             title="Crystal structure and optical spectroscopy of CaGdAlO4:Er single crystal",
             authors="Vasylechko, L.; Kodama, N.; Matkovskii, A.; Zhydachevskii, Ya.",
             journal="Journal of Alloys and Compounds", year=2000),
    ),
    "CaYAlO4": (
        4.630187,
        "experimental lattice params: I4/mmm K2NiF4-type, a=3.6451 A, c=11.8743 A, Z=2 "
        "(MP's only entry is a theoretical, ICSD-unbacked I4mm approximation of this "
        "Ca/Y site-disordered structure; MP density 4.532 g/cm3 is ~2.1% low)",
        dict(doi="10.1016/0022-4596(92)90073-5",
             title="Dielectric constants and crystal structures of CaYAlO4, CaNdAlO4, and "
                    "SrLaAlO4, and deviations from the oxide additivity rule",
             authors="Shannon, R.D.; Oswald, R.A.; Parise, J.B.; Chai, B.H.T.; Byszewski, P.; "
                      "Pajaczkowska, A.; Sobolewski, R.",
             journal="Journal of Solid State Chemistry", year=1992),
    ),
    "Nb2O5": (
        4.45,
        "literature: stoichiometric amorphous Nb2O5 thin film density from XRR/RBS "
        "(amorphous inferred from the Franta 2024 RI.info dataset's deposition method -- "
        "magnetron sputtering, no anneal step mentioned in its RI.info comments; the Franta "
        "paper itself was not directly accessed to confirm)",
        dict(doi="10.1002/1521-396X(200112)188:3<1047::AID-PSSA1047>3.0.CO;2-J",
             title="Characterization of Niobium Oxide Films Prepared by Reactive DC Magnetron Sputtering",
             authors="Venkataraj, S.; Drese, R.; Kappertz, O.; Jayavel, R.; Wuttig, M.",
             journal="Physica Status Solidi (a)", year=2001),
    ),
}

# formula -> (experimental density g/cm3, note, citation dict) to use INSTEAD
# of MP_DFT density, while still keeping the matched MP structure (space
# group / energy_above_hull) for provenance.
EXPERIMENTAL_DENSITY_OVERRIDE = {
    "BiB3O6": (
        5.0263,
        "experimental lattice params: alpha-BiBO, C2, a=7.120 A, b=4.995 A, c=6.508 A, "
        "beta=105.59 deg, Z=2",
        dict(doi="10.1107/S0108270184004078",
             title="Die Kristallstruktur von Wismutborat, BiB3O6",
             authors="Froehlich, R.; Bohaty, L.; Liebertz, J.",
             journal="Acta Crystallographica Section C", year=1984),
    ),
}

# formula -> note appended when we override MP's default (lowest-hull or
# otherwise) polymorph pick with additional context beyond the generic
# EXPECTED_SPACEGROUP mismatch message.
REJECTED_ALTERNATE_NOTE = {
    "BiB3O6": "mp-554718 (Pca2_1 #29, Knyrim et al. 2006 'a new non-centrosymmetric MODIFICATION "
              "of BiB3O6') rejected as a distinct, non-standard polymorph -- not the commercial "
              "NLO crystal our Umemura et al. 2007 optical data was measured on",
}

# formula -> note confirming MP's structure was verified against independent
# provenance (ICSD / same research group), even though no better alternative
# was found and density stays MP_DFT.
PROVENANCE_CONFIRMED_NOTE = {
    "BeAl6O10": "MP structure (mp-560974, P2_1/c #14) sourced from ICSD-95408 (Alimpiev et al. "
                "2002, J. Cryst. Growth 237, 884-889), same research group (Pestryakov) as the "
                "optical dataset used here -- accepted with high confidence. Could not obtain "
                "experimental lattice parameters (paper paywalled, not in COD) to compute an "
                "experimental density, so density_source remains MP_DFT.",
}

# Expected space-group numbers for the intended polymorph, used to pick the
# correct Materials Project entry instead of blindly taking lowest energy
# above hull (see TiO2: anatase mp-390 is lowest-hull but our RI.info data is
# rutile mp-2657). None = no strong prior, just flag for review.
EXPECTED_SPACEGROUP = {
    "Al2O3": ([167], "corundum"),
    "BeO": ([186], "wurtzite"),
    "MgAl2O4": ([227], "spinel"),
    "BeAl2O4": ([62], "chrysoberyl (olivine-type)"),
    "BaB2O4": ([161], "beta-BBO, noncentrosymmetric NLO phase -- NOT the centrosymmetric R-3c #167 alpha phase which is lowest energy_above_hull in MP but has no second-harmonic activity"),
    "LaAlO3": ([167], "rhombohedral room-temperature phase -- MP's lowest-hull entry is a different (Imma #74) distortion"),
    "LiIO3": ([173], "hexagonal NLO/piezoelectric phase, consistent with our o/e uniaxial RI.info data -- MP's lowest-hull entry (P42/n #86, tetragonal) is a different, incompatible symmetry"),
    "CsLiB6O10": ([122], "tetragonal CLBO -- MP's lowest-hull entry (#24) is a different polymorph"),
    "Bi12GeO20": ([197], "sillenite"),
    "Pb5Ge3O11": ([143], "trigonal ferroelectric"),
    "BiB3O6": ([5], "alpha-BiBO, monoclinic C2 (Froehlich/Bohaty/Liebertz 1984, 10 ICSD entries) "
                     "-- NOT the lowest-hull Pca2_1 #29, a distinct 'new modification' (Knyrim 2006)"),
    "LiB3O5": ([33], "orthorhombic LBO"),
    "CaCO3": ([167], "calcite"),
    "CuO": ([15], "tenorite"),
    "Cu2O": ([224], "cuprite"),
    "Dy2O3": ([206], "bixbyite"),
    "Fe2O3": ([167], "hematite"),
    "Fe3O4": ([227], "inverse spinel / magnetite"),
    "Lu2O3": ([206], "bixbyite"),
    "Lu3Al5O12": ([230], "garnet"),
    "MgO": ([225], "rock salt"),
    "CaMoO4": ([88], "scheelite"),
    "PbMoO4": ([88], "scheelite"),
    "SrMoO4": ([88], "scheelite"),
    "LiNbO3": ([161], "trigonal ferroelectric"),
    "Sc2O3": ([206], "bixbyite"),
    "TiO2": ([136], "rutile"),
    "BaTiO3": ([99], "tetragonal ferroelectric"),
    "SrTiO3": ([221], "cubic perovskite"),
    "VO2": ([14], "M1 monoclinic insulating phase"),
    "YVO4": ([141], "zircon"),
    "Y2O3": ([206], "bixbyite"),
    "Y3Al5O12": ([230], "garnet"),
    "Tb3Ga5O12": ([230], "garnet"),
    "ZnO": ([186], "wurtzite"),
    "HfO2": ([14], "monoclinic baddeleyite"),
    "TeO2": ([92], "paratellurite"),
    "WO3": ([14, 15], "monoclinic gamma-WO3"),
    "MoO3": ([62], "orthorhombic alpha-MoO3"),
    "MoO2": ([14], "monoclinic rutile-distorted"),
    "KNbO3": ([38], "orthorhombic ferroelectric"),
}

NEUTRON_ABSORBERS = {"Gd", "Dy", "B", "Li"}

FLAG_JOIN = "; "


def ensure_dirs():
    for sub in ["pubchem", "mp", "ri_info"]:
        (RAW_CACHE / sub).mkdir(parents=True, exist_ok=True)
        (QUARANTINE / sub).mkdir(parents=True, exist_ok=True)


def quarantine(kind: str, key: str, reason: str, payload):
    path = QUARANTINE / kind / f"{key}.json"
    path.write_text(json.dumps({"reason": reason, "payload": payload}, indent=2, default=str))


def parse_formula_counts(formula: str) -> dict:
    """Recursive-descent formula parser supporting nested parentheses,
    e.g. LuAl3(BO3)4 -> {Lu:1, Al:3, B:4, O:12}."""
    tokens = re.findall(r"[A-Z][a-z]?|\d+|\(|\)", formula)
    pos = 0

    def parse_group():
        nonlocal pos
        counts = {}
        while pos < len(tokens) and tokens[pos] != ")":
            tok = tokens[pos]
            if tok == "(":
                pos += 1
                sub = parse_group()
                pos += 1  # skip ")"
                mult = 1
                if pos < len(tokens) and tokens[pos].isdigit():
                    mult = int(tokens[pos])
                    pos += 1
                for el, c in sub.items():
                    counts[el] = counts.get(el, 0) + c * mult
            else:
                pos += 1
                mult = 1
                if pos < len(tokens) and tokens[pos].isdigit():
                    mult = int(tokens[pos])
                    pos += 1
                counts[tok] = counts.get(tok, 0) + mult
        return counts

    return parse_group()


def formulas_match(target: str, pubchem_formula: str) -> bool:
    try:
        a = parse_formula_counts(target)
        b = parse_formula_counts(pubchem_formula)
    except Exception:
        return False
    return a == b


def _walk_cas_sections(section: dict, out: list):
    if section.get("TOCHeading") == "CAS":
        for info in section.get("Information", []):
            for s in info.get("Value", {}).get("StringWithMarkup", []):
                if s.get("String") and re.match(r"^\d{2,7}-\d{2}-\d$", s["String"]):
                    out.append(s["String"])
    for sub in section.get("Section", []):
        _walk_cas_sections(sub, out)


# ---- PubChem -------------------------------------------------------------

def fetch_pubchem(mat: dict) -> dict:
    name = mat["pubchem_name"]
    formula = mat["formula"]
    cache_key = mat["formula"]
    out = dict(pubchem_cid=None, smiles=None, inchikey=None, cas_number=None,
               molecular_weight=None, pubchem_formula_match=None, flags=[])

    def get(url):
        time.sleep(PUBCHEM_RATE_DELAY)
        r = requests.get(url, timeout=10)
        return r

    try:
        r = get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/cids/JSON")
        if r.status_code == 404:
            out["flags"].append("pubchem: not found by name")
            return out
        if r.status_code == 429:
            quarantine("pubchem", cache_key, "rate_limited_cid_lookup", r.text)
            out["flags"].append("pubchem: rate-limited, quarantined")
            return out
        if r.status_code != 200:
            quarantine("pubchem", cache_key, f"cid_lookup_http_{r.status_code}", r.text)
            out["flags"].append(f"pubchem: HTTP {r.status_code} on cid lookup, quarantined")
            return out
        data = r.json()
        (RAW_CACHE / "pubchem" / f"{cache_key}_cids.json").write_text(json.dumps(data, indent=2))
        cid = data.get("IdentifierList", {}).get("CID", [None])[0]
        if not cid:
            quarantine("pubchem", cache_key, "malformed_cid_response", data)
            out["flags"].append("pubchem: malformed CID response, quarantined")
            return out

        r2 = get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,SMILES,InChIKey/JSON")
        if r2.status_code != 200:
            quarantine("pubchem", cache_key, f"property_lookup_http_{r2.status_code}", r2.text)
            out["flags"].append(f"pubchem: HTTP {r2.status_code} on property lookup, quarantined")
            return out
        pdata = r2.json()
        (RAW_CACHE / "pubchem" / f"{cache_key}_properties.json").write_text(json.dumps(pdata, indent=2))
        props_list = pdata.get("PropertyTable", {}).get("Properties", [])
        if not props_list:
            quarantine("pubchem", cache_key, "empty_properties_response", pdata)
            out["flags"].append("pubchem: empty properties response, quarantined")
            return out
        props = props_list[0]

        pubchem_formula = props.get("MolecularFormula", "")
        match = formulas_match(formula, pubchem_formula)
        out["pubchem_formula_match"] = match
        out["pubchem_cid"] = cid
        out["molecular_weight"] = float(props["MolecularWeight"]) if props.get("MolecularWeight") else None
        out["smiles"] = props.get("SMILES")
        out["inchikey"] = props.get("InChIKey")

        if not match:
            out["flags"].append(f"pubchem: formula mismatch (target={formula}, pubchem={pubchem_formula}) -- pubchem fields NULLed")
            out["pubchem_cid"] = None
            out["molecular_weight"] = None
            out["smiles"] = None
            out["inchikey"] = None
            return out

        r3 = get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=CAS")
        if r3.status_code == 404:
            pass  # genuinely no curated CAS section on file -- not an error, leave NULL
        elif r3.status_code == 429:
            quarantine("pubchem", f"{cache_key}_cas", "rate_limited_cas_lookup", r3.text)
            out["flags"].append("pubchem: rate-limited on CAS lookup, quarantined -- cas_number left NULL, retry the pipeline")
        elif r3.status_code != 200:
            quarantine("pubchem", f"{cache_key}_cas", f"cas_lookup_http_{r3.status_code}", r3.text)
            out["flags"].append(f"pubchem: HTTP {r3.status_code} on CAS lookup, quarantined -- cas_number left NULL")
        else:
            rdata = r3.json()
            (RAW_CACHE / "pubchem" / f"{cache_key}_cas.json").write_text(json.dumps(rdata, indent=2))
            cas_values = []
            try:
                for sect in rdata["Record"]["Section"]:
                    _walk_cas_sections(sect, cas_values)
            except (KeyError, TypeError):
                pass
            if cas_values:
                out["cas_number"] = cas_values[0]
                if len(cas_values) > 1:
                    out["flags"].append(f"pubchem: {len(cas_values)} CAS numbers in PUG-View record, took first/primary ({cas_values[0]})")

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        quarantine("pubchem", cache_key, f"exception: {type(e).__name__}: {e}", None)
        out["flags"].append(f"pubchem: exception {type(e).__name__}, quarantined")

    return out


# ---- Materials Project -----------------------------------------------------

def fetch_mp(mat: dict, mpr) -> dict:
    formula = mat["formula"]
    out = dict(mp_id=None, mp_space_group=None, mp_energy_above_hull_ev=None,
               density_g_cm3=None, density_source=None, density_citation=None, flags=[])

    if formula in FORCE_NO_MP:
        lit_density, lit_note, citation = LITERATURE_DENSITY[formula]
        out["density_g_cm3"] = lit_density
        out["density_source"] = "experimental lattice params" if "experimental lattice params" in lit_note else "literature"
        out["density_citation"] = citation
        out["flags"].append(f"no MP structure match. Density = {lit_density} g/cm3 ({lit_note}). "
                             f"Verify before use.")
        return out

    query_formula = re.sub(r"[()]", "", formula)  # MP formula search wants flat formula
    try:
        docs = mpr.materials.summary.search(
            formula=query_formula,
            fields=["material_id", "formula_pretty", "symmetry", "energy_above_hull", "density"],
        )
    except Exception as e:
        quarantine("mp", formula, f"exception: {type(e).__name__}: {e}", None)
        out["flags"].append(f"MP query failed ({type(e).__name__}), quarantined")
        return out

    if not docs:
        quarantine("mp", formula, "no_entries_returned", {"formula": query_formula})
        out["flags"].append("MP: no entries found for formula, quarantined")
        return out

    cache_payload = [
        dict(material_id=str(d.material_id), formula_pretty=d.formula_pretty,
             spacegroup_number=(d.symmetry.number if d.symmetry else None),
             spacegroup_symbol=(d.symmetry.symbol if d.symmetry else None),
             energy_above_hull=d.energy_above_hull, density=d.density)
        for d in docs
    ]
    (RAW_CACHE / "mp" / f"{formula}.json").write_text(json.dumps(cache_payload, indent=2))

    docs_sorted = sorted(cache_payload, key=lambda d: d["energy_above_hull"] if d["energy_above_hull"] is not None else 1e9)

    # Name-keyed lookup first, formula-keyed fallback: needed for a formula
    # stored as multiple distinct materials (batch 3b: "C" is both Diamond
    # and Graphite, genuinely different allotropes needing different
    # expected space groups) -- backward compatible, since every existing
    # EXPECTED_SPACEGROUP entry is formula-keyed and no material's `name`
    # has ever coincided with one.
    expected = EXPECTED_SPACEGROUP.get(mat.get("name")) or EXPECTED_SPACEGROUP.get(formula)
    picked = None
    if expected:
        wanted_sgs, label = expected
        for d in docs_sorted:
            if d["spacegroup_number"] in wanted_sgs:
                picked = d
                break
        if picked is None:
            out["flags"].append(f"polymorph_ambiguity: expected spacegroup {wanted_sgs} ({label}) not found among "
                                 f"{len(docs_sorted)} MP entries for {formula}; falling back to lowest energy_above_hull")
            picked = docs_sorted[0]
    else:
        picked = docs_sorted[0]
        out["flags"].append("polymorph_ambiguity: no pre-verified expected space group for this material -- "
                             "took lowest energy_above_hull MP entry, please confirm polymorph match against RI.info data")

    out["mp_id"] = picked["material_id"]
    out["mp_space_group"] = f"{picked['spacegroup_symbol']} (#{picked['spacegroup_number']})"
    out["mp_energy_above_hull_ev"] = picked["energy_above_hull"]
    out["density_g_cm3"] = picked["density"]
    out["density_source"] = "MP_DFT"

    if formula in REJECTED_ALTERNATE_NOTE:
        out["flags"].append(REJECTED_ALTERNATE_NOTE[formula])
    if formula in PROVENANCE_CONFIRMED_NOTE:
        out["flags"].append(PROVENANCE_CONFIRMED_NOTE[formula])

    # Name-keyed lookup first, formula-keyed fallback -- same reason as
    # EXPECTED_SPACEGROUP above: a formula stored as multiple distinct
    # materials (batch 3b's Diamond/Graphite, both "C") can need different
    # experimental-density treatment per material, not one answer for the
    # shared formula.
    density_override = EXPERIMENTAL_DENSITY_OVERRIDE.get(mat.get("name")) or EXPERIMENTAL_DENSITY_OVERRIDE.get(formula)
    if density_override:
        exp_density, exp_note, exp_citation = density_override
        out["flags"].append(f"density overridden from MP_DFT ({out['density_g_cm3']:.4f} g/cm3) to "
                             f"experimental value ({exp_density} g/cm3): {exp_note}")
        out["density_g_cm3"] = exp_density
        out["density_source"] = "experimental lattice params"
        out["density_citation"] = exp_citation

    return out


# ---- periodictable SLD ------------------------------------------------------

def compute_sld(formula: str, density: float) -> dict:
    import periodictable
    out = dict(xray_sld_real=None, xray_sld_imag=None, neutron_sld_real=None, neutron_sld_imag=None, flags=[])
    if density is None:
        out["flags"].append("SLD: no density available, xray/neutron SLD left NULL")
        return out
    try:
        # periodictable parses parentheses natively; stripping them turned CaMg(CO3)2 into CaMgCO32 (1 C, 32 O) and gave wrong SLDs
        f = periodictable.formula(formula, density=density)
        xr, xi = f.xray_sld(energy=XRAY_ENERGY_KEV)
        nr, ni, _inc = f.neutron_sld(wavelength=NEUTRON_WAVELENGTH_A)
        out["xray_sld_real"] = float(xr) if xr is not None else None
        out["xray_sld_imag"] = float(xi) if xi is not None else None
        out["neutron_sld_real"] = float(nr) if nr is not None else None
        out["neutron_sld_imag"] = float(ni) if ni is not None else None
    except Exception as e:
        out["flags"].append(f"SLD calculation failed: {type(e).__name__}: {e}")
    return out


def strong_neutron_absorber(formula: str) -> bool:
    counts = parse_formula_counts(re.sub(r"[()]", "", formula))
    return any(el in counts for el in NEUTRON_ABSORBERS)


# ---- RI.info interpolation --------------------------------------------------

def interpolate_axis(data_path: str) -> dict:
    out = dict(n_633=None, k_633=None, flags=[])
    yaml_path = RI_DATA_ROOT / data_path
    if not yaml_path.exists():
        out["flags"].append(f"RI.info file missing on disk: {data_path}")
        return out
    try:
        wl_nm, n_val, k_val, refs, temp = parse_file(yaml_path)
    except Exception as e:
        quarantine("ri_info", data_path.replace("/", "_"), f"parse_failure: {type(e).__name__}: {e}", str(yaml_path))
        out["flags"].append(f"RI.info parse failed for {data_path}: {type(e).__name__}, quarantined")
        return out

    n633 = np.interp(633.0, wl_nm, n_val, left=np.nan, right=np.nan)
    out["n_633"] = None if np.isnan(n633) else float(n633)
    if out["n_633"] is None:
        out["flags"].append(f"633nm outside n range of {data_path}")

    if k_val is not None:
        k633 = np.interp(633.0, wl_nm, k_val, left=np.nan, right=np.nan)
        out["k_633"] = None if np.isnan(k633) else float(k633)
    return out


def main():
    ensure_dirs()
    selections = json.load(open(SELECTIONS_PATH))

    key = None
    load_dotenv(_ROOT / ".env")
    import os
    key = os.environ.get("MP_API_KEY")
    from mp_api.client import MPRester
    mpr_ctx = MPRester(key)
    mpr = mpr_ctx.__enter__()

    rows = []
    try:
        for mat in MATERIALS:
            formula = mat["formula"]
            print(f"[{mat['idx']:2d}/50] {mat['name']} ({formula})", flush=True)
            row = dict(idx=mat["idx"], name=mat["name"], formula=formula, polymorph=mat["polymorph"])
            flags = []

            pc = fetch_pubchem(mat)
            flags += pc.pop("flags")
            row.update(pc)

            mpd = fetch_mp(mat, mpr)
            flags += mpd.pop("flags")
            citation = mpd.pop("density_citation", None)
            row.update(mpd)
            if citation:
                row["density_citation_doi"] = citation["doi"]
                row["density_citation_title"] = citation["title"]
                row["density_citation_authors"] = citation["authors"]
                row["density_citation_journal"] = citation["journal"]
                row["density_citation_year"] = citation["year"]

            row["xray_energy_ev"] = XRAY_ENERGY_KEV * 1000

            sld = compute_sld(formula, row.get("density_g_cm3"))
            flags += sld.pop("flags")
            row.update(sld)

            row["strong_neutron_absorber"] = strong_neutron_absorber(formula)

            sel = selections.get(formula)
            if sel is None:
                flags.append("no Step 1 RI.info selection found")
            else:
                row["ri_shelf"], row["ri_book"] = None, None
                axes = sel["axes"]
                if axes:
                    p0 = axes[0]
                    row["ri_shelf"] = p0["data_path"].split("/")[0] if p0.get("data_path") else None
                    row["ri_book"] = p0["data_path"].split("/")[1] if p0.get("data_path") else None
                    rng = p0["wl_range"].replace(" um", "").split("-")
                    row["ri_wl_min_nm"] = float(rng[0]) * 1000 if len(rng) == 2 else None
                    row["ri_wl_max_nm"] = float(rng[1]) * 1000 if len(rng) == 2 else None
                    row["ri_page_primary"] = p0["page"]
                    row["axis_primary"] = p0["axis"]
                    interp = interpolate_axis(p0["data_path"])
                    flags += [f"[{p0['page']}] {f}" for f in interp.pop("flags")]
                    row["n_633"], row["k_633"] = interp["n_633"], interp["k_633"]

                    for extra_i, p in enumerate(axes[1:], start=2):
                        interp2 = interpolate_axis(p["data_path"])
                        flags += [f"[{p['page']}] {f}" for f in interp2.pop("flags")]
                        row[f"axis_{extra_i}"] = p["axis"]
                        row[f"n_633_axis{extra_i}"] = interp2["n_633"]
                        row[f"k_633_axis{extra_i}"] = interp2["k_633"]
                        row[f"ri_page_axis{extra_i}"] = p["page"]

                if sel.get("amorphous_default"):
                    flags.append("RI.info default dataset is amorphous/glass")

            row["flags"] = FLAG_JOIN.join(flags)
            rows.append(row)
    finally:
        mpr_ctx.__exit__(None, None, None)

    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV} ({len(df)} rows, {len(df.columns)} columns)")


if __name__ == "__main__":
    main()
