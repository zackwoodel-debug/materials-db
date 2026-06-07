# materials-db

Unified SQLite database of optical and physical constants for multi-instrument
thin film modeling (ellipsometry, XRR, SPR, QCM-D). Soft matter focus.

## Contents

| File | Description |
|---|---|
| `materials.db` | SQLite database — ready to query |
| `fetch_optical_data.py` | Pipeline: clones refractiveindex.info, parses YAML, populates DB |
| `audit.py` | Validates DB integrity and code correctness; self-remediates DPPC |
| `schema.sql` | Database schema (DDL only, for reference) |
| `requirements.txt` | Python dependencies |

## Schema

```sql
materials  (id, name, formula, material_class, notes)
optical_nk (id, material_id → materials, wavelength_nm, n, k, source_ref, temperature_C)
```

`k = NULL` means no extinction data exists for that material — it is never
stored as `0.0` for absent data.  Wavelengths are always in **nm** internally
(source YAML files use µm; converted on parse).

## Materials loaded

| Material | Formula | Class | WL range | k | Source |
|---|---|---|---|---|---|
| Water | H₂O | solvent | 200–3000 nm | ✓ | Hale & Querry 1973 |
| Gold | Au | metal | 203–1937 nm | ✓ | Johnson & Christy 1972 |
| SiO₂ | SiO₂ | oxide | 210–3000 nm | NULL | Malitson 1965 (Sellmeier) |
| Polystyrene | (C₈H₈)ₙ | polymer | 437–1052 nm | NULL | Sultanova 2009 |
| DPPC | C₄₀H₈₀NO₈P | lipid | 633 nm | NULL | Chou et al. *Biophys J* 2010 |

## Quick start

```bash
pip install -r requirements.txt
python fetch_optical_data.py   # clones RI.info DB (~200 MB, once) and builds materials.db
python audit.py                # validates DB + code; inserts DPPC point if missing
```

Query example:

```python
import sqlite3
conn = sqlite3.connect("materials.db")

# n,k of gold at 633 nm (nearest point)
row = conn.execute("""
    SELECT wavelength_nm, n, k FROM optical_nk o
    JOIN materials m ON m.id = o.material_id
    WHERE m.name = 'Gold'
    ORDER BY ABS(wavelength_nm - 633) LIMIT 1
""").fetchone()
print(row)  # (632.8, 0.1797, 3.097)
```

## Dispersion formula convention

For formula-based entries (SiO₂, Polystyrene) the Sellmeier evaluator uses:

```
n² = 1 + c₀ + Σᵢ Bᵢλ²/(λ²−Cᵢ²)
```

where `c₀ = 0` in the current refractiveindex.info YAML format (the leading
`1` is implicit, not encoded in the coefficient vector).

## Roadmap

- Additional soft matter: PEG, BSA, POPC, SAMs (thiol monolayers)
- XRR / neutron table: electron density ρₑ, scattering length density (SLD)
- QCM-D table: bulk density, shear modulus G′, viscosity η
- SPR discrete-wavelength table: n,k at 633 nm and 785 nm

## License

Data sourced from [refractiveindex.info](https://refractiveindex.info) (CC0).
Pipeline and schema: MIT.
