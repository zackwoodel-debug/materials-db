"""Features that need a materials-db CHECKOUT, not just a release: which dataset is a material's primary one, and whether a
dataset is a model fit. Both are decided by the repository's selection inputs (data/step1_selections*.json, the curated material
lists in scripts/) and the refractiveindex.info files, which a release package does not carry.

The checkout is $MATERIALS_DB_REPO, else the checkout this package is running from (an installed wheel has none). Its scripts are
loaded by file path; nothing is added to sys.path here. Without a checkout the callers report the feature as unavailable
(ReleaseDB.info()["primary_unavailable"]) instead of guessing.
"""
import importlib.util
import os
from pathlib import Path

REPO_ENV_VAR = "MATERIALS_DB_REPO"
_OWN_CHECKOUT = Path(__file__).resolve().parents[3]  # <checkout>/src/materials_db/access/checkout.py
_loaded = {}


class CheckoutUnavailable(RuntimeError):
    """No materials-db checkout to take the selection inputs from."""


def repository_root():
    """The checkout holding the selection inputs, or None."""
    cand = os.environ.get(REPO_ENV_VAR)
    root = Path(cand).expanduser() if cand else _OWN_CHECKOUT
    return root if (root / "scripts" / "generate_ml_release_set.py").is_file() else None


def load_script(name):
    """scripts/<name>.py of the checkout, imported by file path (cached per checkout)."""
    root = repository_root()
    if root is None:
        raise CheckoutUnavailable(f"needs a materials-db checkout (set ${REPO_ENV_VAR} to one): the selection inputs are not part "
                                  "of a release")
    key = (str(root), name)
    if key not in _loaded:
        spec = importlib.util.spec_from_file_location(f"_materials_db_checkout_{name}", root / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _loaded[key] = module
    return _loaded[key]
