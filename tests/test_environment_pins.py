"""The refractiveindex.info commit CI checks out (refractiveindex_commit.txt) must be the one the local clone is at, so CI tests
exactly the data the releases are built from. Skipped where the clone has no git metadata."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_refractiveindex_clone_is_at_the_pinned_commit():
    pin = (ROOT / "refractiveindex_commit.txt").read_text().strip()
    assert len(pin) == 40 and all(c in "0123456789abcdef" for c in pin)
    try:
        head = subprocess.run(["git", "-C", str(ROOT / "refractiveindex_db"), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("refractiveindex_db is not a git clone here")
    assert head == pin, "refractiveindex_db moved: update refractiveindex_commit.txt (and rebuild the data) or check out the pin"


def test_requirements_test_pins_every_package_exactly():
    lines = [ln.strip() for ln in (ROOT / "requirements-test.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert lines and all("==" in ln for ln in lines)
