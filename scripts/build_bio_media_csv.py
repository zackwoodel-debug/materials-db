#!/usr/bin/env python3
"""
scripts/build_bio_media_csv.py
==============================
Builds data/step1_selections_bio_media.json, data/bio_media.csv and data/bio_media_gaps.csv from
scripts/bio_media_material_list.py with the shared listed-pages builder (scripts/listed_family.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bio_media_material_list import EXCLUDED_PAGES, MATERIALS, OUT_OF_FAMILY  # noqa: E402
from listed_family import build  # noqa: E402


def main():
    build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, "bio_media", "bio_media", "bio_media_gaps",
          formula_null_reason="formula NULL: biological fluid, tissue or buffer (a mixture); no x-ray / neutron SLD without a composition",
          density_null_reason="density/SLD left NULL: no density stated by the source",
          source_label="bio_media_material_list.py")


if __name__ == "__main__":
    main()
