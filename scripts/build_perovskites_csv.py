#!/usr/bin/env python3
"""
scripts/build_perovskites_csv.py
=================================
Builds data/step1_selections_perovskites.json, data/perovskites.csv and data/perovskite_gaps.csv from scripts/perovskite_material_list.py with the shared
listed-pages builder (scripts/listed_family.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perovskite_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402
from listed_family import build  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "perovskites", "perovskites", "perovskite_gaps",
          formula_null_reason="formula NULL: no single composition stated",
          density_null_reason="density/SLD left NULL: no density stated by the optical sources",
          source_label="perovskite_material_list.py")


if __name__ == "__main__":
    main()
