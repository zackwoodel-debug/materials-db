#!/usr/bin/env python3
"""Verify DB integrity and SQL agent correctness. Exit 0 on full pass, 1 on any failure."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DB = str(_ROOT / "data" / "materials.db")

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        print(f"  PASS  {name}")
        _passed += 1
    else:
        _failed += 1
        suffix = f": {detail}" if detail else ""
        print(f"  FAIL  {name}{suffix}")


# ── 1. Audit ──────────────────────────────────────────────────────────────────

from materials_db.core.audit import run_audit

ok = run_audit()
check("run_audit() returns True", ok)

# ── 2. Agent ──────────────────────────────────────────────────────────────────

if ok:
    import os
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OLLAMA"):
        print("\n  SKIP  Agent tests (set ANTHROPIC_API_KEY or OLLAMA=1 to run)")
        total = _passed + _failed
        print(f"\n{total} check(s): {_passed} PASS, {_failed} FAIL, 1 SKIP")
        sys.exit(0 if _failed == 0 else 1)

    from materials_db.core.sql_agent import SQLAgent

    agent  = SQLAgent(_DB)
    result = agent.ask("list all materials", [])

    check(
        "result rows not empty",
        len(result["rows"]) > 0,
        f"rows={result['rows']}",
    )
    check(
        "SQL contains no INSERT",
        "INSERT" not in result["sql"].upper(),
        f"sql={result['sql']}",
    )
    check(
        "confidence is a valid value",
        result["confidence"] in ("exact_match", "approximate", "no_data"),
        f"confidence={result['confidence']}",
    )
    check(
        "answer is a non-empty string",
        isinstance(result["answer"], str) and len(result["answer"]) > 0,
        f"answer={result['answer']!r}",
    )

    print(f"\n  sql        : {result['sql']}")
    print(f"  rows       : {len(result['rows'])} returned")
    print(f"  tables_used: {result['tables_used']}")
    print(f"  confidence : {result['confidence']}")
    print(f"  answer     : {result['answer'][:120]}")

# ── Report ────────────────────────────────────────────────────────────────────

total = _passed + _failed
print(f"\n{total} check(s): {_passed} PASS, {_failed} FAIL")
sys.exit(0 if _failed == 0 else 1)
