#!/usr/bin/env python3
"""Write data/step1_selections_batch3b.json (the selections the shared family loader reads) from the curated batch-3b entries of
scripts/pure_element_material_list.py (idx >= 260: Diamond, Graphite, Tin, Boron). Keyed by material NAME, because Diamond and
Graphite share the formula "C". Each axis carries the exact dataset_label the original batch-3b loader built:
label_join(polymorph, source_label, axis). tests/test_batch3b_loader.py fails if the file is stale.

    python3 scripts/build_batch3b_selections.py
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_family_db import label_join  # noqa: E402
from pure_element_material_list import MATERIALS_PURE_ELEMENTS  # noqa: E402

OUT = _ROOT / "data" / "step1_selections_batch3b.json"


def selections():
    out = {}
    for m in (m for m in MATERIALS_PURE_ELEMENTS if m["idx"] >= 260):
        out[m["name"]] = dict(
            name=m["name"], polymorph=m["polymorph"], effective_polymorph=m["polymorph"],
            axes=[dict(page=Path(a["data_path"]).stem, axis=a["axis"], data_path=a["data_path"],
                       dataset_label=label_join(m["polymorph"], a["source_label"], a["axis"])) for a in m["ri_axes"]])
    return out


if __name__ == "__main__":
    sel = selections()
    OUT.write_text(json.dumps(sel, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(_ROOT)}: {len(sel)} materials, {sum(len(v['axes']) for v in sel.values())} axes")
