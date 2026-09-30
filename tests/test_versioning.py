"""Software version: one authoritative field (pyproject.toml), read at runtime. See docs/versioning.md for the four version axes."""
import importlib.metadata
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import materials_db  # noqa: E402

PYPROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_runtime_version_is_the_pyproject_version():
    assert materials_db.__version__ == PYPROJECT_VERSION


def test_installed_metadata_if_any_is_not_stale():
    # a stale build (e.g. an old *.egg-info next to src/) makes importlib.metadata report the wrong software version
    try:
        installed = importlib.metadata.version("materials_db")
    except importlib.metadata.PackageNotFoundError:
        installed = None  # an uninstalled checkout: __version__ reads pyproject.toml (checked above)
    assert installed in (None, PYPROJECT_VERSION)


def test_versioning_doc_names_each_axis_and_its_authoritative_source():
    doc = (ROOT / "docs" / "versioning.md").read_text()
    for needle in ("pyproject.toml", "build_release.py --version", "SCHEMA_TAG", "MODALFIT_COMMIT_SHA"):
        assert needle in doc
