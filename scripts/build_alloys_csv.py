#!/usr/bin/env python3
"""
scripts/build_alloys_csv.py
============================
Builds data/step1_selections_alloys.json, data/alloys.csv and data/alloy_gaps.csv from scripts/alloy_material_list.py with the shared
listed-pages builder (scripts/listed_family.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alloy_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402
from listed_family import build  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "alloys", "alloys", "alloy_gaps",
          formula_null_reason="formula NULL: the page gives no exact composition (a doped crystal / conducting oxide; dopant level in the name); no x-ray / neutron SLD",
          density_null_reason="density/SLD left NULL: no source states the density of this composition (no interpolation between end members is made)",
          source_label="alloy_material_list.py")


if __name__ == "__main__":
    main()
