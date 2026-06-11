# Descriptor Population Report
_Generated 2026-06-10 09:23_

## Summary

| Metric | Value |
|--------|-------|
| Total materials | 23 |
| Descriptors populated (any) | 23 |
| Fully populated (all 8 fields) | 19 |
| Partially populated | 4 |
| No descriptors | 0 |
| With Morgan fingerprint | 15 |

## Per-Material Descriptor Coverage

| material_id | Name | exact_mass | tpsa | logp | heavy_atom_count | rotatable_bonds | hbond_donors | hbond_acceptors | aromatic_rings | Morgan FP | Source |
|-------------|------|-----------|------|------|-----------------|-----------------|-------------|-----------------|----------------|-----------|--------|
| 1 | Water | 18.01 | 31.5 | -0.8247 | 1 | 0 | 0 | 0 | 0 | ✓ | rdkit |
| 2 | Gold | 197 | 0 | -0.0025 | 1 | 0 | 0 | 0 | 0 | ✓ | rdkit |
| 3 | SiO2 | 59.97 | 34.14 | -0.6184 | 3 | 0 | 0 | 2 | 0 | ✓ | rdkit |
| 4 | Polystyrene | 106.1 | 0 | 2.249 | 8 | 1 | 0 | 0 | 1 | ✓ | rdkit |
| 5 | DPPC | 733.6 | 111.2 | 10.61 | 50 | 38 | 0 | 8 | 0 | ✓ | rdkit |
| 6 | PMMA | 102.1 | 26.3 | 0.8154 | 7 | 1 | 0 | 2 | 0 | ✓ | rdkit |
| 7 | Ethanol | 46.04 | 20.23 | -0.0014 | 3 | 0 | 1 | 1 | 0 | ✓ | rdkit |
| 8 | DMSO | 78.01 | 17.07 | -0.0053 | 4 | 0 | 0 | 1 | 0 | ✓ | rdkit |
| 9 | PEG | 62.04 | 40.46 | -1.029 | 4 | 1 | 2 | 2 | 0 | ✓ | rdkit |
| 10 | Silicon | 27.98 | 0 | -0.3808 | 1 | 0 | 0 | 0 | 0 | ✓ | rdkit |
| 15 | TiO2 | 79.94 | 34.14 | -0.2401 | 3 | 0 | 0 | 2 | 0 | ✓ | rdkit |
| 16 | PDMS | 164.1 | 29.46 | 1.532 | 9 | 2 | 1 | 2 | 0 | ✓ | rdkit |
| 17 | PEI | 103.1 | 64.07 | -1.507 | 7 | 4 | 3 | 3 | 0 | ✓ | rdkit |
| 18 | BSA | 203.1 | 21.6 | — | 12 | 3 | 0 | 2 | — | — | pubchem_only |
| 20 | ITO | — | — | — | 3 | 0 | 0 | 0 | 0 | — | legacy_migration |
| 21 | Chromium | 51.94 | 0 | -0.0025 | 1 | 0 | 0 | 0 | 0 | ✓ | rdkit |
| 22 | Silver | 106.9 | 0 | -0.0025 | 1 | 0 | 0 | 0 | 0 | ✓ | rdkit |
| 24 | PTFE | 100 | 0 | 1.991 | 6 | 0 | 0 | 0 | 0 | — | legacy_migration |
| 25 | PEEK | 288.3 | 35.53 | 5.084 | 22 | 5 | 0 | 3 | 3 | — | legacy_migration |
| 26 | PVA | 44.03 | 20.2 | 0.5 | 3 | 0 | 1 | 1 | 0 | — | pubchem_only |
| 27 | Nylon66 | 226.3 | 58.2 | 1.353 | 16 | 0 | 2 | 2 | 0 | — | legacy_migration |
| 28 | Al2O3 | 101.9 | 3 | — | 5 | 0 | 0 | 3 | — | — | pubchem_only |
| 29 | ZnO | 79.92 | 17.1 | — | 2 | 0 | 0 | 1 | — | — | pubchem_only |

## Failures & Partial Fills

| material_id | Name | Partial | Missing Fields | Reason |
|-------------|------|---------|----------------|--------|
| 1 | Water | no | none | ok |
| 2 | Gold | no | none | ok |
| 3 | SiO2 | no | none | ok |
| 4 | Polystyrene | no | none | ok |
| 5 | DPPC | no | none | ok |
| 6 | PMMA | no | none | ok |
| 7 | Ethanol | no | none | ok |
| 8 | DMSO | no | none | ok |
| 9 | PEG | no | none | ok |
| 10 | Silicon | no | none | ok |
| 15 | TiO2 | no | none | ok |
| 16 | PDMS | no | none | ok |
| 17 | PEI | no | none | ok |
| 18 | BSA | yes | logp, aromatic_rings | PubChem found compound but no SMILES available |
| 20 | ITO | yes | exact_mass, tpsa, logp | PubChem lookup returned nothing |
| 21 | Chromium | no | none | ok |
| 22 | Silver | no | none | ok |
| 24 | PTFE | no | none | PubChem lookup returned nothing |
| 25 | PEEK | no | none | PubChem lookup returned nothing |
| 26 | PVA | no | none | PubChem found compound but no SMILES available |
| 27 | Nylon66 | no | none | PubChem lookup returned nothing |
| 28 | Al2O3 | yes | logp, aromatic_rings | PubChem found compound but no SMILES available |
| 29 | ZnO | yes | logp, aromatic_rings | PubChem found compound but no SMILES available |

