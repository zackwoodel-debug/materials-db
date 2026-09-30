"""README's Layout section stays true: every path it names exists, and every materials_db subpackage is listed."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
BLOCK = README[README.index("### Layout"):README.index("### Quickstart")]
TREE = BLOCK[BLOCK.index("```") + 3:BLOCK.rindex("```")]


def _listed_paths():
    """Rebuild each tree entry's path from its indentation (4 characters per level under the root)."""
    paths, stack = [], []
    for line in TREE.splitlines()[1:]:
        m = re.match(r"^([│ ]*)[├└]── (\S+)", line)
        if not m:
            continue
        depth = len(m.group(1)) // 4
        stack = stack[:depth] + [m.group(2).rstrip("/")]
        paths.append("/".join(stack))
    return paths


def test_every_listed_path_exists():
    paths = _listed_paths()
    assert len(paths) > 15
    missing = [p for p in paths if not (ROOT / p).exists()]
    assert missing == []


def test_every_subpackage_is_listed():
    pkgs = sorted(p.name for p in (ROOT / "src" / "materials_db").iterdir() if p.is_dir() and not p.name.startswith("__"))
    listed = {p.split("/")[-1] for p in _listed_paths() if p.startswith("src/materials_db/")}
    assert [p for p in pkgs if p not in listed] == []
