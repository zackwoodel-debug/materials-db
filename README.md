# materials-db

### What this does

materials-db is a SQLite database of optical and physical constants for soft-matter thin-film modeling, paired with a Python pipeline that fetches dispersion data from the refractiveindex.info YAML repository, seeds manual entries for materials such as DPPC and PEG, and provides a Parratt-recursion XRR simulator that reads material properties directly from the database. The schema covers optical constants (n, k vs. wavelength), X-ray scattering length densities, and a view that interpolates n and k at the discrete wavelengths used by SPR instruments.

### Data flow

Raw YAML dispersion files from the refractiveindex.info repository are parsed and converted from micrometres to nanometres, then written into the SQLite database. Manual-entry materials (lipids, polymers, solvents without RI.info entries) are seeded from `core/seed_manual.sql`. The XRR calculators read formula and density from that same database, compute electron density and SLD, and run the Parratt recursion to produce a reflectivity curve as a CSV file.

### Quickstart

```bash
python init_db.py
python calculators/simulate_xrr.py --stack "Vacuum,PMMA:120,Gold:250,Silicon"
python calculators/xrr_engine.py --material PMMA
```

`init_db.py` runs the full four-step pipeline (schema → fetch → seed → audit) and hard-stops on any failure. Subsequent runs are safe because seeding uses `INSERT OR IGNORE` and fetching clears and repopulates the optical tables.

### Verification checklist

1. `python core/audit.py` — all checks should print PASS or WARN; any FAIL indicates a missing material row or a broken unit-conversion in the fetch pipeline.
2. `python verify_all.py` — 15 assertions covering DB round-trips, CSV parsing, and Parratt physics (TER plateau, high-Q decay); exits 0 on success.
3. `sqlite3 materials.db "SELECT * FROM spr_data LIMIT 5;"` — should return n and k values at 633, 785, and 980 nm for at least Water and Gold; NULL means no optical data within 10 nm of the target wavelength.
