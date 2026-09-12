"""Tests for src/materials_db/export/modalfit.py.

Started with a regression test for Bug 1 found while running the bulk
50-material export: _polymorph_prefix() used to take dataset_label.split(
" | ")[0] as "the polymorph", which is wrong for materials with no named
polymorph -- their physical_properties rows have no polymorph segment at
all (e.g. "density_MP_DFT", "xray_sld_real | periodictable_CuKalpha"), so
each of the 5 quantity types was treated as its own distinct "polymorph".
More tests (round-trip, dataset_label disambiguation, missing-density
error, SLD-agreement tolerance) are added in Step 4 per MODALFIT_INTEGRATION.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.export.modalfit import _polymorph_prefix  # noqa: E402


class TestPolymorphPrefix:
    # --- with a real polymorph segment -------------------------------------
    def test_physical_properties_with_polymorph(self):
        assert _polymorph_prefix("rutile | xray_sld_real | periodictable_CuKalpha") == "rutile"
        assert _polymorph_prefix("rutile | density_MP_DFT") == "rutile"
        assert _polymorph_prefix("K2NiF4-type | density_MP_DFT") == "K2NiF4-type"

    def test_optical_dispersion_with_polymorph(self):
        assert _polymorph_prefix("rutile | Devore1951 | o-ray") == "rutile"
        assert _polymorph_prefix("alpha-BiBO | Umemura2007 | alpha-axis") == "alpha-BiBO"

    # --- no polymorph segment (the bug) --------------------------------------
    def test_physical_properties_without_polymorph_no_pipe(self):
        """'density_MP_DFT' alone (no ' | ' at all) must not be read as a
        polymorph named 'density_MP_DFT'."""
        assert _polymorph_prefix("density_MP_DFT") is None
        assert _polymorph_prefix("density_experimental lattice params") is None
        assert _polymorph_prefix("density_literature") is None

    def test_physical_properties_without_polymorph_with_pipe(self):
        """'xray_sld_real | periodictable_CuKalpha' has a pipe, but the first
        segment is a quantity marker, not a polymorph -- must not be read as
        a distinct 'xray_sld_real' polymorph (this was the actual bug: each
        of density/xray_real/xray_imag/neutron_real/neutron_imag looked like
        a different polymorph for a material with none named)."""
        assert _polymorph_prefix("xray_sld_real | periodictable_CuKalpha") is None
        assert _polymorph_prefix("xray_sld_imag | periodictable_CuKalpha") is None
        assert _polymorph_prefix("neutron_sld_real | periodictable_thermal") is None
        assert _polymorph_prefix("neutron_sld_imag | periodictable_thermal") is None

    def test_optical_dispersion_without_polymorph(self):
        """An 'AuthorYYYY[ | axis]' label with no polymorph prefix must not
        be read as a polymorph named after the paper."""
        assert _polymorph_prefix("Devore1951 | o-ray") is None
        assert _polymorph_prefix("Devore1951") is None  # isotropic, single block, no axis
        assert _polymorph_prefix("Chernova2017") is None

    def test_all_five_quantity_rows_group_together_when_polymorph_absent(self):
        """This is the exact bug scenario: a material with no named
        polymorph has 5 physical_properties rows (density + 4 SLD parts);
        all 5 must resolve to the SAME (None) group, not 5 different ones."""
        labels = [
            "density_MP_DFT",
            "xray_sld_real | periodictable_CuKalpha",
            "xray_sld_imag | periodictable_CuKalpha",
            "neutron_sld_real | periodictable_thermal",
            "neutron_sld_imag | periodictable_thermal",
        ]
        prefixes = {_polymorph_prefix(l) for l in labels}
        assert prefixes == {None}, f"expected all 5 rows to group as one (None) polymorph, got {prefixes}"
