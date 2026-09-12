#!/usr/bin/env python3
"""
export/modalfit.py
===================
ModalFit dataset_label parsing: given a physical_properties or
optical_dispersion dataset_label, identify which polymorph (if any) it
belongs to.

dataset_label shapes (see scripts/load_oxides_db.py / build_checkpoint1_report.py):
  with polymorph:    "rutile | xray_sld_real | periodictable_CuKalpha"
                      "rutile | Devore1951 | o-ray"
  without polymorph: "xray_sld_real | periodictable_CuKalpha"   (physical_properties)
                      "density_MP_DFT"                          (physical_properties, no " | " at all)
                      "Devore1951 | o-ray"                      (optical_dispersion)
                      "Devore1951"                              (optical_dispersion, isotropic, no axis)

A naive split(" | ")[0] cannot tell these apart -- for a polymorph-less
material it would treat each quantity type (density/xray_real/xray_imag/
neutron_real/neutron_imag) or each paper as its own distinct "polymorph".
This detects the absence of a polymorph segment instead, by recognizing
what the first segment looks like when one isn't there: a
physical_properties quantity marker, or an optical "AuthorYYYY" source
label (never a real polymorph name in this dataset -- polymorph names here
are words like "rutile"/"wurtzite"/"K2NiF4-type", never Letters+4-digits).
"""

import re
from typing import Optional

_QUANTITY_MARKERS = ("density_", "xray_sld_real", "xray_sld_imag",
                     "neutron_sld_real", "neutron_sld_imag")
_SOURCE_LABEL_RE = re.compile(r"^[A-Za-z]+\d{4}$")


def _polymorph_prefix(dataset_label: str) -> Optional[str]:
    first = dataset_label.split(" | ", 1)[0]
    if any(first.startswith(m) for m in _QUANTITY_MARKERS) or _SOURCE_LABEL_RE.match(first):
        return None
    return first
