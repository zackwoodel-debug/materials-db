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

What works from an installed wheel and what needs a checkout: `docs/installation.md`. Note: `init_db` is currently broken (its step paths predate the `src/` layout; see that document) and aborts at step 1.

`init_db.py` runs the full four-step pipeline (schema → fetch → seed → audit) and hard-stops on any failure. Subsequent runs are safe because seeding uses `INSERT OR IGNORE` and fetching clears and repopulates the optical tables.

### Verification checklist

1. `python -m materials_db.core.audit` — a presence check on the legacy `data/materials.db` only: it prints each table's row count and "Audit passed" if the file exists and at least one row exists. It does not check values, units or provenance, and run as a script it exits 0 even when it prints a failure, so it is not a quality gate. The release build's validation stages (`scripts/build_release.py`) and the test suite are where data is checked.
2. `PYTHONPATH=.:src python3 src/materials_db/verify_all.py` — 34 checks covering DB round-trips, CSV parsing, SLD values, stack export and Parratt physics (TER plateau, high-Q decay); exits 0 on success.
3. `sqlite3 data/materials.db "SELECT * FROM spr_data LIMIT 5;"` — should return n and k values at 633, 785, and 980 nm for at least Water and Gold; NULL means no optical data within 10 nm of the target wavelength.

### Downloadable dataset (releases)

`python3 scripts/build_release.py --version X.Y.Z` builds one SQLite database holding every curated family (oxides,
nitrides, polymers, inorganic batch 3, halides, chalcogenides, liquids, semiconductors, inorganic batch 4, glasses, optical media, liquid crystals, biological media, gases), plus compositional, structural and molecular descriptors.
It also writes a CSV of every table, the family tables with their per-material flags, a data card, a manifest and
checksums. The output goes to `release/` (not committed); publish it as a GitHub release. The build runs offline and
stops if any validation check fails. Descriptor inputs and their rules are in `data/descriptors/README.md`.

### Access for programs and AI assistants

`src/materials_db/access/` is a read-only query layer over a release: search, a material's full record with every optical
dataset and its source, n and k at any wavelength (only inside a dataset's range, default the primary dataset), source points,
like-for-like comparisons and read-only SQL. The release is found at `$MATERIALS_DB_RELEASE` or as the newest `release/materials-db-v*/`.

- MCP server (Claude Code, Claude Desktop, any MCP client), after `pip install mcp`:
  `claude mcp add materials-db -e PYTHONPATH="$PWD/src" -- python3 -m materials_db.access.mcp_server`
- HTTP API with OpenAPI docs at `/docs`: `PYTHONPATH=src uvicorn materials_db.access.http:app`
- Python: `from materials_db.access import ReleaseDB; ReleaseDB().nk_at("GaAs", 633)`

The older `src/materials_db/api/server.py` (MatChat, stack builder) still reads the legacy `data/materials.db`.

### Browse in a web browser (Datasette)

`python3 scripts/build_datasette.py` prepares `release/browse-vX.Y.Z/` (the release file linked unchanged, a `families.db`
with a one-row-per-material index and the family tables, and column descriptions from the data dictionary). Then
`pip install datasette` and run the `datasette serve ...` command the script prints; saved queries include source points
near a wavelength, a material's datasets and sources, datasets that disagree, and materials by n(633 nm).

### Generated files at the repository root

`analysis_dataset.csv`, `correlation_summary.csv`, `correlation_summary_dielectric.csv`, `migration_report.md`, `schema_audit.md` and `ER_diagram.png` are outputs of the analysis and migration scripts that write them (`scripts/materials_analysis.py`, `scripts/enrich_and_reanalyze.py`, `scripts/dielectric_enrich_analyze.py`, `migration_scripts/`). They stay committed as the record of those runs: `analysis_dataset.csv` is also an input (`scripts/analysis_publication.py` reads it; `migrations/001_constraints_indexes.sql` names it), and `updated_sql_schema.sql` is a curated schema that three tests read. Do not ignore or delete them in bulk; replace one only by rerunning the script that writes it, and commit the new version with that script's change. Release packages (`release/`), the per-family test databases a loader rebuilds (listed in `.gitignore`; the release's base `data/materials_oxide_test.db` is tracked) and build output (`build/`, `dist/`, `*.egg-info/`) are regenerable and ignored.

### License

Code: MIT (`LICENSE`). Data: CC BY 4.0, with attribution to the upstream sources (`DATA_LICENSE.md`).
