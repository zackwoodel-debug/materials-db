"""Fail unless every skipped test in a pytest JUnit report was skipped for a known, documented reason, and nothing failed.

The fast CI job has no release packages (release/ is gitignored and not rebuilt there), so the tests that read a built release skip;
the mcp extra is not installed there. Any other skip reason is treated as a regression.

    python .github/ci/check_skips.py report.xml
"""
import re
import sys
import xml.etree.ElementTree as ET

ALLOWED = [
    r"^no release built locally$",                                   # tests over a built release (test_access, test_datasette, ...)
    r"^materials-db-v[\d.]+ not built locally$",                     # ML sets checked against the release they came from
    r"^v[\d.]+ not built locally$",                                  # registry test against an old release
    r"^could not import 'mcp': No module named 'mcp'$",              # mcp extra (exercised in the release-artifacts job)
]


def main(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    skipped, bad, failed = [], [], []
    for c in cases:
        name = f"{c.get('classname')}::{c.get('name')}"
        if c.find("failure") is not None or c.find("error") is not None:
            failed.append(name)
        s = c.find("skipped")
        if s is not None:
            reason = (s.get("message") or "").removeprefix("Skipped: ").strip()
            skipped.append(reason)
            if not any(re.match(p, reason) for p in ALLOWED):
                bad.append(f"{name}: {reason!r}")
    print(f"{len(cases)} test cases: {len(cases) - len(skipped) - len(failed)} passed, {len(skipped)} skipped, {len(failed)} failed/errored")
    for b in bad:
        print("UNEXPECTED SKIP:", b)
    for f in failed:
        print("FAILED:", f)
    return 1 if bad or failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
