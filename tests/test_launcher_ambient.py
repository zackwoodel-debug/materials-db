"""Tests for src/materials_db/launcher/ambient.py.

Pure logic, no DB or Tkinter needed -- these presets exist precisely
because materials_oxide_test.db has no liquid/gas materials to drive an
ambient picker from (see the module's own docstring for what was checked
against ModalFit's schema before this was written).
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.launcher.ambient import (  # noqa: E402
    AMBIENT_PRESETS, build_ambient_entry, describe_ambient_presets,
)


class TestAmbientPresetTable:
    def test_four_presets_exist(self):
        assert set(AMBIENT_PRESETS) == {"air", "vacuum", "d2o", "h2o"}

    def test_air_and_vacuum_are_both_zero_sld(self):
        for name in ("air", "vacuum"):
            p = AMBIENT_PRESETS[name]
            assert p["xray_sld_real"] == 0.0
            assert p["neutron_sld_real"] == 0.0
            assert p["molecular"] is None

    def test_water_presets_have_real_neutron_contrast(self):
        """The whole point of a D2O/H2O ambient: real, opposite-signed
        neutron contrast (the standard reflectometry contrast-variation
        technique) -- not a knob that silently does nothing."""
        d2o = AMBIENT_PRESETS["d2o"]
        h2o = AMBIENT_PRESETS["h2o"]
        assert d2o["neutron_sld_real"] > 6.0
        assert h2o["neutron_sld_real"] < 0.0
        # x-ray can't distinguish the isotopes -- both should be close
        assert abs(d2o["xray_sld_real"] - h2o["xray_sld_real"]) < 0.1

    def test_water_presets_carry_molecular_formula_and_density(self):
        for name in ("d2o", "h2o"):
            mol = AMBIENT_PRESETS[name]["molecular"]
            assert mol["formula"] in ("D2O", "H2O")
            assert mol["density_g_cm3"] > 0.9


class TestBuildAmbientEntry:
    def test_air_entry_shape(self):
        entry = build_ambient_entry("air")
        assert entry["role"] == "ambient"
        assert entry["xray"]["sld_real"]["value"] == 0.0
        assert entry["optical"]["params"]["n"] == 1.0
        assert "molecular" not in entry
        assert "NOT a DB material" in entry["materials_db"]["note"]

    def test_d2o_entry_includes_molecular_block(self):
        entry = build_ambient_entry("D2O")  # case-insensitive
        assert entry["molecular"] == {"formula": "D2O", "density_g_cm3": 1.107}
        assert entry["neutron"]["sld_real"]["value"] > 6.0
        assert entry["scattering"]["sld_real"]["value"] == entry["xray"]["sld_real"]["value"]

    def test_unknown_preset_raises_with_real_options_listed(self):
        with pytest.raises(ValueError, match="vacuum"):
            build_ambient_entry("helium")


class TestDescribeAmbientPresets:
    def test_returns_one_row_per_preset(self):
        rows = describe_ambient_presets()
        assert len(rows) == 4
        names = {r[0] for r in rows}
        assert names == {"air", "vacuum", "d2o", "h2o"}
