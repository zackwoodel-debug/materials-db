# Materials Database Expansion Plan

This document outlines the research, database design, and implementation strategies to transform `materials-db` into a robust, referenced database for thin-film materials informatics.

---

## 1. Updated Database Schema

To support citations for every data point and accommodate the new mechanical, dielectric, chemical, and scattering properties, we propose a normalized schema. 

### Schema Diagram (Entity-Relationship)

```mermaid
erDiagram
    materials ||--o{ chemical_descriptors : has
    materials ||--o{ optical_nk : has
    materials ||--o{ viscoelasticity : has
    materials ||--o{ dielectrics : has
    materials ||--o{ calculated_slds : has
    references ||--o{ optical_nk : cites
    references ||--o{ viscoelasticity : cites
    references ||--o{ dielectrics : cites
    references ||--o{ calculated_slds : cites
    materials {
        int id PK
        string name UNIQUE
        string formula
        string smiles
        float molecular_weight
        string material_class
        string notes
    }
    references {
        int id PK
        string doi UNIQUE
        string citation_text
        string url
        string bibtex
    }
    chemical_descriptors {
        int id PK
        int material_id FK
        string descriptor_name
        float value
        string source_library
    }
    optical_nk {
        int id PK
        int material_id FK
        int reference_id FK
        float wavelength_nm
        float n
        float k
        float temperature_C
    }
    viscoelasticity {
        int id PK
        int material_id FK
        int reference_id FK
        float frequency_hz
        float temperature_C
        float storage_modulus_pa
        float loss_modulus_pa
        float viscosity_mpa_s
    }
    dielectrics {
        int id PK
        int material_id FK
        int reference_id FK
        float frequency_hz
        float temperature_C
        float real_permittivity
        float imag_permittivity
    }
    calculated_slds {
        int id PK
        int material_id FK
        int reference_id FK
        float energy_ev
        float wavelength_nm
        float xray_sld_real
        float xray_sld_imag
        float neutron_sld_real
    }
```

### SQL Implementation (`core/schema_v2.sql`)

```sql
-- References lookup table for robust citations
CREATE TABLE IF NOT EXISTS references_db (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doi           TEXT    UNIQUE,
    citation_text TEXT    NOT NULL,
    url           TEXT,
    bibtex        TEXT
);

-- Core materials table (expanded with smiles and molecular_weight)
CREATE TABLE IF NOT EXISTS materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    formula          TEXT,
    smiles           TEXT,
    molecular_weight REAL,
    material_class   TEXT,
    notes            TEXT
);

-- Chemical descriptors key-value store (dynamic & extensible)
CREATE TABLE IF NOT EXISTS chemical_descriptors (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    descriptor_name TEXT   NOT NULL,
    value          REAL    NOT NULL,
    source_library TEXT,
    UNIQUE(material_id, descriptor_name)
);

-- Optical dispersion table linked to references
CREATE TABLE IF NOT EXISTS optical_nk (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id   INTEGER REFERENCES references_db(id),
    wavelength_nm  REAL    NOT NULL,
    n              REAL    NOT NULL,
    k              REAL,
    temperature_C  REAL,
    UNIQUE(material_id, wavelength_nm, temperature_C)
);

-- Viscoelastic properties linked to references
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

-- Dielectric properties linked to references
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

-- Calculated Scattering Length Densities (SLD) as function of Energy
CREATE TABLE IF NOT EXISTS calculated_slds (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id), -- density source
    energy_ev         REAL    NOT NULL,
    wavelength_nm     REAL    NOT NULL,
    xray_sld_real     REAL    NOT NULL, -- Å⁻²
    xray_sld_imag     REAL,             -- Å⁻²
    neutron_sld_real  REAL    NOT NULL, -- Å⁻²
    neutron_sld_imag  REAL              -- Å⁻² (absorption)
);
```

---

## 2. Ingesting PubChem Data

For small molecules, we can auto-populate `formula`, `smiles`, and `molecular_weight` using the PubChem PUG REST API. 

For polymers (e.g., PMMA, PEG, Polystyrene) or lipids (e.g., DPPC), PubChem queries by name may return a `404` or represent only the monomer. We resolve this by using a **hybrid parser**:
1. Check PubChem for the compound name.
2. If found, extract properties.
3. If not found, fall back to a local dictionary of manual entries (specifically defined for polymer repeating units and complex lipids).

### Python PubChem Client Implementation

