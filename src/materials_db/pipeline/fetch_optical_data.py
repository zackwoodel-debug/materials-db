#!/usr/bin/env python3
"""
pipeline/fetch_optical_data.py
==============================
Clone the refractiveindex.info YAML database, parse n,k optical data for
selected soft-matter / substrate materials, and populate materials.db.

Materials
---------
Water, Gold, SiO2, Polystyrene, DPPC      (original five)
PMMA, Ethanol, DMSO                        (auto-loaded from RI.info)
PEG                                        (manual insert — not in RI.info)

Schema
------
materials  : id, name, formula, material_class, notes, density_g_cm3
optical_nk : id, material_id (FK), wavelength_nm, n, k, source_ref, temperature_C
"""

import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import requests
import yaml
from rdkit import Chem
from rdkit.Chem import Descriptors

# ─── Paths ────────────────────────────────────────────────────────────────────

_ROOT    = Path(__file__).resolve().parents[3]   # project root
DB_FILE  = str(_ROOT / "data" / "materials.db")
REPO_URL = "https://github.com/polyanskiy/refractiveindex.info-database.git"
REPO_DIR = str(_ROOT / "refractiveindex_db")

# ─── Configuration ────────────────────────────────────────────────────────────

WL_MIN_NM  = 200.0    # fetch window – UV
WL_MAX_NM  = 3000.0   # fetch window – near-IR
N_FORMULA  = 500      # sample points for formula-based entries
HC_EV_NM   = 1239.84193  # hc in eV·nm (CODATA 2018)

# ─── Materials manifest ───────────────────────────────────────────────────────
# Keys
#   candidates   : preferred YAML paths relative to data/ root, tried in order
#   search_dirs  : fallback dirs to glob *.yml from (skips about.yml)
#   density_g_cm3: bulk density at ~20 °C for XRR modelling
#   manual_nk    : list of dicts {wavelength_nm, n, k, source_ref, temperature_C}
#                  inserted directly when no YAML is found (or to supplement)

