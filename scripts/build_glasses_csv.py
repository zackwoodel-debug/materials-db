#!/usr/bin/env python3
"""
scripts/build_glasses_csv.py
============================
Builds data/step1_selections_glasses.json, data/glasses.csv and data/glass_gaps.csv from scripts/glass_material_list.py with the
shared listed-pages builder (scripts/listed_family.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glass_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402
from listed_family import build  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "glasses", "glasses", "glass_gaps",
          formula_null_reason="formula NULL: multicomponent glass (no single formula); no x-ray / neutron SLD without a composition",
          density_null_reason="density/SLD left NULL: no density stated by the source (a multicomponent glass has no MP entry)",
          source_label="glass_material_list.py")


if __name__ == "__main__":
    main()
