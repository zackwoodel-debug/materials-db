"""Tests for src/materials_db/launcher/catalog.py: the shared material
search/browse interface for both film-layer and substrate selection.
Density confidence must be visible on every selectable row; named
exclusions must appear (so a search doesn't look broken) but marked
unselectable with the real reason.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.launcher.catalog import describe_row, list_materials  # noqa: E402
from materials_db.pipeline.process_condition import (  # noqa: E402
    DENSITY_BULK_APPROXIMATION, DENSITY_VERIFIED,
)

_DB_PATH = ROOT / "data" / "materials_oxide_test.db"
pytestmark = pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")


class TestListMaterials:
    def test_returns_all_135_selectable_rows_plus_2_exclusions(self):
        rows = list_materials(str(_DB_PATH))
        selectable = [r for r in rows if r["selectable"]]
        excluded = [r for r in rows if not r["selectable"]]
        # 133 exportable materials (each with exactly one polymorph here),
        # 2 named exclusions (GdF3, LuAl3(BO3)4) -- see
        # scripts/export_all_materials_modalfit.py's own assertion.
        assert len(selectable) == 133
        assert len(excluded) == 2
        assert {r["formula"] for r in excluded} == {"GdF3", "LuAl3(BO3)4"}

    def test_named_exclusion_carries_its_real_reason(self):
        rows = list_materials(str(_DB_PATH), query="Gadolinium")
        gdf3 = [r for r in rows if r["formula"] == "GdF3"]
        assert len(gdf3) == 1
        assert gdf3[0]["selectable"] is False
        assert "named exclusion" in gdf3[0]["exclusion_reason"] or "no density" in gdf3[0]["exclusion_reason"]

    def test_search_is_case_insensitive_on_name_or_formula(self):
        by_name = list_materials(str(_DB_PATH), query="sapphire")
        by_formula = list_materials(str(_DB_PATH), query="al2o3")
        assert any(r["formula"] == "Al2O3" for r in by_name)
        assert any(r["formula"] == "Al2O3" for r in by_formula)

    def test_bulk_approximation_materials_are_flagged(self):
        """Gold has no measured film density anywhere in its corpus --
        must show bulk_approximation, not a silently-trusted density."""
        rows = list_materials(str(_DB_PATH), query="Gold")
        gold = [r for r in rows if r["formula"] == "Au"]
        assert len(gold) == 1
        assert gold[0]["density_confidence"] == DENSITY_BULK_APPROXIMATION

    def test_verified_material_is_flagged_verified(self):
        rows = list_materials(str(_DB_PATH), query="Sapphire")
        sapphire = [r for r in rows if r["formula"] == "Al2O3"]
        assert sapphire[0]["density_confidence"] == DENSITY_VERIFIED

    def test_diamond_and_graphite_are_distinct_rows_despite_shared_formula(self):
        """The same material-picker used for the launcher must not
        collapse Diamond and Graphite into one row just because they
        share formula "C" -- _find_material()'s ambiguity guard exists
        because they're genuinely distinct materials."""
        rows = list_materials(str(_DB_PATH), query="")
        carbon_rows = [r for r in rows if r["formula"] == "C"]
        names = {r["name"] for r in carbon_rows}
        assert {"Diamond", "Graphite"} <= names


class TestDescribeRow:
    def test_excluded_row_shows_reason(self):
        rows = list_materials(str(_DB_PATH), query="Gadolinium")
        gdf3 = [r for r in rows if r["formula"] == "GdF3"][0]
        text = describe_row(gdf3)
        assert "EXCLUDED" in text

    def test_bulk_approximation_row_is_visibly_flagged(self):
        rows = list_materials(str(_DB_PATH), query="Gold")
        gold = [r for r in rows if r["formula"] == "Au"][0]
        text = describe_row(gold)
        assert "BULK_APPROXIMATION" in text
