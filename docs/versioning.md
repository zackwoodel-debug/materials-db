# Versioning

materials-db has four versioned things. They change for different reasons, so they have separate version numbers and
are never expected to be equal to each other. Each one has exactly one authoritative place; everything else reads it.

| Axis | What it versions | Authoritative source | Where it is read / recorded |
|---|---|---|---|
| Software | the `materials_db` Python package (code under `src/`) | `version` in `pyproject.toml` | `materials_db.__version__` (via `importlib.metadata`; from an uninstalled checkout, the same `pyproject.toml` field); a release's `MANIFEST.json` `software.materials_db` |
| Dataset release | the published database (`materials-db-vX.Y.Z.sqlite` and its package) | `scripts/build_release.py --version X.Y.Z` | `MANIFEST.json` `version`, file and folder names, the package README and data dictionary titles, `CHANGELOG.md` (a versioned build needs its `## [X.Y.Z]` entry), the git tag `vX.Y.Z` and GitHub release; the ML package and `CITATION.cff` are generated from the release's `MANIFEST.json` |
| Descriptor schema | the layout of `chemical_descriptors.descriptor_json` | `SCHEMA_TAG` in `scripts/release_descriptors.py` | each material's `descriptor_json`; ML feature generation branches on it |
| ModalFit pin | the ModalFit commit whose behaviour the export and launcher were checked against | `MODALFIT_COMMIT_SHA` (and `MODALFIT_COMMIT_DATE`) in `src/materials_db/export/modalfit_contract.py` | `scripts/verify_modalfit_pin.py`, the launcher bridge |

Rules

- Bump the software version when the package's code or behaviour changes; bump the dataset version when a release's
  data changes. A data-only release does not bump the software version, and vice versa.
- Do not copy one axis into another (e.g. the dataset version into `pyproject.toml`).
- `CITATION.cff` at the repository root is written by `scripts/package_ml_dataset.py` (the ML package, from a release's
  `MANIFEST.json`); do not edit it by hand.
- Tests check consistency within each axis, never equality between axes: `tests/test_versioning.py` (software) and
  `tests/test_release_build.py` (dataset version single-sourced across a built package; the manifest records the
  software version).
