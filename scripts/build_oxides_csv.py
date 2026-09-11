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
MATERIALS = [
    dict(idx=1, name="Aluminium oxide / sapphire", formula="Al2O3", polymorph="corundum/sapphire", pubchem_name="Aluminum oxide"),
    dict(idx=2, name="Beryllium oxide", formula="BeO", polymorph="wurtzite", pubchem_name="Beryllium oxide"),
    dict(idx=3, name="Chrysoberyl", formula="BeAl2O4", polymorph="chrysoberyl", pubchem_name="Beryllium aluminate"),
    dict(idx=4, name="Beryllium hexaaluminate", formula="BeAl6O10", polymorph=None, pubchem_name="Beryllium hexaaluminate"),
    dict(idx=5, name="Calcium gadolinium aluminate", formula="CaGdAlO4", polymorph=None, pubchem_name="Calcium gadolinium aluminate"),
    dict(idx=6, name="Calcium yttrium aluminate", formula="CaYAlO4", polymorph=None, pubchem_name="Calcium yttrium aluminate"),
    dict(idx=7, name="Spinel", formula="MgAl2O4", polymorph="spinel", pubchem_name="Magnesium aluminate"),
    dict(idx=8, name="Lanthanum aluminate", formula="LaAlO3", polymorph=None, pubchem_name="Lanthanum aluminate"),
    dict(idx=9, name="Barium borate (BBO)", formula="BaB2O4", polymorph="beta-BBO", pubchem_name="Barium borate"),
    dict(idx=10, name="Bismuth triborate (BiBO)", formula="BiB3O6", polymorph=None, pubchem_name="Bismuth borate"),
    dict(idx=11, name="Lithium triborate (LBO)", formula="LiB3O5", polymorph=None, pubchem_name="Lithium triborate"),
    dict(idx=12, name="Cesium lithium borate (CLBO)", formula="CsLiB6O10", polymorph=None, pubchem_name="Cesium lithium borate"),
    dict(idx=13, name="Lutetium aluminium borate", formula="LuAl3(BO3)4", polymorph=None, pubchem_name="Lutetium aluminum borate"),
    dict(idx=14, name="Calcite", formula="CaCO3", polymorph="calcite", pubchem_name="Calcium carbonate"),
    dict(idx=15, name="Copper(II) oxide", formula="CuO", polymorph="tenorite", pubchem_name="Copper(II) oxide"),
    dict(idx=16, name="Copper(I) oxide", formula="Cu2O", polymorph="cuprite", pubchem_name="Copper(I) oxide"),
    dict(idx=17, name="Dysprosium oxide", formula="Dy2O3", polymorph="bixbyite", pubchem_name="Dysprosium oxide"),
    dict(idx=18, name="Hematite", formula="Fe2O3", polymorph="hematite", pubchem_name="Iron(III) oxide"),
    dict(idx=19, name="Magnetite", formula="Fe3O4", polymorph="magnetite", pubchem_name="Iron(II,III) oxide"),
    dict(idx=20, name="Germanium dioxide", formula="GeO2", polymorph=None, pubchem_name="Germanium dioxide"),
    dict(idx=21, name="Bismuth germanate", formula="Bi12GeO20", polymorph="BGO", pubchem_name="Bismuth germanium oxide"),
    dict(idx=22, name="Lead germanate", formula="Pb5Ge3O11", polymorph=None, pubchem_name="Lead germanate"),
    dict(idx=23, name="Hafnium dioxide", formula="HfO2", polymorph=None, pubchem_name="Hafnium oxide"),
    dict(idx=24, name="Lithium iodate", formula="LiIO3", polymorph=None, pubchem_name="Lithium iodate"),
    dict(idx=25, name="Lutetium oxide", formula="Lu2O3", polymorph="bixbyite", pubchem_name="Lutetium oxide"),
    dict(idx=26, name="LuAG", formula="Lu3Al5O12", polymorph="garnet", pubchem_name="Lutetium aluminum garnet"),
    dict(idx=27, name="Magnesium oxide", formula="MgO", polymorph="rock salt", pubchem_name="Magnesium oxide"),
    dict(idx=28, name="Molybdenum dioxide", formula="MoO2", polymorph=None, pubchem_name="Molybdenum dioxide"),
    dict(idx=29, name="Molybdenum trioxide", formula="MoO3", polymorph=None, pubchem_name="Molybdenum trioxide"),
    dict(idx=30, name="Calcium molybdate", formula="CaMoO4", polymorph="scheelite", pubchem_name="Calcium molybdate"),
    dict(idx=31, name="Lead molybdate", formula="PbMoO4", polymorph="scheelite/wulfenite", pubchem_name="Lead molybdate"),
    dict(idx=32, name="Strontium molybdate", formula="SrMoO4", polymorph="scheelite", pubchem_name="Strontium molybdate"),
    dict(idx=33, name="Niobium pentoxide", formula="Nb2O5", polymorph=None, pubchem_name="Niobium pentoxide"),
    dict(idx=34, name="Potassium niobate", formula="KNbO3", polymorph=None, pubchem_name="Potassium niobate"),
    dict(idx=35, name="Lithium niobate", formula="LiNbO3", polymorph=None, pubchem_name="Lithium niobate"),
    dict(idx=36, name="Scandium oxide", formula="Sc2O3", polymorph="bixbyite", pubchem_name="Scandium oxide"),
    dict(idx=37, name="Silicon monoxide", formula="SiO", polymorph="amorphous", pubchem_name="Silicon monoxide"),
    dict(idx=38, name="Silicon dioxide / quartz", formula="SiO2", polymorph="amorphous (fused silica)", pubchem_name="Silicon dioxide"),
    dict(idx=39, name="Tantalum pentoxide", formula="Ta2O5", polymorph="amorphous", pubchem_name="Tantalum pentoxide"),
    dict(idx=40, name="TGG", formula="Tb3Ga5O12", polymorph="garnet", pubchem_name="Terbium gallium garnet"),
    dict(idx=41, name="Tellurium dioxide", formula="TeO2", polymorph="paratellurite", pubchem_name="Tellurium dioxide"),
    dict(idx=42, name="Titanium dioxide (rutile / anatase)", formula="TiO2", polymorph="rutile", pubchem_name="Titanium dioxide"),
    dict(idx=43, name="Barium titanate", formula="BaTiO3", polymorph=None, pubchem_name="Barium titanate"),
    dict(idx=44, name="Strontium titanate", formula="SrTiO3", polymorph=None, pubchem_name="Strontium titanate"),
    dict(idx=45, name="Vanadium dioxide", formula="VO2", polymorph="M1 (insulating)", pubchem_name="Vanadium dioxide"),
    dict(idx=46, name="Yttrium orthovanadate", formula="YVO4", polymorph="zircon", pubchem_name="Yttrium vanadate"),
    dict(idx=47, name="Tungsten trioxide", formula="WO3", polymorph=None, pubchem_name="Tungsten trioxide"),
    dict(idx=48, name="Yttrium oxide", formula="Y2O3", polymorph="bixbyite", pubchem_name="Yttrium oxide"),
    dict(idx=49, name="YAG", formula="Y3Al5O12", polymorph="garnet", pubchem_name="Yttrium aluminum garnet"),
    dict(idx=50, name="Zinc oxide", formula="ZnO", polymorph="wurtzite", pubchem_name="Zinc oxide"),
]