```python
import requests
from typing import Dict, Any, Optional

def get_pubchem_data(name: str) -> Optional[Dict[str, Any]]:
    """
    Fetch formula, molecular weight, and Canonical SMILES from PubChem by name.
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/MolecularFormula,MolecularWeight,CanonicalSMILES/JSON"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            props = r.json()["PropertyTable"]["Properties"][0]
            return {
                "formula": props.get("MolecularFormula"),
                "molecular_weight": float(props.get("MolecularWeight", 0)),
                "smiles": props.get("CanonicalSMILES") or props.get("ConnectivitySMILES")
            }
    except Exception as e:
        print(f"PubChem resolution failed for {name}: {e}")
    return None
```

---

## 3. Computing Cheminformatics Descriptors

Once a material has a valid `smiles` string (from PubChem or manual fallback), we can compute chemical descriptors using **RDKit**. 

### Code Snippet for RDKit Descriptor Extraction

```python
from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski

def compute_descriptors(smiles: str) -> Dict[str, float]:
    """
    Compute standard 2D cheminformatics descriptors from SMILES.
    """
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        raise ValueError("Invalid SMILES string")
        
    return {
        "logP": float(Crippen.MolLogP(mol)),
        "TPSA": float(Descriptors.TPSA(mol)),
        "h_bond_donors": float(Lipinski.NumHDonors(mol)),
        "h_bond_acceptors": float(Lipinski.NumHAcceptors(mol)),
        "rotatable_bonds": float(Lipinski.NumRotatableBonds(mol)),
        "exact_mass": float(Descriptors.ExactMolWt(mol)),
        "molar_refractivity": float(Crippen.MolMR(mol))
    }
```

---

## 4. Wavelength, Energy, and Frequency Conversions

