"""Import every module of the INSTALLED materials_db wheel, with no help from the checkout (run with `python -I` from a directory
outside the repository; no PYTHONPATH). Every module must import except the documented checkout-only ones and modules whose
optional extra is absent, each of which must fail for exactly that recorded reason (checked STRICTLY both ways). Required package
data must be present and no generic top-level package may be installed.

    python -I .github/ci/wheel_smoke.py <expected software version>
"""
import importlib
import importlib.util
import io
import contextlib
import pathlib
import sys

# Modules that need a materials-db checkout by design (documented in docs/installation.md): module -> text its import error must
# contain when installed from a wheel. verify_all.py is the checkout's self-test harness and imports the legacy src.db /
# src.pipeline packages, which are deliberately not installed.
CHECKOUT_ONLY_MODULES = {
    "materials_db.verify_all": "No module named 'src'",
}
# Phase 2 fixed every recorded import defect; a new failure outside the two lists here is a regression.
KNOWN_IMPORT_DEFECTS = {}
# modules that need an optional extra: without it the import must fail on exactly that extra, with it the import must work
OPTIONAL_EXTRA_MODULES = {
    "materials_db.access.mcp_server": "mcp",
    "materials_db.access.http": "fastapi",
    "materials_db.api.server": "fastapi",
    "materials_db.launch": "uvicorn",
}
# package data the installed code reads; it must be in the wheel
REQUIRED_PACKAGE_DATA = ["core/schema.sql", "core/seed_manual.sql", "chat/ui.html", "export/mp_ids.json"]
# generic top-level names the wheel must NOT install (src/db, src/ml, src/pipeline are checkout-only legacy code)
FORBIDDEN_TOP_LEVEL = ["db", "ml", "pipeline", "src"]


def main(expected_version):
    problems = []
    import materials_db
    pkg = pathlib.Path(materials_db.__file__).parent
    if "site-packages" not in str(pkg):
        problems.append(f"materials_db imported from {pkg}, not from an installed wheel")
    if any((pathlib.Path(p) / "pyproject.toml").is_file() and (pathlib.Path(p) / "src" / "materials_db").is_dir() for p in sys.path if p):
        problems.append("a materials-db checkout is on sys.path")
    if materials_db.__version__ != expected_version:
        problems.append(f"__version__ {materials_db.__version__} != {expected_version}")

    modules = sorted({"materials_db." + ".".join(p.relative_to(pkg).with_suffix("").parts).removesuffix(".__init__")
                      for p in pkg.rglob("*.py")})
    ok = 0
    for name in modules:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                importlib.import_module(name)
            error = None
        except BaseException as exc:  # noqa: BLE001 -- SystemExit is one of the recorded defects
            error = f"{type(exc).__name__}: {exc}"
        known = KNOWN_IMPORT_DEFECTS.get(name) or CHECKOUT_ONLY_MODULES.get(name)
        extra = OPTIONAL_EXTRA_MODULES.get(name)
        if extra and importlib.util.find_spec(extra) is None:
            known = f"No module named '{extra}'"  # the extra is not installed in this job
        if error is None and known:
            problems.append(f"{name} now imports: remove it from its list")
        elif error is not None and not known:
            problems.append(f"{name}: {error}")
        elif error is not None and known not in error:
            problems.append(f"{name}: expected '{known}', got {error}")
        ok += error is None
    for rel in REQUIRED_PACKAGE_DATA:
        if not (pkg / rel).is_file():
            problems.append(f"package data {rel} is missing from the wheel")
    for top in FORBIDDEN_TOP_LEVEL:
        if importlib.util.find_spec(top) is not None:
            problems.append(f"the environment has a top-level '{top}' package (the wheel must not install it)")

    print(f"wheel smoke: {len(modules)} modules, {ok} import; checkout-only as documented: {sorted(CHECKOUT_ONLY_MODULES)}; "
          f"package data present: {REQUIRED_PACKAGE_DATA}; no top-level {FORBIDDEN_TOP_LEVEL}")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
