# materials-db

Unified SQLite database of optical and physical constants for multi-instrument
thin film modeling (ellipsometry, XRR, SPR, QCM-D). Soft matter focus.

## Layout

| File / Directory | Description |
|---|---|
| `materials.db` | SQLite database — ready to query |
| `init_db.py` | Full initialization pipeline (schema → fetch → seed → audit) |
| `requirements.txt` | Python dependencies |
| `core/schema.sql` | DDL: tables, indexes, `spr_data` view |
| `core/seed_manual.sql` | Idempotent seed for manual-entry materials (PEG, DPPC, Silicon) |
| `core/audit.py` | DB integrity checks and DPPC auto-remediation |
| `pipeline/fetch_optical_data.py` | Clone refractiveindex.info YAML DB, parse and load optical data |
| `calculators/xrr_engine.py` | X-ray SLD / ρₑ calculator (CLI) |
| `calculators/simulate_xrr.py` | Parratt XRR reflectivity simulator (CLI) |

## Schema

```sql
materials  (id, name, formula, material_class, notes, density_g_cm3)
optical_nk (id, material_id → materials, wavelength_nm, n, k, source_ref, temperature_C)
```

`k = NULL` means no extinction data exists for that material — it is never
stored as `0.0` for absent data.  Wavelengths are always in **nm** internally
(source YAML files use µm; converted on parse).

## Quick start

```bash
pip install -r requirements.txt
python init_db.py   # clones RI.info DB (~200 MB, first run only), builds materials.db
```

Or run steps individually:

```bash
sqlite3 materials.db < core/schema.sql
python pipeline/fetch_optical_data.py
sqlite3 materials.db < core/seed_manual.sql
python core/audit.py
```

## Materials loaded

| Material | Formula | Class | WL range | k | Source |
|---|---|---|---|---|---|
| Water | H₂O | solvent | 200–3000 nm | ✓ | Hale & Querry 1973 |
| Gold | Au | metal | 203–1937 nm | ✓ | Johnson & Christy 1972 |
| SiO₂ | SiO₂ | oxide | 210–3000 nm | NULL | Malitson 1965 (Sellmeier) |
| Polystyrene | (C₈H₈)ₙ | polymer | 437–1052 nm | NULL | Sultanova 2009 |
| PMMA | (C₅H₈O₂)ₙ | polymer | 420–1620 nm | NULL | Beadie 2015 |
| Ethanol | C₂H₆O | solvent | 200–2800 nm | ✓ | Sani & Dell'Oro 2016 |
| DMSO | C₂H₆OS | solvent | 200–1700 nm | NULL | Li 2022 |
| DPPC | C₄₀H₈₀NO₈P | lipid | 633 nm | NULL | Chou et al. *Biophys J* 2010 |
| PEG | (C₂H₄O)ₙ | polymer | 589 nm | NULL | Brandrup *Polymer Handbook* 4th ed. |
| Silicon | Si | semiconductor | — | — | Deslattes et al. 1980 (density only) |

## Calculators

```bash
# X-ray electron density and SLD
python calculators/xrr_engine.py --material PMMA

# Parratt reflectivity simulation
python calculators/simulate_xrr.py \
    --stack "Vacuum,PMMA:120,Gold:250,Silicon" \
    --qmin 0.01 --qmax 0.5 --qpts 500 \
    --output xrr_simulation_output.csv
```

## SPR view

```sql
SELECT * FROM spr_data WHERE material_name = 'Water';
-- Returns n, k at 633, 785, 980 nm via linear interpolation.
-- NULL if no data within 10 nm of the target wavelength.
```

## Dispersion formula convention

For formula-based entries the Sellmeier evaluator uses:

```
n² = 1 + c₀ + Σᵢ Bᵢλ²/(λ²−Cᵢ²)
```

where `c₀ = 0` in the current refractiveindex.info YAML format.

## License

Data sourced from [refractiveindex.info](https://refractiveindex.info) (CC0).
Pipeline and schema: MIT.
