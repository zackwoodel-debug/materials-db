#!/usr/bin/env python3
"""
scripts/build_liquid_crystals_csv.py
====================================
Builds data/step1_selections_liquid_crystals.json, data/liquid_crystals.csv and data/liquid_crystal_gaps.csv from
scripts/liquid_crystal_material_list.py with the shared listed-pages builder (scripts/listed_family.py). 5CB and 5PCH get their
identity from PubChem (network); the mixtures have no formula.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liquid_crystal_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402
from listed_family import build  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "liquid_crystals", "liquid_crystals", "liquid_crystal_gaps",
          formula_null_reason="formula NULL: commercial liquid-crystal mixture (no single formula); no x-ray / neutron SLD without a composition",
          density_null_reason="density/SLD left NULL: no density stated by the source",
          source_label="liquid_crystal_material_list.py")


if __name__ == "__main__":
    main()
