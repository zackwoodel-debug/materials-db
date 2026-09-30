"""Import every module of the INSTALLED materials_db wheel, with no help from the checkout (run with `python -I` from a directory
outside the repository; no PYTHONPATH). Known Phase 2 defects are listed below and checked STRICTLY: an unexpected failure fails, and a
known defect that stops reproducing also fails, so this list is updated when Phase 2 fixes it. Dependencies installing is not the
same as the wheel's features working; the known defects are the gap.

    python -I .github/ci/wheel_smoke.py <expected software version>
"""
import importlib
import importlib.util
import io
import contextlib
import pathlib
import sys

# module -> text its import error must contain. Source: Phase 0.2 (clean-venv wheel install, 2026-09-29).
KNOWN_IMPORT_DEFECTS = {
    "materials_db.export.modalfit": "No module named 'oxide_material_list'",           # sys.path.insert into scripts/
    "materials_db.launcher.catalog": "No module named 'oxide_material_list'",          # via export.modalfit
    "materials_db.launcher.library_export": "No module named 'oxide_material_list'",   # via export.modalfit
    "materials_db.launcher.modalfit_bridge": "No module named 'verify_modalfit_pin'",  # sys.path.insert into scripts/
    "materials_db.launch": "SystemExit",       # expects data/materials.db next to the package (checkout-only)
    "materials_db.verify": "SystemExit",       # likewise
    "materials_db.verify_all": "No module named 'src'",                                 # imports the checkout's src.* packages
}
# modules that need an optional extra: without it the import must fail on exactly that extra, with it the import must work
OPTIONAL_EXTRA_MODULES = {"materials_db.access.mcp_server": "mcp"}
# files the checkout has but the wheel does not ship (package data not declared)
KNOWN_MISSING_PACKAGE_DATA = ["core/schema.sql", "core/seed_manual.sql", "chat/ui.html"]
# generic top-level packages the wheel installs next to materials_db (src/db, src/ml, src/pipeline)
KNOWN_LEAKED_TOP_LEVEL = ["db", "ml", "pipeline"]


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
        known = KNOWN_IMPORT_DEFECTS.get(name)
        extra = OPTIONAL_EXTRA_MODULES.get(name)
        if extra and importlib.util.find_spec(extra) is None:
            known = f"No module named '{extra}'"  # the extra is not installed in this job
        if error is None and known:
            problems.append(f"{name} now imports: remove it from KNOWN_IMPORT_DEFECTS")  # (an extra's module cannot import without it)
        elif error is not None and not known:
            problems.append(f"{name}: {error}")
        elif error is not None and known not in error:
            problems.append(f"{name}: expected '{known}', got {error}")
        ok += error is None
    for rel in KNOWN_MISSING_PACKAGE_DATA:
        if (pkg / rel).exists():
            problems.append(f"{rel} is now shipped: remove it from KNOWN_MISSING_PACKAGE_DATA")
    for top in KNOWN_LEAKED_TOP_LEVEL:
        if importlib.util.find_spec(top) is None:
            problems.append(f"top-level '{top}' is no longer installed: remove it from KNOWN_LEAKED_TOP_LEVEL")

    print(f"wheel smoke: {len(modules)} modules, {ok} import, {len(KNOWN_IMPORT_DEFECTS)} known defects reproduced as recorded; "
          f"missing package data {KNOWN_MISSING_PACKAGE_DATA}; leaked top-level packages {KNOWN_LEAKED_TOP_LEVEL}")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