# Forced "no legitimate MP match" materials: the RI.info default dataset is
# amorphous/glass (auto-detected in Step 1, plus SiO confirmed manually per
# user instruction). Density must come from literature, not MP.
FORCE_NO_MP = {"SiO", "SiO2", "GeO2", "Ta2O5"}

LITERATURE_DENSITY = {
    # g/cm3, with source note
    "SiO2": (2.20, "literature: fused silica, standard value"),
    "SiO": (2.13, "literature: evaporated amorphous SiO film, commonly cited value"),
    "GeO2": (3.65, "literature: fused (vitreous) GeO2, commonly cited value"),
    "Ta2O5": (7.90, "literature: amorphous Ta2O5 thin film, commonly cited value (vs 8.37 crystalline)"),
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
        if r3.status_code == 200:
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
        # 404/empty just means no curated CAS on file -- not an error, leave NULL

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        quarantine("pubchem", cache_key, f"exception: {type(e).__name__}: {e}", None)
        out["flags"].append(f"pubchem: exception {type(e).__name__}, quarantined")

    return out


# ---- Materials Project -----------------------------------------------------

def fetch_mp(mat: dict, mpr) -> dict:
    formula = mat["formula"]
    out = dict(mp_id=None, mp_space_group=None, mp_energy_above_hull_ev=None,
               density_g_cm3=None, density_source=None, flags=[])

    if formula in FORCE_NO_MP:
        lit_density, lit_note = LITERATURE_DENSITY[formula]
        out["density_g_cm3"] = lit_density
        out["density_source"] = "literature"
        out["flags"].append(f"no MP structure match: RI.info default optical data is amorphous/glass, MP has no "
                             f"amorphous entries. Density = {lit_density} g/cm3 ({lit_note}). Verify before use.")
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

    expected = EXPECTED_SPACEGROUP.get(formula)
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
    return out


# ---- periodictable SLD ------------------------------------------------------

def compute_sld(formula: str, density: float) -> dict:
    import periodictable
    out = dict(xray_sld_real=None, xray_sld_imag=None, neutron_sld_real=None, neutron_sld_imag=None, flags=[])
    if density is None:
        out["flags"].append("SLD: no density available, xray/neutron SLD left NULL")
        return out
    try:
        clean_formula = re.sub(r"[()]", "", formula)
        f = periodictable.formula(clean_formula, density=density)
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
            row.update(mpd)

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