Physical properties are often reported along different coordinates:
- Optical constants ($n$, $k$) as a function of wavelength $\lambda$ (nm) or energy $E$ (eV).
- Viscoelastic properties ($G'$, $G''$, viscosity $\eta$) and dielectric constants ($\epsilon$) as a function of frequency $f$ (Hz) or angular frequency $\omega$ (rad/s).

We implement a conversion class to map all parameters onto a unified axis during query or insertion:

```python
class EnergyConverter:
    H_PLANCK_EV_S = 4.135667697e-15  # Planck constant in eV·s
    C_NM_S = 2.99792458e17          # Speed of light in nm/s
    HC_EV_NM = 1239.84193           # hc in eV·nm

    @classmethod
    def wl_to_energy(cls, wl_nm: float) -> float:
        """Convert wavelength (nm) to photon energy (eV)."""
        return cls.HC_EV_NM / wl_nm

    @classmethod
    def energy_to_wl(cls, energy_ev: float) -> float:
        """Convert photon energy (eV) to wavelength (nm)."""
        return cls.HC_EV_NM / energy_ev

    @classmethod
    def frequency_to_energy(cls, freq_hz: float) -> float:
        """Convert frequency (Hz) to photon energy (eV)."""
        return cls.H_PLANCK_EV_S * freq_hz

    @classmethod
    def energy_to_frequency(cls, energy_ev: float) -> float:
        """Convert photon energy (eV) to frequency (Hz)."""
        return energy_ev / cls.H_PLANCK_EV_S

    @classmethod
    def wl_to_frequency(cls, wl_nm: float) -> float:
        """Convert wavelength (nm) to frequency (Hz)."""
        return cls.C_NM_S / wl_nm

    @classmethod
    def frequency_to_wl(cls, freq_hz: float) -> float:
        """Convert frequency (Hz) to wavelength (nm)."""
        return cls.C_NM_S / freq_hz
```

---

## 5. X-ray and Neutron SLD Derivations

Scattering Length Density (SLD) can be calculated dynamically from formula and mass density.

### A. X-ray SLD (Energy-Dependent)

The X-ray Scattering Length Density ($\text{SLD}_x$) is given by:

$$\text{SLD}_x(E) = r_e \cdot \rho_e(E) = r_e \frac{\rho N_A}{M_w} \sum_{i} n_i \left( Z_i + f_{1,i}(E) + i f_{2,i}(E) \right)$$

Where:
- $r_e = 2.81794 \times 10^{-5} \text{ Å}$ is the classical electron radius.
- $\rho$ is the mass density of the material ($\text{g/cm}^3$).
- $N_A = 6.02214 \times 10^{23} \text{ mol}^{-1}$ is Avogadro's number.
- $M_w$ is the molecular weight ($\text{g/mol}$).
- $n_i$ is the number of atoms of element $i$ in the chemical formula.
- $Z_i$ is the atomic number (number of protons) of element $i$.
- $f_{1,i}(E)$ and $f_{2,i}(E)$ are the energy-dependent anomalous dispersion corrections (from the Henke tables).

#### X-ray SLD Python Implementation

```python
import numpy as np

# Classical electron radius in Angstroms
R_E = 2.8179403e-5
NA = 6.02214076e23

def compute_xray_sld(
    formula_counts: dict[str, int], 
    density: float, 
    mw: float, 
    energy_ev: float,
    f1_f2_lookup_func = None
) -> complex:
    """
    Compute complex energy-dependent X-ray SLD in Å⁻².
    """
    # Sum over components
    z_eff = 0.0
    for elem, count in formula_counts.items():
        # Retrieve atomic number (Z)
        z = ATOMIC_NUMBERS[elem]
        # Retrieve f1 and f2 anomalous dispersion factors (if available)
        f1, f2 = 0.0, 0.0
        if f1_f2_lookup_func:
            f1, f2 = f1_f2_lookup_func(elem, energy_ev)
            
        z_eff += count * (z + f1 + 1j * f2)

    # Electron density: (density * NA * z_eff) / (mw * 1e24)
    rho_e = (density * NA * z_eff) / (mw * 1e24)
    sld = rho_e * R_E
    return sld
```

### B. Neutron SLD (Isotope-Specific)

The Neutron Scattering Length Density ($\text{SLD}_n$) is isotope-dependent:

$$\text{SLD}_n = \frac{\rho N_A}{M_w} \sum_{i} n_i b_i$$

Where:
- $b_i$ is the bound coherent neutron scattering length of isotope $i$ (in units of length, e.g., $\text{fm} = 10^{-15} \text{ m} = 10^{-5} \text{ Å}$).

Because **deuteration** is a critical contrast-matching tool in soft-matter neutron reflectometry, the formula parsing must support isotope labels (e.g., `D` for Deuterium, separate from `H` for Hydrogen).

#### Bound Coherent Scattering Lengths ($b_i$) Lookup Table (in fm)

| Isotope/Element | $b_i$ (fm) |
| :--- | :--- |
| **H** (Hydrogen) | -3.7406 |
| **D** / **[2H]** (Deuterium) | 6.6710 |
| **C** (Carbon) | 6.6460 |
| **N** (Nitrogen) | 9.3600 |
| **O** (Oxygen) | 5.8030 |
| **P** (Phosphorus) | 5.1300 |
| **S** (Sulfur) | 2.8470 |
| **Si** (Silicon) | 4.1491 |
| **Au** (Gold) | 7.6300 |

#### Neutron SLD Python Implementation

```python
# Coherent scattering lengths in Angstroms (1 fm = 1e-5 Angstroms)
B_COH = {
    "H": -3.7406e-5,
    "D":  6.6710e-5,
    "C":  6.6460e-5,
    "N":  9.3600e-5,
    "O":  5.8030e-5,
    "P":  5.1300e-5,
    "S":  2.8470e-5,
    "Si": 4.1491e-5,
    "Au": 7.6300e-5,
}

def compute_neutron_sld(formula_counts: dict[str, int], density: float, mw: float) -> float:
    """
    Compute real Neutron SLD in Å⁻² based on isotopic composition.
    """
    b_total = 0.0
    for elem, count in formula_counts.items():
        if elem not in B_COH:
            raise ValueError(f"Neutron scattering length unknown for element {elem}")
        b_total += count * B_COH[elem]
        
    sld_n = (density * NA * b_total) / (mw * 1e24)
    return sld_n
```

---

## 6. Implementation Action Plan

To execute this database overhaul:
1. **Rebuild Schema**: Write the schema migrations to `core/schema_v2.sql`.
2. **Expand Pipeline Ingestion**:
   - Update `pipeline/fetch_optical_data.py` to query PubChem.
   - Integrate RDKit to compute chemical descriptors.
   - Populate references using the DOIs of refractiveindex.info source files.
3. **Write SLD Calculator Service**:
   - Package the X-ray/Neutron SLD math into a module `calculators/sld_calculator.py`.
   - Update `xrr_engine.py` to support these dynamic SLD formulas directly.
4. **Upgrade tests & verification**:
   - Add new test cases in `verify_all.py` validating chemical descriptor lookups, reference links, and neutron SLD calculation results.
