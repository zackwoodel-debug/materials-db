#!/usr/bin/env python3
"""
scripts/build_optical_media_csv.py
==================================
Builds data/step1_selections_optical_media.json, data/optical_media.csv and data/optical_media_gaps.csv from
scripts/optical_media_material_list.py with the shared listed-pages builder (scripts/listed_family.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from listed_family import build  # noqa: E402
from optical_media_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "optical_media", "optical_media", "optical_media_gaps",
          formula_null_reason="formula NULL: proprietary commercial formulation (no single formula); no x-ray / neutron SLD without a composition",
          density_null_reason="density/SLD left NULL: no density stated by the source (a commercial formulation has no MP entry)",
          source_label="optical_media_material_list.py")


if __name__ == "__main__":
    main()