MATERIALS: List[dict] = [
    dict(
        name="Water",
        formula="H2O",
        material_class="solvent",
        notes="Hale & Querry 1973; broad UV–IR; essential solvent reference",
        density_g_cm3=1.000,
        candidates=[
            "main/H2O/nk/Hale.yml",
            "main/H2O/nk/Segelstein.yml",
            "main/H2O/nk/Daimon-19.0C.yml",
        ],
        search_dirs=["main/H2O/nk", "main/H2O/n"],
    ),
    dict(
        name="Gold",
        formula="Au",
        material_class="metal",
        notes="Johnson & Christy 1972; 188–1937 nm; SPR substrate",
        density_g_cm3=19.32,
        candidates=[
            "main/Au/nk/Johnson.yml",
            "main/Au/nk/McPeak.yml",
            "main/Au/nk/Rakic-LD.yml",
        ],
        search_dirs=["main/Au/nk"],
    ),
    dict(
        name="SiO2",
        formula="SiO2",
        material_class="oxide",
        notes="Malitson 1965; fused silica 210–6700 nm; XRR/ellipsometry substrate",
        density_g_cm3=2.20,
        candidates=[
            "main/SiO2/nk/Malitson.yml",
            "main/SiO2/nk/Philipp.yml",
            "main/SiO2/nk/Popova.yml",
            "main/SiO2/nk/Lemarchand.yml",
        ],
        search_dirs=["main/SiO2/nk", "main/SiO2/n"],
    ),
    dict(
        name="Polystyrene",
        formula="(C8H8)n",
        material_class="polymer",
        notes="Sultanova 2009; visible; common NP / thin-film material",
        density_g_cm3=1.05,
        candidates=[
            "organic/(C8H8)n - polystyrene/nk/Sultanova.yml",
            "organic/(C8H8)n - polystyrene/nk/Zhang.yml",
            "organic/(C8H8)n - polystyrene/nk/Inagaki.yml",
        ],
        search_dirs=[
            "organic/(C8H8)n - polystyrene/nk",
            "organic/(C8H8)n - polystyrene/n",
        ],
    ),
    dict(
        name="DPPC",
        formula="C40H80NO8P",
        material_class="lipid",
        notes=(
            "Dipalmitoylphosphatidylcholine; lipid bilayer model. "
            "Not in refractiveindex.info."
        ),
        density_g_cm3=1.01,
        candidates=["organic/lipids/DPPC.yml", "organic/phospholipids/DPPC.yml"],
        search_dirs=["organic/lipids", "organic/phospholipids"],
        manual_nk=[
            dict(
                wavelength_nm=633.0, n=1.48, k=None,
                source_ref="Chou et al. Biophys J 2010 doi:10.1016/j.bpj.2010.07.026",
                temperature_C=25.0,
            ),
        ],
    ),
    dict(
        name="PMMA",
        formula="(C5H8O2)n",
        material_class="polymer",
        notes="Beadie et al. 2015; 420–1620 nm; common resist / optical coating",
        density_g_cm3=1.19,
        candidates=[
            "organic/(C5H8O2)n - poly(methyl methacrylate)/nk/Beadie.yml",
            "organic/(C5H8O2)n - poly(methyl methacrylate)/nk/Sultanova.yml",
        ],
        search_dirs=["organic/(C5H8O2)n - poly(methyl methacrylate)/nk"],
    ),
    dict(
        name="Ethanol",
        formula="C2H6O",
        material_class="solvent",
        notes="Sani & Dell'Oro 2016; 185–2800 nm; includes tabulated k",
        density_g_cm3=0.789,
        candidates=[
            "organic/C2H6O - ethanol/nk/Sani-formula.yml",
            "organic/C2H6O - ethanol/nk/Rheims.yml",
            "organic/C2H6O - ethanol/nk/Kedenburg.yml",
        ],
        search_dirs=["organic/C2H6O - ethanol/nk"],
    ),
    dict(
        name="DMSO",
        formula="C2H6OS",
        material_class="solvent",
        notes="Li et al. 2022; 200–1700 nm; common biochemical solvent",
        density_g_cm3=1.100,
        candidates=[
            "organic/C2H6OS - dimethyl sulfoxide/nk/Li.yml",
            "organic/C2H6OS - dimethyl sulfoxide/nk/Kozma.yml",
        ],
        search_dirs=["organic/C2H6OS - dimethyl sulfoxide/nk"],
    ),
    dict(
        name="PEG",
        formula="(C2H4O)n",
        material_class="polymer",
        notes=(
            "Polyethylene glycol; not in refractiveindex.info. "
            "Bulk n from Polymer Handbook (Brandrup et al. 4th ed.)."
        ),
        density_g_cm3=1.13,
        candidates=[
            "organic/PEG/PEG.yml",
            "organic/(C2H4O)n - polyethylene glycol/nk/PEG.yml",
        ],
        search_dirs=[],
        manual_nk=[
            dict(
                wavelength_nm=589.0, n=1.4570, k=None,
                source_ref="Brandrup et al. Polymer Handbook 4th ed. (1999)",
                temperature_C=20.0,
            ),
        ],
    ),
    dict(
        name="Silicon",
        formula="Si",
        material_class="semiconductor",
        notes="Single-crystal silicon substrate. Density: Deslattes et al. 1980.",
        density_g_cm3=2.329,
        candidates=[],
        search_dirs=[],
    ),
]

# ─── Chemical Properties & Calculations Fallbacks ────────────────────────────────

FALLBACK_PROPERTIES = {
    "Water": {"formula": "H2O", "smiles": "O", "molecular_weight": 18.015},
    "Gold": {"formula": "Au", "smiles": "[Au]", "molecular_weight": 196.9665},
    "SiO2": {"formula": "SiO2", "smiles": "O=[Si]=O", "molecular_weight": 60.084},
    "Silicon": {"formula": "Si", "smiles": "[Si]", "molecular_weight": 28.0855},
    "Polystyrene": {"formula": "(C8H8)n", "smiles": "CC(C1=CC=CC=C1)", "molecular_weight": 104.15},
    "DPPC": {"formula": "C40H80NO8P", "smiles": "CCCCCCCCCCCCCCCC(=O)OCC(COP(=O)([O-])OCC[N+](C)(C)C)OC(=O)CCCCCCCCCCCCCCC", "molecular_weight": 734.05},
    "PMMA": {"formula": "(C5H8O2)n", "smiles": "CC(C)(C(=O)OC)", "molecular_weight": 100.115},
    "Ethanol": {"formula": "C2H6O", "smiles": "CCO", "molecular_weight": 46.068},
    "DMSO": {"formula": "C2H6OS", "smiles": "CS(=O)C", "molecular_weight": 78.13},
    "PEG": {"formula": "(C2H4O)n", "smiles": "CCO", "molecular_weight": 44.053},
}

ATOMS: dict[str, tuple[int, float]] = {
    #       Z    atomic_weight (g/mol)
    "H":  ( 1,   1.00794),
    "D":  ( 1,   2.01410),
    "C":  ( 6,  12.0107),
    "N":  ( 7,  14.0067),
    "O":  ( 8,  15.9994),
    "F":  ( 9,  18.9984),
    "Si": (14,  28.0855),
    "P":  (15,  30.97376),
    "S":  (16,  32.065),
    "Au": (79, 196.9665),
}

