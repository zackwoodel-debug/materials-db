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

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.export.modalfit import (  # noqa: E402
    _classify_material_type, _density_confidence, _lookup_mp_id, _polymorph_prefix,
    export_layer, export_stack,
)
from materials_db.pipeline.process_condition import (  # noqa: E402
    DENSITY_BULK_APPROXIMATION, DENSITY_VERIFIED,
)

_DB_PATH = ROOT / "data" / "materials_oxide_test.db"


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


class TestLookupMpIdCoversEveryBatch:
    """Regression test for the bug found during the batch-2 audit:
    _lookup_mp_id only ever read data/oxides_50.csv, so every batch-2
    material's mp_id silently came back None (a wrong answer, no error --
    the same failure shape as batch 1's polymorph fallback). This test
    would have caught it: it requires a real mp_id for a material from
    EACH batch's CSV, not just the oxide batch's."""

    @pytest.mark.skipif(not (ROOT / "data" / "oxides_50.csv").exists(), reason="data/oxides_50.csv not built")
    def test_oxide_batch_material_resolves(self):
        assert _lookup_mp_id("TiO2") is not None

    @pytest.mark.skipif(not (ROOT / "data" / "batch2_31.csv").exists(), reason="data/batch2_31.csv not built")
    def test_batch2_material_resolves(self):
        """This is the exact case that silently returned None: a formula
        that only exists in batch2_31.csv, not oxides_50.csv. Also
        regression coverage for _lookup_mp_id's glob-based lookup surviving
        a CSV rename (batch2_28.csv -> batch2_31.csv broke this test once
        already, via the OLD hardcoded-filename-list implementation)."""
        mp_id = _lookup_mp_id("ZnS")
        assert mp_id is not None, (
            "_lookup_mp_id returned None for a batch-2-only formula -- "
            "regression of the oxides_50.csv-only lookup bug."
        )
        assert mp_id.startswith("mp-")

    def test_unknown_formula_returns_none_not_an_error(self):
        assert _lookup_mp_id("NotARealFormulaXYZ") is None

    def test_lookup_is_filename_agnostic(self, tmp_path, monkeypatch):
        """The real regression: a hardcoded filename list broke this
        function twice (once when batch2_28.csv was first written, again
        when it was renamed to batch2_31.csv) -- prove the CURRENT
        (glob-based) implementation doesn't care what a CSV is named at
        all, so a future rename can't reintroduce the same bug shape."""
        import materials_db.export.modalfit as modalfit_mod
        import pandas as pd

        monkeypatch.setattr(modalfit_mod, "_ROOT", tmp_path)
        (tmp_path / "data").mkdir()
        pd.DataFrame([{"formula": "Zzzz9", "mp_id": "mp-999999", "name": "Fake"}]).to_csv(
            tmp_path / "data" / "whatever_this_file_is_called_2027.csv", index=False
        )
        assert modalfit_mod._lookup_mp_id("Zzzz9") == "mp-999999"


class TestClassifyMaterialType:
    """Regression test for the second bug found during the same audit:
    export_layer() hardcoded material_type="oxide" for every layer
    regardless of formula, silently mislabeling every batch-2 fluoride/
    nitride/sulfide layer. material_type must vary by formula."""

    def test_oxide(self):
        assert _classify_material_type("TiO2") == "oxide"
        assert _classify_material_type("LuAl3(BO3)4") == "oxide"  # borate: O present -> oxide

    def test_fluoride(self):
        assert _classify_material_type("CaF2") == "fluoride"
        assert _classify_material_type("LiCaAlF6") == "fluoride"

    def test_nitride(self):
        assert _classify_material_type("GaN") == "nitride"
        assert _classify_material_type("BN") == "nitride"

    def test_sulfide(self):
        assert _classify_material_type("ZnS") == "sulfide"
        assert _classify_material_type("As2S3") == "sulfide"

    def test_not_all_oxide(self):
        """The literal shape of the bug: every material_type must NOT
        collapse to the same value."""
        types = {_classify_material_type(f) for f in ("TiO2", "CaF2", "GaN", "ZnS")}
        assert types == {"oxide", "fluoride", "nitride", "sulfide"}

    def test_unrecognized_anion_returns_unknown_not_a_guess(self):
        assert _classify_material_type("Au") == "unknown"


