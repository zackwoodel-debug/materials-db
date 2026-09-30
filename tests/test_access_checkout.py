"""materials_db.access.checkout: checkout-only features are found explicitly, never through sys.path, and are reported as
unavailable (not guessed) when there is no checkout."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.access import checkout  # noqa: E402


def test_own_checkout_is_found(monkeypatch):
    monkeypatch.delenv(checkout.REPO_ENV_VAR, raising=False)
    assert checkout.repository_root() == ROOT


def test_loading_a_script_does_not_touch_sys_path(monkeypatch):
    monkeypatch.delenv(checkout.REPO_ENV_VAR, raising=False)
    before = list(sys.path)
    module = checkout.load_script("dataset_kind")
    assert sys.path == before
    assert Path(module.__file__) == ROOT / "scripts" / "dataset_kind.py"


def test_no_checkout_is_reported_not_guessed(monkeypatch, tmp_path):
    monkeypatch.setenv(checkout.REPO_ENV_VAR, str(tmp_path))  # an explicit repo that is not a checkout: no fallback to our own
    assert checkout.repository_root() is None
    with pytest.raises(checkout.CheckoutUnavailable, match=checkout.REPO_ENV_VAR):
        checkout.load_script("generate_ml_release_set")