B_COH = {
    "H": -3.7406e-5,   # Å
    "D":  6.6710e-5,   # Å
    "C":  6.6460e-5,   # Å
    "N":  9.3600e-5,   # Å
    "O":  5.8030e-5,   # Å
    "P":  5.1300e-5,   # Å
    "S":  2.8470e-5,   # Å
    "Si": 4.1491e-5,   # Å
    "Au": 7.6300e-5,   # Å
}

NA = 6.02214076e23
R_E = 2.8179403e-5

def parse_formula(formula: str) -> dict[str, int]:
    clean = re.sub(r"^\((.+)\)[A-Za-z]?\d*$", r"\1", formula.strip())
    counts: dict[str, int] = {}
    for elem, num_str in re.findall(r"([A-Z][a-z]?)(\d*)", clean):
        if not elem:
            continue
        counts[elem] = counts.get(elem, 0) + (int(num_str) if num_str else 1)
    return counts

def fetch_pubchem_properties(name: str) -> Optional[dict]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/MolecularFormula,MolecularWeight,CanonicalSMILES/JSON"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            props = r.json()["PropertyTable"]["Properties"][0]
            return {
                "formula": props.get("MolecularFormula"),
                "molecular_weight": float(props.get("MolecularWeight", 0.0)),
                "smiles": props.get("CanonicalSMILES") or props.get("ConnectivitySMILES")
            }
    except Exception as e:
        print(f"  [PubChem warn] Resolution failed for {name}: {e}")
    
    # Fallback to local dict
    if name in FALLBACK_PROPERTIES:
        print(f"  [Fallback] Using manual properties for {name}")
        return FALLBACK_PROPERTIES[name]
    return None

def compute_rdkit_descriptors(smiles: str) -> dict[str, float]:
    clean_smiles = smiles.replace("*", "")
    try:
        mol = Chem.MolFromSmiles(clean_smiles)
        if mol is None:
            return {}
        return {
            "logP": float(Descriptors.MolLogP(mol)),
            "TPSA": float(Descriptors.TPSA(mol)),
            "h_bond_donors": float(Descriptors.NumHDonors(mol)),
            "h_bond_acceptors": float(Descriptors.NumHAcceptors(mol)),
            "rotatable_bonds": float(Descriptors.NumRotatableBonds(mol)),
            "exact_mass": float(Descriptors.ExactMolWt(mol)),
        }
    except Exception as e:
        print(f"  [RDKit warn] Descriptor calculation failed: {e}")
        return {}


# ─── Repository access ────────────────────────────────────────────────────────

def clone_repo(repo_dir: str) -> Path:
    """Shallow-clone the database repo (once); return path to data/ directory."""
    if not Path(repo_dir).exists():
        print("Cloning refractiveindex.info-database (shallow, ~200 MB) …")
        subprocess.run(
            ["git", "clone", "--depth=1", REPO_URL, repo_dir],
            check=True,
        )
        print("Clone complete.\n")
    else:
        print(f"Using cached repo at '{repo_dir}/'.\n")

    for sub in ["database/data", "data"]:
        p = Path(repo_dir) / sub
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot find data/ directory under {repo_dir}/")


def find_yaml(data_root: Path, mat: dict) -> Optional[Path]:
    """Return the best YAML file for a material, or None if absent."""
    for rel in mat["candidates"]:
        p = data_root / rel
        if p.exists():
            return p
    for d in mat.get("search_dirs", []):
        dp = data_root / d
        if dp.is_dir():
            ymls = sorted(p for p in dp.glob("*.yml") if p.name != "about.yml")
            if ymls:
                return ymls[0]
    return None


def detect_formula_type(yaml_path: Path) -> str:
    """Return a compact description of DATA block types (for the summary table)."""
    with open(yaml_path) as fh:
        raw = yaml.safe_load(fh)
    types = [str(b.get("type", "?")).strip() for b in raw.get("DATA", [])]
    seen: dict = {}
    for t in types:
        seen[t] = None
    return " + ".join(seen)


# ─── Dispersion formula evaluators ───────────────────────────────────────────
# Refractiveindex.info formula conventions (current DB format)
#
# F1 / F2  n² = 1 + c₀ + Σ pairs         c₀ = 0 in current format (1 implicit)
# F3       n² = c₀ + Σ (B, p) pairs       c₀ is standalone constant
# F4       n² = c₀ + Σ (B,p,C,q) quads   general B·λ^p/(λ^q−C) + 2-coeff tails
# F5       n  = c₀ + Σ (B, p) pairs       Cauchy; c₀ is standalone constant
# F6       n−1 = c₀ + Σ (B, C) pairs      gases; c₀ standalone
# F7       Herzberger; 6 named coefficients

