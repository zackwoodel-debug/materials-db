#!/usr/bin/env python3
"""Report (never fail, never write) every tracked formula-sampled value that this platform recomputes differently from the
tracked data: the base DB, the base catalog CSVs and every family CSV, as tests/test_formula_sampling.py checks them, but listing
all differences instead of stopping at the first. Used to measure cross_platform_float_reproducibility (TRACKED_OPEN_TASKS);
run by the manual `float-report` CI job on Linux.

    python3 scripts/report_cross_platform_floats.py
"""
import json
import platform
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "src"))

import resample_formula_data as rs  # noqa: E402


def main():
    report = dict(platform=f"{platform.system()} {platform.machine()}", python=platform.python_version(), db=None, csv={}, family={})
    try:
        out = rs.resample_db(rs.DEFAULT_DBS[0], apply=False)
        report["db"] = dict(datasets_to_resample=len(out["datasets"]), already_new=len(out["already_new"]))
    except rs.ResampleError as exc:
        report["db"] = dict(error=str(exc)[:500])
    pages = rs.rf4._catalog_pages()
    for p in rs.DEFAULT_CSVS:
        out = rs.resample_csv(p, apply=False, pages=pages, raise_on_unexplained=False)
        report["csv"][Path(p).name] = dict(updated=len(out["cells_updated"]), unexplained=out["unexplained"], unresolved=out["unresolved"])
    for f, sel in rs.FAMILY_CSVS.items():
        out = rs.refresh_family_csv(_ROOT / "data" / f"{f}.csv", _ROOT / "data" / sel, apply=False, raise_on_unexplained=False)
        report["family"][f] = dict(updated=len(out["cells_updated"]), flags_updated=len(out["flags_updated"]), unexplained=out["unexplained"])
    n_diff = sum(len(v["unexplained"]) for v in report["csv"].values()) + sum(len(v["unexplained"]) for v in report["family"].values())
    report["summary"] = dict(unexplained_values=n_diff, db_ok="error" not in report["db"])
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
