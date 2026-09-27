#!/usr/bin/env python3
"""
scripts/build_gases_csv.py
==========================
Builds data/step1_selections_gases.json, data/gases.csv and data/gas_gaps.csv from scripts/gas_material_list.py with the shared
listed-pages builder (scripts/listed_family.py). Gases with a formula get their identity from PubChem (network); air has none.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gas_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402
from listed_family import build  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "gases", "gases", "gas_gaps",
          formula_null_reason="formula NULL: a gas mixture (dry air); no x-ray / neutron SLD without a composition",
          density_null_reason="density/SLD left NULL: a gas density depends on temperature and pressure and no source states one",
          source_label="gas_material_list.py")


if __name__ == "__main__":
    main()
