"""Check whether a ModalFit clone is at the exact commit materials_db.export.modalfit_contract pins (MODALFIT_COMMIT_SHA).

Library home of check_pin() (moved verbatim from scripts/verify_modalfit_pin.py, which keeps the command-line report) so the
installed launcher bridge does not import from scripts/.
"""

import subprocess
from pathlib import Path

from materials_db.export.modalfit_contract import MODALFIT_COMMIT_SHA, MODALFIT_REPO_URL


def check_pin(clone_path) -> dict:
    """Library entry point (the launcher's modalfit_bridge.py uses this
    directly, so it checks the same pin the same way rather than
    re-deriving a second git-rev-parse call): returns
    {"match": bool, "actual_sha": str, "actual_remote": str,
    "pinned_sha": str, "pinned_repo": str}. Raises FileNotFoundError if
    clone_path isn't a git repo at all -- a caller decides how to report
    that; this function only decides MATCH/MISMATCH."""
    clone_path = Path(clone_path)
    if not (clone_path / ".git").is_dir():
        raise FileNotFoundError(f"{clone_path} is not a git repository.")

    actual_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=clone_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    actual_remote = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=clone_path, capture_output=True, text=True
    ).stdout.strip()

    return dict(match=(actual_sha == MODALFIT_COMMIT_SHA), actual_sha=actual_sha,
                actual_remote=actual_remote, pinned_sha=MODALFIT_COMMIT_SHA,
                pinned_repo=MODALFIT_REPO_URL)