def _coeffs(block: dict) -> np.ndarray:
    return np.array([float(x) for x in str(block["coefficients"]).split()])


def eval_formula(
    block: dict, lam: np.ndarray
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Evaluate a dispersion formula block at wavelengths *lam* (µm).
    Returns (n_array, k_array_or_None).
    """
    ftype = block["type"]
    c = _coeffs(block)

    if ftype == "formula 1":
        # Sellmeier:  n² = 1 + c₀ + Σ cᵢ·λ²/(λ²−cᵢ₊₁²)
        n2 = np.full_like(lam, 1.0 + c[0])
        for i in range(1, len(c) - 1, 2):
            n2 = n2 + c[i] * lam**2 / (lam**2 - c[i + 1] ** 2)
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 2":
        # Sellmeier-2:  n² = 1 + c₀ + Σ cᵢ·λ²/(λ²−cᵢ₊₁)   (Cᵢ not squared)
        n2 = np.full_like(lam, 1.0 + c[0])
        for i in range(1, len(c) - 1, 2):
            n2 = n2 + c[i] * lam**2 / (lam**2 - c[i + 1])
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 3":
        # Polynomial in n²:  n² = c₀ + Σ cᵢ·λ^cᵢ₊₁
        # c[0] is a standalone constant; Σ iterates 2-coeff pairs from index 1.
        n2 = np.full_like(lam, c[0])
        for i in range(1, len(c) - 1, 2):
            n2 = n2 + c[i] * lam ** c[i + 1]
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 4":
        # General:  n² = c₀ + Σ Bᵢ·λ^pᵢ/(λ^qᵢ−Cᵢ)   [4-coeff groups]
        #                    + Σ Dⱼ·λ^fⱼ                [2-coeff polynomial tail]
        # Group layout: [B, p_num, C, q_den] → B·λ^p / (λ^q − C)
        n2 = np.full_like(lam, c[0])
        i = 1
        while i < len(c):
            if i + 3 < len(c):
                B, p, C_val, q = c[i], c[i + 1], c[i + 2], c[i + 3]
                denom = lam**q - C_val
                with np.errstate(divide="ignore", invalid="ignore"):
                    n2 = n2 + np.where(denom != 0.0, B * lam**p / denom, 0.0)
                i += 4
            elif i + 1 < len(c):
                n2 = n2 + c[i] * lam ** c[i + 1]
                i += 2
            else:
                break
        return np.sqrt(np.clip(n2, 1e-30, None)), None

    if ftype == "formula 5":
        # Cauchy:  n = c₀ + Σ cᵢ·λ^cᵢ₊₁
        # c[0] is a standalone constant; Σ iterates 2-coeff pairs from index 1.
        n = np.full_like(lam, c[0])
        for i in range(1, len(c) - 1, 2):
            n = n + c[i] * lam ** c[i + 1]
        return n, None

    if ftype == "formula 6":
        # Gases:  n−1 = c₀ + Σ cᵢ/(cᵢ₊₁−λ⁻²)
        n_m1 = np.full_like(lam, c[0])
        for i in range(1, len(c) - 1, 2):
            n_m1 = n_m1 + c[i] / (c[i + 1] - lam**-2)
        return 1.0 + n_m1, None

    if ftype == "formula 7":
        # Herzberger:  n = A + B/L + C/L² + Dλ² + Eλ⁴ + Fλ⁶  (L = λ²−0.028)
        A, B, C, D, E, F = (float(c[i]) if i < len(c) else 0.0 for i in range(6))
        L = lam**2 - 0.028
        n = A + B / L + C / L**2 + D * lam**2 + E * lam**4 + F * lam**6
        return n, None

    raise ValueError(f"Unsupported formula type: '{ftype}'")


# ─── YAML parser ──────────────────────────────────────────────────────────────

def _parse_table(data_str: str, ncols: int) -> np.ndarray:
    rows = []
    for line in data_str.strip().splitlines():
        parts = line.split()
        if len(parts) >= ncols:
            try:
                rows.append([float(x) for x in parts[:ncols]])
            except ValueError:
                pass
    return np.array(rows) if rows else np.zeros((0, ncols))


def parse_file(
    yaml_path: Path,
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], str, Optional[float]]:
    """
    Parse a refractiveindex.info YAML file.

    Returns
    -------
    wavelengths_nm : 1-D array, sorted ascending
    n              : 1-D array (real refractive index)
    k              : 1-D array or None  (extinction coefficient; None → absent)
    source_ref     : str  (≤512 chars)
    temperature_C  : float or None
    """
    with open(yaml_path) as fh:
        raw = yaml.safe_load(fh)

    refs = raw.get("REFERENCES") or raw.get("COMMENTS") or ""
    if isinstance(refs, list):
        refs = " | ".join(str(r) for r in refs)
    refs = str(refs)[:512]

    temp: Optional[float] = None
    m = re.search(r"[-_](\d+(?:\.\d+)?)[Cc](?:\b|$)", yaml_path.stem)
    if m:
        temp = float(m.group(1))
    cond = raw.get("CONDITIONS") or {}
    if isinstance(cond, dict) and "temperature" in cond and temp is None:
        try:
            t_k = float(cond["temperature"])
            temp = t_k - 273.15 if t_k > 200 else t_k
        except (ValueError, TypeError):
            pass

    wl_min_um = WL_MIN_NM / 1000.0
    wl_max_um = WL_MAX_NM / 1000.0

    n_wl: List[float] = []
    n_val: List[float] = []
    k_wl: List[float] = []
    k_val: List[float] = []

    for block in raw.get("DATA", []):
        btype = str(block.get("type", "")).strip()

        if btype == "tabulated nk":
            arr = _parse_table(block["data"], 3)
            if arr.shape[0] == 0:
                continue
            mask = (arr[:, 0] >= wl_min_um) & (arr[:, 0] <= wl_max_um)
            n_wl.extend((arr[mask, 0] * 1000).tolist())
            n_val.extend(arr[mask, 1].tolist())
            k_wl.extend((arr[mask, 0] * 1000).tolist())
            k_val.extend(arr[mask, 2].tolist())

        elif btype == "tabulated n":
            arr = _parse_table(block["data"], 2)
            if arr.shape[0] == 0:
                continue
            mask = (arr[:, 0] >= wl_min_um) & (arr[:, 0] <= wl_max_um)
            n_wl.extend((arr[mask, 0] * 1000).tolist())
            n_val.extend(arr[mask, 1].tolist())

        elif btype == "tabulated k":
            arr = _parse_table(block["data"], 2)
            if arr.shape[0] == 0:
                continue
            mask = (arr[:, 0] >= wl_min_um) & (arr[:, 0] <= wl_max_um)
            k_wl.extend((arr[mask, 0] * 1000).tolist())
            k_val.extend(arr[mask, 1].tolist())

        elif btype.startswith("formula"):
            wr = block.get("wavelength_range", f"{wl_min_um} {wl_max_um}")
            parts = str(wr).split()
            lo = max(float(parts[0]), wl_min_um)
            hi = min(float(parts[1]), wl_max_um)
            if lo >= hi:
                continue
            lam = np.linspace(lo, hi, N_FORMULA)
            try:
                n_f, k_f = eval_formula(block, lam)
            except (ValueError, ZeroDivisionError, FloatingPointError) as exc:
                print(f"    [formula warn] {exc}")
                continue
            n_wl.extend((lam * 1000).tolist())
            n_val.extend(n_f.tolist())
            if k_f is not None:
                k_wl.extend((lam * 1000).tolist())
                k_val.extend(k_f.tolist())

    if not n_wl:
        raise ValueError("No n data found in any DATA block")

    n_wl_a = np.array(n_wl)
    n_val_a = np.array(n_val)
    idx = np.argsort(n_wl_a)
    n_wl_a = n_wl_a[idx]
    n_val_a = n_val_a[idx]

    k_out: Optional[np.ndarray] = None
    if k_wl:
        k_wl_a = np.array(k_wl)
        k_val_a = np.array(k_val)
        kidx = np.argsort(k_wl_a)
        # Interpolate k onto the n wavelength grid; NaN outside k range → NULL
        k_out = np.interp(
            n_wl_a, k_wl_a[kidx], k_val_a[kidx], left=np.nan, right=np.nan
        )

    return n_wl_a, n_val_a, k_out, refs, temp


# ─── Database helpers ─────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS references_db (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doi           TEXT    UNIQUE,
    citation_text TEXT    NOT NULL,
    url           TEXT,
    bibtex        TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    formula          TEXT,
    smiles           TEXT,
    molecular_weight REAL,
    material_class   TEXT,
    notes            TEXT,
    density_g_cm3    REAL
);

CREATE TABLE IF NOT EXISTS chemical_descriptors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id     INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    descriptor_name TEXT    NOT NULL,
    value           REAL    NOT NULL,
    source_library  TEXT,
    UNIQUE(material_id, descriptor_name)
);

CREATE TABLE IF NOT EXISTS optical_nk (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id   INTEGER REFERENCES references_db(id),
    wavelength_nm  REAL    NOT NULL,
    n              REAL    NOT NULL,
    k              REAL,
    source_ref     TEXT,
    temperature_C  REAL,
    UNIQUE(material_id, wavelength_nm, temperature_C)
);

CREATE TABLE IF NOT EXISTS viscoelasticity (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id        INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id       INTEGER REFERENCES references_db(id),
    frequency_hz       REAL    NOT NULL,
    temperature_C      REAL,
    storage_modulus_pa REAL,
    loss_modulus_pa    REAL,
    viscosity_mpa_s    REAL,
    UNIQUE(material_id, frequency_hz, temperature_C)
);

CREATE TABLE IF NOT EXISTS dielectrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id),
    frequency_hz      REAL    NOT NULL,
    temperature_C     REAL,
    real_permittivity REAL    NOT NULL,
    imag_permittivity REAL,
    UNIQUE(material_id, frequency_hz, temperature_C)
);

CREATE TABLE IF NOT EXISTS calculated_slds (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id),
    energy_ev         REAL    NOT NULL,
    wavelength_nm     REAL    NOT NULL,
    xray_sld_real     REAL    NOT NULL,
    xray_sld_imag     REAL,
    neutron_sld_real  REAL    NOT NULL,
    neutron_sld_imag  REAL,
    UNIQUE(material_id, energy_ev)
);

CREATE INDEX IF NOT EXISTS idx_nk_mat ON optical_nk(material_id);
CREATE INDEX IF NOT EXISTS idx_nk_wl  ON optical_nk(wavelength_nm);
"""


def setup_db(path: str) -> sqlite3.Connection:
    """Open (or create) the DB and apply any missing schema changes non-destructively."""
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def insert_material(conn: sqlite3.Connection, mat: dict) -> int:
    cur = conn.execute(
        "INSERT INTO materials (name, formula, smiles, molecular_weight, material_class, notes, density_g_cm3) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            mat["name"], mat["formula"], mat.get("smiles"),
            mat.get("molecular_weight"), mat["material_class"],
            mat["notes"], mat.get("density_g_cm3"),
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_or_create_reference(conn: sqlite3.Connection, refs_str: str) -> Optional[int]:
    if not refs_str or not refs_str.strip():
        return None
    refs_str = refs_str.strip()
    
    # Try to extract DOI if present
    doi_match = re.search(r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b', refs_str, re.IGNORECASE)
    doi = doi_match.group(0) if doi_match else None
    
    try:
        if doi:
            row = conn.execute("SELECT id FROM references_db WHERE doi = ?", (doi,)).fetchone()
            if row:
                return row[0]
            cur = conn.execute(
                "INSERT INTO references_db (doi, citation_text, url) VALUES (?, ?, ?)",
                (doi, refs_str, f"https://doi.org/{doi}")
            )
            conn.commit()
            return cur.lastrowid
        else:
            row = conn.execute("SELECT id FROM references_db WHERE citation_text = ?", (refs_str,)).fetchone()
            if row:
                return row[0]
            cur = conn.execute(
                "INSERT INTO references_db (citation_text) VALUES (?)",
                (refs_str,)
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        print(f"Reference insertion failed: {e}")
        return None


def insert_nk(
    conn: sqlite3.Connection,
    mat_id: int,
    wl: np.ndarray,
    n: np.ndarray,
    k: Optional[np.ndarray],
    ref: str,
    temp: Optional[float],
) -> int:
    ref_id = get_or_create_reference(conn, ref)
    rows = []
    for i in range(len(wl)):
        k_val: Optional[float] = None
        if k is not None:
            kv = float(k[i])
            k_val = None if (np.isnan(kv) or np.isinf(kv)) else kv
        rows.append((mat_id, ref_id, float(wl[i]), float(n[i]), k_val, ref, temp))
    conn.executemany(
        "INSERT INTO optical_nk "
        "(material_id, reference_id, wavelength_nm, n, k, source_ref, temperature_C) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def insert_manual_nk(conn: sqlite3.Connection, mat_id: int, entries: list) -> int:
    rows = []
    for e in entries:
        ref_id = get_or_create_reference(conn, e.get("source_ref", ""))
        rows.append((
            mat_id,
            ref_id,
            e["wavelength_nm"], e["n"], e.get("k"),
            e.get("source_ref"), e.get("temperature_C"),
        ))
    conn.executemany(
        "INSERT INTO optical_nk "
        "(material_id, reference_id, wavelength_nm, n, k, source_ref, temperature_C) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(rows: list) -> None:
    W = 98
    print("\n" + "=" * W)
    print(
        f"  {'Material':<13} {'Formula type':<22} {'WL range (nm)':<20} "
        f"{'Pts':>5}  {'k':>10}  Status"
    )
    print("-" * W)
    for name, ftype, wl_lo, wl_hi, pts, k_pts, status in rows:
        if wl_lo is None:
            wl_str = "—"
        elif wl_lo == wl_hi:
            wl_str = f"{wl_lo:.0f} nm"
        else:
            wl_str = f"{wl_lo:.0f}–{wl_hi:.0f} nm"

        k_str = f"{k_pts}/{pts}" if k_pts else "NULL"
        pts_str = str(pts) if pts else "—"

        print(
            f"  {name:<13} {ftype:<22} {wl_str:<20} "
            f"{pts_str:>5}  {k_str:>10}  {status}"
        )
    print("=" * W + "\n")


# ─── Spot-check ───────────────────────────────────────────────────────────────

def spot_check(conn: sqlite3.Connection) -> None:
    checks = [
        ("Water",       589),
        ("Gold",        633),
        ("SiO2",        589),
        ("Polystyrene", 589),
        ("PMMA",        589),
        ("Ethanol",     589),
        ("DMSO",        589),
        ("DPPC",        633),
        ("PEG",         589),
    ]
    print("Spot-check — nearest stored (n, k) to reference wavelength:")
    for name, wl in checks:
        row = conn.execute(
            """
            SELECT o.wavelength_nm, o.n, o.k
            FROM optical_nk o
            JOIN materials m ON m.id = o.material_id
            WHERE m.name = ?
            ORDER BY ABS(o.wavelength_nm - ?) LIMIT 1
            """,
            (name, wl),
        ).fetchone()
        if row:
            wl_a, nv, kv = row
            k_str = f"{kv:.4e}" if kv is not None else "NULL"
            print(f"  {name:<13} @ {wl_a:6.1f} nm   n={nv:.4f}  k={k_str}")
        else:
            print(f"  {name:<13}   no optical data")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    data_root = clone_repo(REPO_DIR)
    print(f"Data root : {data_root}")

    conn = setup_db(DB_FILE)
    print(f"Database  : {DB_FILE}\n")

    summary_rows = []

    for mat in MATERIALS:
        name = mat["name"]
        print(f"[{name} ({mat['formula']})]")

        # 1. Fetch Smiles, Formula, and Molecular Weight from PubChem (or Fallback)
        pubchem_props = fetch_pubchem_properties(name)
        if pubchem_props:
            mat["formula"] = pubchem_props.get("formula") or mat["formula"]
            mat["smiles"] = pubchem_props.get("smiles")
            mat["molecular_weight"] = pubchem_props.get("molecular_weight")
        else:
            # Local fallback properties
            props = FALLBACK_PROPERTIES.get(name, {})
            mat["formula"] = props.get("formula") or mat["formula"]
            mat["smiles"] = props.get("smiles")
            mat["molecular_weight"] = props.get("molecular_weight")

        mat_id = insert_material(conn, mat)

        # 2. Compute and Insert RDKit Chemical Descriptors
        if mat.get("smiles"):
            descriptors = compute_rdkit_descriptors(mat["smiles"])
            for desc_name, value in descriptors.items():
                conn.execute(
                    "INSERT OR IGNORE INTO chemical_descriptors (material_id, descriptor_name, value, source_library) "
                    "VALUES (?, ?, ?, ?)",
                    (mat_id, desc_name, value, "RDKit")
                )
            conn.commit()
            if descriptors:
                print(f"  +  {len(descriptors)} chemical descriptors computed via RDKit")

        # 3. Calculate and Insert Dynamic SLDs
        if mat.get("formula") and mat.get("density_g_cm3") and mat.get("molecular_weight"):
            counts = parse_formula(mat["formula"])
            mw = mat["molecular_weight"]
            density = mat["density_g_cm3"]

            # Compute X-ray SLD (Cu K-alpha 8.04 keV, 0.15406 nm)
            z_total = sum(cnt * ATOMS[el][0] for el, cnt in counts.items() if el in ATOMS)
            rho_e = (density * NA * z_total) / (mw * 1e24)
            xray_sld = rho_e * R_E

            # Compute Neutron SLD coherent
            b_total = sum(cnt * B_COH[el] for el, cnt in counts.items() if el in B_COH)
            neutron_sld = (density * NA * b_total) / (mw * 1e24)

            # Insert Cu K-alpha (8.04 keV, 0.15406 nm)
            conn.execute(
                "INSERT OR IGNORE INTO calculated_slds "
                "(material_id, energy_ev, wavelength_nm, xray_sld_real, xray_sld_imag, neutron_sld_real, neutron_sld_imag) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mat_id, 8040.0, HC_EV_NM / 8040.0, xray_sld, None, neutron_sld, None)
            )

            # Insert Mo K-alpha (17.4 keV, 0.07093 nm)
            conn.execute(
                "INSERT OR IGNORE INTO calculated_slds "
                "(material_id, energy_ev, wavelength_nm, xray_sld_real, xray_sld_imag, neutron_sld_real, neutron_sld_imag) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mat_id, 17400.0, HC_EV_NM / 17400.0, xray_sld, None, neutron_sld, None)
            )
            conn.commit()
            print(f"  +  X-ray/Neutron SLD computed (Cu Ka={xray_sld:.3e} Å⁻², SLDn={neutron_sld:.3e} Å⁻²)")

        # 4. Seed viscoelasticity and dielectrics tables
        if name == "Water":
            conn.execute(
                "INSERT OR IGNORE INTO viscoelasticity (material_id, frequency_hz, temperature_C, storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s) "
                "VALUES (?, 1.0, 20.0, 0.0, 0.0, 1.0016)",
                (mat_id,)
            )
            conn.execute(
                "INSERT OR IGNORE INTO dielectrics (material_id, frequency_hz, temperature_C, real_permittivity, imag_permittivity) "
                "VALUES (?, 1e3, 20.0, 80.1, 0.0)",
                (mat_id,)
            )
        elif name == "PMMA":
            conn.execute(
                "INSERT OR IGNORE INTO viscoelasticity (material_id, frequency_hz, temperature_C, storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s) "
                "VALUES (?, 1.0, 20.0, 3e9, 1e8, NULL)",
                (mat_id,)
            )
            conn.execute(
                "INSERT OR IGNORE INTO dielectrics (material_id, frequency_hz, temperature_C, real_permittivity, imag_permittivity) "
                "VALUES (?, 1e3, 20.0, 3.0, 0.01)",
                (mat_id,)
            )
        elif name == "DPPC":
            conn.execute(
                "INSERT OR IGNORE INTO viscoelasticity (material_id, frequency_hz, temperature_C, storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s) "
                "VALUES (?, 1.0, 25.0, 1e7, 1e6, 80.0)",
                (mat_id,)
            )
            conn.execute(
                "INSERT OR IGNORE INTO dielectrics (material_id, frequency_hz, temperature_C, real_permittivity, imag_permittivity) "
                "VALUES (?, 1e3, 25.0, 2.5, 0.05)",
                (mat_id,)
            )
        conn.commit()

        # 5. Load Optical Data from YAML
        yaml_path = find_yaml(data_root, mat)

        if yaml_path is not None:
            ftype_str = detect_formula_type(yaml_path)
            print(f"  → {yaml_path.relative_to(data_root)}  [{ftype_str}]")

            try:
                wl, n, k, ref, temp = parse_file(yaml_path)
            except Exception as exc:
                print(f"  ✗  Parse error: {exc}")
                summary_rows.append((name, ftype_str, None, None, 0, 0, "FAIL"))
                print()
                continue

            n_rows = insert_nk(conn, mat_id, wl, n, k, ref, temp)
            k_finite = int(np.sum(np.isfinite(k) & ~np.isnan(k))) if k is not None else 0
            k_info = f"k: {k_finite}/{n_rows}" if k is not None else "k: NULL"
            print(f"  ✓  {n_rows:,} rows  |  {k_info}")

            manual = mat.get("manual_nk", [])
            if manual:
                insert_manual_nk(conn, mat_id, manual)
                print(f"  +  {len(manual)} manual point(s) added")

            wl_lo, wl_hi = float(wl.min()), float(wl.max())
            summary_rows.append(
                (name, ftype_str, wl_lo, wl_hi, n_rows, k_finite, "LOADED")
            )

        else:
            manual = mat.get("manual_nk", [])
            if manual:
                n_rows = insert_manual_nk(conn, mat_id, manual)
                wls = [e["wavelength_nm"] for e in manual]
                k_pts = sum(1 for e in manual if e.get("k") is not None)
                print(f"  ✗  Not in RI.info — inserted {n_rows} manual point(s)")
                summary_rows.append(
                    (name, "manual", min(wls), max(wls), n_rows, k_pts, "MANUAL")
                )
            else:
                print("  ✗  Not found — material record only, no optical data")
                summary_rows.append((name, "—", None, None, 0, 0, "NOT_FOUND"))

        print()

    print_summary(summary_rows)
    spot_check(conn)
    conn.close()
    print(f"\nDone → {DB_FILE}")


if __name__ == "__main__":
    main()
