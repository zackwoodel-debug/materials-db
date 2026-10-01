#!/usr/bin/env python3
"""Write docs/INVARIANTS.md from materials_db.core.invariants (tests/test_invariants.py fails while it is stale).

    python3 scripts/write_invariants_md.py
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.core.invariants import INVARIANTS  # noqa: E402

OUT = _ROOT / "docs" / "INVARIANTS.md"
GROUPS = {"A": "Provenance", "B": "Physical sanity", "D": "Identity", "L": "Legacy database (data/materials.db)"}


def render():
    lines = ["# Invariants", "",
             "Generated from `src/materials_db/core/invariants.py` by `scripts/write_invariants_md.py`; do not edit by hand.", "",
             "**FAIL** invariants block a release (`scripts/build_release.py` validation); **WARN** invariants are reported (release "
             "`MANIFEST.json` `invariants`, and `materials_db.core.audit` for the legacy database).", ""]
    for g, title in GROUPS.items():
        lines += [f"## {g}. {title}", ""]
        for inv in INVARIANTS:
            if inv.group == g:
                lines += [f"- **{inv.name}** ({inv.severity}, {inv.scope}): {inv.rationale}"]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(_ROOT)} ({len(INVARIANTS)} invariants)")
