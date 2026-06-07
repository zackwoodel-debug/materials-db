# Project: materials-db

## Stack
Python 3.11 | sqlite3 | pyyaml | numpy

## Files
- fetch_optical_data.py — main pipeline
- materials.db — sqlite database
- ./refractiveindex.info-database — cloned repo (do not re-clone)

## Schema
materials: id, name, formula, material_class, notes
optical_nk: id, material_id FK, wavelength_nm, n, k, source_ref, temperature_C

## Rules
- k=NULL (never 0) for transparent materials
- wavelength always in nm internally (source files in um, convert on parse)
- formula evaluator: n²=1+c₀+Σ Bᵢλ²/(λ²−Cᵢ²)
- no new dependencies without asking

## Materials loaded
Water, Gold, SiO2, Polystyrene — from refractiveindex.info
DPPC — manual insert, n=1.48 @ 633nm, source: Chou et al. Biophys J 2010

## Next steps
- Add remaining soft matter materials (lipids, PEG, proteins, SAMs)
- Add XRR/neutron table: electron density, SLD
- Add QCM-D table: bulk density, shear modulus G, viscosity
- Add SPR table: n,k at discrete wavelengths 633/785nm