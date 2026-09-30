"""modalfit_db_export/citations.py and modalfit_export.py carry vendored copies of the resolved optical-source citation table
(so they work outside this repository). They must stay identical to the package's table, materials_db.export.citations; this
test fails the moment one drifts. The copies are read as data (their assignment is evaluated alone), not imported."""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.export.citations import RESOLVED_OPTICAL_SOURCE_CITATION  # noqa: E402


def _vendored_table(path):
    tree = ast.parse(path.read_text())
    node = next(n.value for n in ast.walk(tree)
                if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "RESOLVED_OPTICAL_SOURCE_CITATION")
    return eval(compile(ast.Expression(node), str(path), "eval"), {"__builtins__": {}, "dict": dict})


@pytest.mark.parametrize("rel", ["modalfit_db_export/citations.py", "modalfit_export.py"])
def test_vendored_copy_equals_the_package_table(rel):
    assert _vendored_table(ROOT / rel) == RESOLVED_OPTICAL_SOURCE_CITATION
