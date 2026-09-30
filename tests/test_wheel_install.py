"""The installed package works without the checkout: the wheel is built from the package's own source files, installed into a
fresh venv, and imported with `python -I` from a directory outside the repository (no PYTHONPATH, no checkout on sys.path).

Offline: the wheel is built with setuptools (the build backend) from the running environment, and the venv sees the running
environment's installed dependencies through a .pth file; the test first checks that environment does not itself contain
materials_db, so nothing but the wheel can supply it. CI's wheel smoke job (.github/ci/wheel_smoke.py) additionally installs the
wheel with the locked dependencies into a venv of its own and imports every module.
"""
import json
import site
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # the checkout side of the parity check
MODULES = [
    "materials_db.export.modalfit", "materials_db.export.citations", "materials_db.export.modalfit_pin",
    "materials_db.launcher.catalog", "materials_db.launcher.library_export", "materials_db.launcher.modalfit_bridge",
    "materials_db.launcher.ambient", "materials_db.access.db", "materials_db.access.checkout",
]
# installed and checkout exports must agree field by field (docs/adr/0001); one oxide, one batch-2 and one element material
PARITY_MATERIALS = ["Aluminium oxide / sapphire", "Zinc sulfide", "Silicon"]
PROBE = """
import importlib, importlib.resources, json, sys
mods = %r
PARITY_MATERIALS = %r
out = {"sys_path": sys.path, "errors": {}}
for m in mods:
    try:
        importlib.import_module(m)
    except BaseException as exc:
        out["errors"][m] = f"{type(exc).__name__}: {exc}"
import materials_db
from materials_db.export.modalfit import RESOLVED_OPTICAL_SOURCE_CITATION
from materials_db.access import checkout
out["file"] = materials_db.__file__
out["version"] = materials_db.__version__
out["citations"] = sorted(RESOLVED_OPTICAL_SOURCE_CITATION)
out["data"] = {p: importlib.resources.files("materials_db").joinpath(p).is_file()
               for p in ("core/schema.sql", "core/seed_manual.sql", "chat/ui.html")}
out["checkout"] = str(checkout.repository_root())
import sqlite3
from materials_db.export.modalfit import export_layer
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
out["layers"] = {n: export_layer(con, n) for n in PARITY_MATERIALS}
print(json.dumps(out))
"""


def _package_sources(dest):
    """What the wheel is built from: pyproject.toml, LICENSE, README.md and src/ (tracked files plus new, non-ignored ones)."""
    names = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z", "--", "pyproject.toml", "LICENSE", "README.md", "src"],
                           cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    for name in filter(None, names):
        src = ROOT / name
        if src.is_file():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            (dest / name).write_bytes(src.read_bytes())


def test_installed_wheel_imports_export_launcher_and_access_without_the_checkout(tmp_path):
    parent_sites = [p for p in site.getsitepackages() if Path(p).is_dir()]
    assert not any((Path(p) / "materials_db").exists() for p in parent_sites), "the running environment already has materials_db"

    src, dist, env, work = tmp_path / "src", tmp_path / "dist", tmp_path / "venv", tmp_path / "work"
    for d in (src, dist, work):
        d.mkdir()
    _package_sources(src)
    subprocess.run([sys.executable, "-c", f"from setuptools import build_meta as b; b.build_wheel({str(dist)!r})"], cwd=src,
                   check=True, capture_output=True)
    wheel = next(dist.glob("materials_db-*.whl"))

    venv.create(env, with_pip=True)
    py = env / "bin" / "python"
    purelib = subprocess.run([py, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], capture_output=True, text=True,
                             check=True).stdout.strip()
    (Path(purelib) / "_parent_env_dependencies.pth").write_text("\n".join(parent_sites) + "\n")
    subprocess.run([py, "-m", "pip", "install", "--no-deps", "--no-index", "-q", str(wheel)], check=True, capture_output=True)

    run = subprocess.run([py, "-I", "-c", PROBE % (MODULES, PARITY_MATERIALS), str(ROOT / "data" / "materials_oxide_test.db")], cwd=work,
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])  # the exporter logs its approximations to stdout first
    assert out["errors"] == {}
    assert Path(out["file"]).is_relative_to(env) and not any(str(ROOT) in p for p in out["sys_path"])
    assert out["citations"] == ["As2S3", "HgS", "Ta2O5", "TeO2", "VO2"]
    assert out["data"] == {"core/schema.sql": True, "core/seed_manual.sql": True, "chat/ui.html": True}
    assert out["checkout"] == "None"  # an installed wheel has no checkout; checkout-only features report themselves unavailable
    # installed == checkout, field by field (ADR 0001: the mp_id map ships in the wheel); the checkout export runs in this process
    import sqlite3
    from materials_db.export.modalfit import export_layer
    checkout_dir = tmp_path / "checkout_export"
    checkout_dir.mkdir()
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'materials_oxide_test.db'}?mode=ro", uri=True)
    checkout = {n: export_layer(con, n, nk_csv_dir=checkout_dir) for n in PARITY_MATERIALS}
    assert json.loads(json.dumps(checkout)) == out["layers"]
    assert out["layers"]["Aluminium oxide / sapphire"]["materials_db"]["mp_id"] == "mp-1143"
    assert all(layer["materials_db"]["mp_id_status"] for layer in out["layers"].values())
    import tomllib
    assert out["version"] == tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
