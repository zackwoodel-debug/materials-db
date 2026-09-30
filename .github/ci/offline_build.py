"""Full offline release build into a temporary directory (version 0.0.0-ci), then check that it changed nothing in the checkout.

This is the build's validation mode: build_release.py has no --dry-run; a 0.0.0* version is exempt from the CHANGELOG check, and
package(..., out_root=tmp) writes only under tmp (it does not touch CITATION.cff, which only scripts/package_ml_dataset.py writes).
Needs the tracked base DB and the refractiveindex.info checkout at the commit recorded in the release MANIFEST. No network, no
API keys. ~10 minutes.

    python .github/ci/offline_build.py [--keep DIR]    # DIR (outside the checkout) keeps the built package for later jobs
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))  # build_release lives in scripts/ (checkout-only by design)

import build_release as br  # noqa: E402


def status():
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=Path, help="copy the built package here (must be outside the checkout)")
    a = ap.parse_args(argv)
    if a.keep and a.keep.resolve().is_relative_to(ROOT):
        ap.error("--keep must be outside the checkout")
    before = status()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "work.sqlite"
        facts = br.build_db(db)  # raises ReleaseError on any failed validation stage
        out, zpath, manifest = br.package(db, "0.0.0-ci", facts, out_root=tmp)
        print(f"built {out.name}: {manifest['counts']['tables']['materials']} materials, "
              f"{manifest['counts']['tables']['optical_dispersion']:,} optical rows; lock {manifest['dependency_lock']['sha256'][:12]}")
        if a.keep:
            shutil.copytree(out, a.keep / out.name)
    after = status()
    if after != before:
        print("the build changed the checkout:\n" + after)
        return 1
    print("checkout unchanged by the build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
