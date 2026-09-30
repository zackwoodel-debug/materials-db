# Installation: what works installed, and what needs a checkout

`pip install .` (or the wheel) installs one package, `materials_db`, with its core dependencies (numpy, pandas, periodictable,
pydantic, rich). Extras add features: `ingest` (refractiveindex.info / PubChem parsing), `api` (FastAPI server, local-LLM SQL
agent), `mcp` (MCP server), `release` (the release build and family pipelines in `scripts/`), `analysis` (exploratory scripts),
`dev` (tests, ruff, setuptools). The tested, hash-pinned set is `requirements.lock`.

The published data itself is not in the package: it is the release (`materials-db-vX.Y.Z.sqlite` and its folder, from the GitHub
release). The repository's curated inputs (`data/`, `scripts/`, the refractiveindex.info checkout) are not in the package either.

## Works from an installed wheel

Checked by `tests/test_wheel_install.py` (fresh venv, `python -I`, no checkout on `sys.path`) and in CI by
`.github/ci/wheel_smoke.py` (every module imports, except the checkout-only one below and modules whose extra is absent).

| Feature | Module | Notes |
|---|---|---|
| Read-only access to a release (library, HTTP, MCP) | `materials_db.access` (`db`, `http` with `api`, `mcp_server` with `mcp`) | Point it at a release with `$MATERIALS_DB_RELEASE` (folder or `.sqlite`). **Primary-dataset selection and the model-fit flag need a checkout** (below): without one, `ReleaseDB.info()["primary_unavailable"]` says so and callers must name a dataset; nothing is guessed. |
| ModalFit export | `materials_db.export.modalfit`, `.citations`, `.modalfit_pin` | Pass the database explicitly (`export_layer(db, ...)`); `DEFAULT_DB` points into a checkout. **Limitation:** the Materials Project id lookup (`_lookup_mp_id`) reads the checkout's `data/*.csv`; installed, it finds none and exports `mp_id` as missing for every material. Use a checkout for exports that need `mp_id`. |
| ModalFit launcher | `materials_db.launcher` | Set `$MODALFIT_PATH` to the ModalFit clone; the `.modalfit_path` file is looked up in a checkout. |
| XRR calculators and Parratt simulation | `materials_db.calculators`, `materials_db.simulation` | Pass `--db`; the default is a checkout's `data/materials.db`. |
| Package data | `core/schema.sql`, `core/seed_manual.sql`, `chat/ui.html` | Shipped in the wheel. |

## Needs a checkout

| Feature | Why |
|---|---|
| Release build, family pipelines, descriptors, ML sets (`scripts/`) | They read the curated inputs in `data/` and the refractiveindex.info checkout; `scripts/` is not a package. |
| Primary dataset / model-fit flag in `materials_db.access` | Decided by `data/step1_selections*.json`, the curated lists in `scripts/` and the refractiveindex.info files. Found at `$MATERIALS_DB_REPO`, else the checkout the package runs from (`materials_db.access.checkout`). |
| `materials_db.verify_all` | The checkout's self-test harness; imports the legacy `src/db` and `src/pipeline` packages, which are deliberately not installed. Run it as `PYTHONPATH=.:src python3 src/materials_db/verify_all.py`. |
| Legacy MatChat stack: `materials_db.launch`, `.verify`, `.core.audit`, `.api.server`, `.pipeline.stack_exporter`, `.pipeline.fetch_*` | They read or write the legacy `data/materials.db` in a checkout. They import when installed but have no database there. |
| `materials_db.init_db` | Rebuilds the legacy `data/materials.db`. **Currently broken:** its step paths still point at the pre-`src/` layout (`<repo>/core/schema.sql`, `<repo>/pipeline/...`), so it aborts at step 1. Not fixed, because a working `init_db` fetches from the network and rewrites the legacy database that `verify_all` and the guard tests read: that is a data decision, pending. |
