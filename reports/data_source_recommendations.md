# Data Source Recommendations

Coverage % is fraction of the 23 materials in `materials` table that currently have at least one non-null value for this property.

| Property | Current Coverage % | Candidate Sources |
|---|---:|---|
| n / k (optical constants) | 100.0 | RefractiveIndex.INFO (refractiveindex.info) — tabulated n,k for ~3 000 materials; also Filmetrics, SOPRA database |
| bandgap (eV) | 0.0 | Materials Project (materialsproject.org) — DFT bandgaps; AFLOW; NOMAD repository |
| dielectric tensor / static ε | 91.3 | Materials Project `dielectric` endpoint; ICSD+DFT compiled datasets; Springer Materials |
| density (g/cm³) | 100.0 | PubChem Compound API (`density` property); Materials Project; CRC Handbook; NIST WebBook |
| elastic constants (GPa) | 39.1 | Materials Project elasticity dataset; AFLOW AFEL; Citrination; Matminer datasets |
| viscosity / rheology | 26.1 | Polymer Handbook (Brandrup et al.); NIST TDE; literature search (Scopus/WoS) for each polymer |
| neutron SLD | 100.0 | NIST SLD calculator (https://www.ncnr.nist.gov/resources/sldcalc.html); SasView SLD calculator — computable from formula + density |
| X-ray SLD | 100.0 | Same as neutron SLD — computable from formula + density + NIST atomic scattering factors (Henke tables) |
| phase / crystal structure | 0.0 | Materials Project `crystal_system`, `spacegroup`; ICSD; COD (Crystallography Open Database) |
| deposition method / substrate / thickness | 0.0 | No automated DB; requires per-paper extraction or lab records. Consider adding to `sources` table metadata fields. |
| smiles / InChIKey | 82.6 | PubChem CID → SMILES via PubChem REST API; already partially populated (pubchem_cid present for some) |
| chemical descriptors (TPSA, logP…) | 95.7 | RDKit (from SMILES, free); PubChem REST for computed properties; descriptor_failures table lists 23 failures |

## Priority Order

1. **Bandgap** — 0 % coverage; available from Materials Project for all inorganic entries
2. **Phase / crystal structure** — 0 % coverage; critical for SLD and dielectric interpretation
3. **Deposition method / substrate / thickness** — structural metadata; cannot be computed; must come from literature or lab records
4. **Dielectric tensor** — partial coverage (21/23 in physical_properties, but only scalar; tensor components missing)
5. **Elastic constants** — only 9/23 materials have mechanical data; Materials Project covers the inorganics
6. **Viscosity** — only 7 records; polymer data from Polymer Handbook or direct literature
7. **SMILES / descriptors** — 23 descriptor_failures logged; fix by resolving SMILES for inorganic polymers via PubChem or custom mol-file

## Notes on Computable Properties

- **X-ray SLD** and **neutron SLD** are computable from `formula` + `density_g_cm3` using Henke/NIST tables — no external data acquisition needed once density is populated.
- **eps_real / eps_imag** at optical frequencies are already computed as generated columns in `optical_dispersion`.
- **Molecular descriptors** (TPSA, logP, heavy-atom count) are computable from SMILES using RDKit — no external DB needed for materials with valid SMILES.
