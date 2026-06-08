# materials-db

### What this does

materials-db is a SQLite database of optical and physical constants for soft-matter thin-film modeling, paired with a Python pipeline that fetches dispersion data from the refractiveindex.info YAML repository, seeds manual entries for materials such as DPPC and PEG, and provides a Parratt-recursion XRR simulator that reads material properties directly from the database. The schema covers optical constants (n, k vs. wavelength), X-ray scattering length densities, and a view that interpolates n and k at the discrete wavelengths used by SPR instruments.

### Data flow

Raw YAML dispersion files from the refractiveindex.info repository are parsed and converted from micrometres to nanometres, then written into the SQLite database. Manual-entry materials (lipids, polymers, solvents without RI.info entries) are seeded from `src/materials_db/core/seed_manual.sql`. The XRR calculators read formula and density from that same database, compute electron density and SLD, and run the Parratt recursion to produce a reflectivity curve as a CSV file.

### Layout

```
materials-db/
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml
├── data/
│   ├── materials.db
│   └── xrr_simulation_output.csv
├── docs/
│   └── database_expansion_plan.md
├── scripts/
│   ├── git-ai-commit.sh
│   ├── run_matchat.sh
│   └── setup.sh
└── src/
    └── materials_db/
        ├── __init__.py
        ├── init_db.py
        ├── launch.py
        ├── verify.py
        ├── verify_all.py
        ├── api/
        ├── calculators/
        ├── chat/
        ├── core/
        ├── pipeline/
        └── simulation/
```

### Quickstart

```bash
pip install -e .
python -m materials_db.init_db
python -m materials_db.calculators.simulate_xrr --stack "Vacuum,PMMA:120,Gold:250,Silicon"
python -m materials_db.calculators.xrr_engine --material PMMA
```

`init_db.py` runs the full four-step pipeline (schema → fetch → seed → audit) and hard-stops on any failure. Subsequent runs are safe because seeding uses `INSERT OR IGNORE` and fetching clears and repopulates the optical tables.

### Verification checklist

1. `python -m materials_db.core.audit` — all checks should print PASS or WARN; any FAIL indicates a missing material row or a broken unit-conversion in the fetch pipeline.
2. `python -m materials_db.verify_all` — 15 assertions covering DB round-trips, CSV parsing, and Parratt physics (TER plateau, high-Q decay); exits 0 on success.
3. `sqlite3 data/materials.db "SELECT * FROM spr_data LIMIT 5;"` — should return n and k values at 633, 785, and 980 nm for at least Water and Gold; NULL means no optical data within 10 nm of the target wavelength.