class TestExportStackLabelDisambiguation:
    """Regression tests for the repeated-material label collision:
    export_stack() used to give two layers of the same material (a
    Bragg mirror / repeated-unit multilayer -- a real sample type) the
    IDENTICAL label, silently overwriting the first layer's sidecar n,k
    CSV with the second's, and producing two physics.extract_params()
    ParamSpecs with the same key (confirmed: a SiO2/Ta2O5/SiO2 stack gave
    two "SiO2_amorphous:thick" entries), so FitEngine could not move the
    two physically distinct layers independently."""

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_repeated_material_gets_disambiguated_labels(self, tmp_path):
        out = export_stack(
            str(_DB_PATH),
            layers=[
                dict(material="SiO2", dataset_label="amorphous", thickness_a=50.0, roughness_a=3.0),
                dict(material="Ta2O5", thickness_a=30.0, roughness_a=3.0),
                dict(material="SiO2", dataset_label="amorphous", thickness_a=15.0, roughness_a=3.0),
            ],
            substrate="silicon", substrate_roughness_a=3.0,
            stack_id="collision_regression_test", out_dir=tmp_path,
        )
        film_labels = [e["label"] for e in out["stack"] if e.get("role") not in ("ambient", "substrate")]
        assert len(film_labels) == len(set(film_labels)), f"duplicate labels: {film_labels}"
        assert film_labels[0] == "SiO2_amorphous"
        assert film_labels[2] == "SiO2_amorphous#2"

        # Both sidecar files must exist and be distinct -- the second
        # write must not have overwritten the first.
        nk_files = {e["label"]: e["optical"]["params"]["file"]
                    for e in out["stack"] if e.get("role") not in ("ambient", "substrate")}
        assert len(set(nk_files.values())) == 3
        for fname in nk_files.values():
            assert (tmp_path / fname).exists()

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_no_duplicate_fittable_param_keys(self, tmp_path):
        out = export_stack(
            str(_DB_PATH),
            layers=[
                dict(material="SiO2", dataset_label="amorphous", thickness_a=50.0, roughness_a=3.0),
                dict(material="Ta2O5", thickness_a=30.0, roughness_a=3.0),
                dict(material="SiO2", dataset_label="amorphous", thickness_a=15.0, roughness_a=3.0),
            ],
            substrate="silicon", substrate_roughness_a=3.0,
            stack_id="collision_regression_test_2", out_dir=tmp_path,
        )
        # This is what actually broke: physics.extract_params() building a
        # duplicate ParamSpec key for the two SiO2 layers. Reproduce the
        # exact key-construction rule here without depending on the
        # ModalFit clone (not a repo dependency) -- one ParamSpec key per
        # (label, quantity) pair.
        keys = [f"{e['label']}:thick" for e in out["stack"] if e.get("role") not in ("ambient", "substrate")]
        assert len(keys) == len(set(keys)), f"duplicate fittable-parameter keys: {keys}"

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_explicit_duplicate_labels_also_disambiguated(self, tmp_path):
        """Two DIFFERENT materials given the SAME explicit label by the
        caller must also be disambiguated -- the collision isn't only a
        same-formula concern."""
        out = export_stack(
            str(_DB_PATH),
            layers=[
                dict(material="SiO2", dataset_label="amorphous", thickness_a=50.0,
                     roughness_a=3.0, label="cap"),
                dict(material="Ta2O5", thickness_a=30.0, roughness_a=3.0, label="cap"),
            ],
            substrate="silicon", substrate_roughness_a=3.0,
            stack_id="collision_regression_test_3", out_dir=tmp_path,
        )
        film_labels = [e["label"] for e in out["stack"] if e.get("role") not in ("ambient", "substrate")]
        assert film_labels == ["cap", "cap#2"]


class TestDensityConfidenceCarriesThroughExport:
    """A layer whose density is a bulk_elemental_approximation must be
    visibly flagged in the exported JSON itself -- at fit time, not just
    in the DB -- so a caller (or a GUI) can tell an approximated SLD from
    a trusted one without a separate DB query."""

    def test_density_confidence_helper(self):
        assert _density_confidence("density_MP_DFT") == DENSITY_VERIFIED
        assert _density_confidence("amorphous | density_literature") == DENSITY_VERIFIED
        assert _density_confidence("density_bulk_elemental_approximation") == DENSITY_BULK_APPROXIMATION
        assert _density_confidence(None) == DENSITY_VERIFIED

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_verified_material_gets_pinned_bounds_in_json(self, tmp_path):
        layer = export_layer(str(_DB_PATH), "TiO2", nk_csv_dir=tmp_path)
        assert layer["molecular"]["density_confidence"] == DENSITY_VERIFIED
        assert layer["materials_db"]["density_confidence"] == DENSITY_VERIFIED
        b = layer["molecular"]["density_bounds"]
        assert b["min"] == b["max"] == layer["molecular"]["density_g_cm3"]
