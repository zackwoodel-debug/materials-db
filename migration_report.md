# Migration Report

## Summary

| Item | Count |
| --- | ---: |
| legacy tables preserved | 11 |
| materials | 23 |
| optical dispersion | 2819 |
| mechanical properties | 11 |
| rheology | 7 |
| physical properties | 167 |
| chemical descriptors | 0 |
| consensus properties | 122 |
| sources | 41 |

## Descriptor Skips

- Water: RDKit not installed
- Gold: RDKit not installed
- SiO2: RDKit not installed
- Polystyrene: RDKit not installed
- DPPC: RDKit not installed
- PMMA: RDKit not installed
- Ethanol: RDKit not installed
- DMSO: RDKit not installed
- PEG: RDKit not installed
- Silicon: RDKit not installed
- TiO2: RDKit not installed
- PDMS: RDKit not installed
- PEI: RDKit not installed
- BSA: missing SMILES
- ITO: missing SMILES
- Chromium: RDKit not installed
- Silver: RDKit not installed
- PTFE: missing SMILES
- PEEK: missing SMILES
- PVA: missing SMILES
- Nylon66: missing SMILES
- Al2O3: missing SMILES
- ZnO: missing SMILES

## Notes

- The source database is not modified.
- Raw legacy tables are copied into the normalized target with `legacy_` prefixes.
- The migration writes a normalized database and does not delete existing measurements.
- Legacy rows without a reference are assigned explicit fallback provenance rows in `sources`.
- Viscosity rows migrated from `viscoelasticity` are flagged when shear rate is absent.
