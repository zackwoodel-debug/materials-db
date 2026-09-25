"""Tests for modalfit_db_export.

Ported from materials-db's tests/test_modalfit_export.py. The assertions
are unchanged; only the imports and the database-path resolution were
rewired for the drop-in, plus three tests noted inline that exercised
materials-db modules which do not travel with this package.

Point it at a database with MODALFIT_DB, or leave it unset to use a
materials-db checkout's data/materials_oxide_test.db if this package is
still sitting inside one:

    MODALFIT_DB=/path/to/materials_oxide_test.db pytest test_export.py -v

Every DB-backed test skips cleanly when no database is reachable, so a
bare `pytest` in a fresh checkout still runs the pure-logic tests.

Started with a regression test for Bug 1 found while running the bulk
50-material export: _polymorph_prefix() used to take dataset_label.split(
" | ")[0] as "the polymorph", which is wrong for materials with no named
polymorph -- their physical_properties rows have no polymorph segment at
all (e.g. "density_MP_DFT", "xray_sld_real | periodictable_CuKalpha"), so
each of the 5 quantity types was treated as its own distinct "polymorph".
More tests (round-trip, dataset_label disambiguation, missing-density
error, SLD-agreement tolerance) are added in Step 4 per MODALFIT_INTEGRATION.md.
"""

import os
import sys
from pathlib import Path

import pytest

# Import the package as a sibling of this file, so the suite runs from
# inside the package directory without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modalfit_db_export.exporter import (  # noqa: E402
    ExportError, _classify_material_type, _density_confidence, _find_material, _lookup_mp_id,
    _polymorph_prefix, export_layer, export_stack,
)
from modalfit_db_export.density import (  # noqa: E402
    DENSITY_BULK_APPROXIMATION, DENSITY_VERIFIED,
)
from modalfit_db_export.bulk import list_materials  # noqa: E402


def _resolve_db_path() -> Path:
    """MODALFIT_DB if set, else a materials-db checkout's database if this
    package still sits inside one. Returns a non-existent path rather than
    raising when neither applies -- every DB-backed test is guarded by
    skipif(not _DB_PATH.exists()), so a fresh copy of this folder with no
    database anywhere still runs the pure-logic tests."""
    env = os.environ.get("MODALFIT_DB")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "materials_oxide_test.db"
        if candidate.exists():
            return candidate
    return here.parent / "materials_oxide_test.db"


_DB_PATH = _resolve_db_path()
_DB_DIR = _DB_PATH.parent
_NO_DB = f"no database at {_DB_PATH} (set MODALFIT_DB)"


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

    @pytest.mark.skipif(not (_DB_DIR / "oxides_50.csv").exists(), reason="oxides_50.csv not beside the database")
    def test_oxide_batch_material_resolves(self):
        assert _lookup_mp_id("TiO2", _DB_DIR) is not None

    @pytest.mark.skipif(not (_DB_DIR / "batch2_31.csv").exists(), reason="batch2_31.csv not beside the database")
    def test_batch2_material_resolves(self):
        """This is the exact case that silently returned None: a formula
        that only exists in batch2_31.csv, not oxides_50.csv. Also
        regression coverage for _lookup_mp_id's glob-based lookup surviving
        a CSV rename (batch2_28.csv -> batch2_31.csv broke this test once
        already, via the OLD hardcoded-filename-list implementation)."""
        mp_id = _lookup_mp_id("ZnS", _DB_DIR)
        assert mp_id is not None, (
            "_lookup_mp_id returned None for a batch-2-only formula -- "
            "regression of the oxides_50.csv-only lookup bug."
        )
        assert mp_id.startswith("mp-")

    def test_unknown_formula_returns_none_not_an_error(self):
        assert _lookup_mp_id("NotARealFormulaXYZ", _DB_DIR) is None

    def test_no_enrichment_dir_returns_none_not_an_error(self):
        """A drop-in with no enrichment CSVs anywhere: mp_id is
        supplementary provenance, so its absence is None, never a raise."""
        assert _lookup_mp_id("TiO2", None) is None

    def test_lookup_is_filename_agnostic(self, tmp_path, monkeypatch):
        """The real regression: a hardcoded filename list broke this
        function twice (once when batch2_28.csv was first written, again
        when it was renamed to batch2_31.csv) -- prove the CURRENT
        (glob-based) implementation doesn't care what a CSV is named at
        all, so a future rename can't reintroduce the same bug shape."""
        pd = pytest.importorskip("pandas", reason="mp_id enrichment is pandas-only")

        pd.DataFrame([{"formula": "Zzzz9", "mp_id": "mp-999999", "name": "Fake"}]).to_csv(
            tmp_path / "whatever_this_file_is_called_2027.csv", index=False
        )
        assert _lookup_mp_id("Zzzz9", tmp_path) == "mp-999999"


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

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_repeated_material_gets_disambiguated_labels(self, tmp_path):
        out = export_stack(
            str(_DB_PATH),
            layers=[
                dict(material="SiO2", dataset_label="amorphous", thickness_a=50.0, roughness_a=3.0),
                dict(material="Ta2O5", thickness_a=30.0, roughness_a=3.0),
                dict(material="SiO2", dataset_label="amorphous", thickness_a=15.0, roughness_a=3.0),
            ],
            substrate="Silicon", substrate_roughness_a=3.0,
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

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_no_duplicate_fittable_param_keys(self, tmp_path):
        out = export_stack(
            str(_DB_PATH),
            layers=[
                dict(material="SiO2", dataset_label="amorphous", thickness_a=50.0, roughness_a=3.0),
                dict(material="Ta2O5", thickness_a=30.0, roughness_a=3.0),
                dict(material="SiO2", dataset_label="amorphous", thickness_a=15.0, roughness_a=3.0),
            ],
            substrate="Silicon", substrate_roughness_a=3.0,
            stack_id="collision_regression_test_2", out_dir=tmp_path,
        )
        # This is what actually broke: physics.extract_params() building a
        # duplicate ParamSpec key for the two SiO2 layers. Reproduce the
        # exact key-construction rule here without depending on the
        # ModalFit clone (not a repo dependency) -- one ParamSpec key per
        # (label, quantity) pair.
        keys = [f"{e['label']}:thick" for e in out["stack"] if e.get("role") not in ("ambient", "substrate")]
        assert len(keys) == len(set(keys)), f"duplicate fittable-parameter keys: {keys}"

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
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
            substrate="Silicon", substrate_roughness_a=3.0,
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

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_verified_material_gets_pinned_bounds_in_json(self, tmp_path):
        layer = export_layer(str(_DB_PATH), "TiO2", nk_csv_dir=tmp_path)
        assert layer["molecular"]["density_confidence"] == DENSITY_VERIFIED
        assert layer["materials_db"]["density_confidence"] == DENSITY_VERIFIED
        b = layer["molecular"]["density_bounds"]
        assert b["min"] == b["max"] == layer["molecular"]["density_g_cm3"]


class TestFindMaterialFormulaAmbiguity:
    """Regression test for the ambiguity _find_material() must catch, not
    silently resolve: a formula with multiple genuinely distinct
    materials rows (carbon's Diamond and Graphite, batch 3b -- the same
    formula "C" deliberately stored as two separate materials, since
    they're optically nothing alike). Before this check, .fetchone() on
    the formula-fallback query would silently return whichever row
    SQLite happened to return first."""

    def test_unambiguous_formula_still_resolves(self, tmp_path):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT, formula TEXT)")
        conn.execute("INSERT INTO materials (name, formula) VALUES ('Silicon', 'Si')")
        row = _find_material(conn, "Si")
        assert row is not None
        assert row[1] == "Silicon"

    def test_ambiguous_formula_raises(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT, formula TEXT)")
        conn.execute("INSERT INTO materials (name, formula) VALUES ('Diamond', 'C')")
        conn.execute("INSERT INTO materials (name, formula) VALUES ('Graphite', 'C')")
        with pytest.raises(ExportError, match="matches 2 distinct materials"):
            _find_material(conn, "C")

    def test_exact_name_bypasses_the_ambiguity(self):
        """Looking up by the exact name ('Diamond') must still work even
        when the formula alone would be ambiguous -- name is checked
        first and short-circuits before the formula fallback runs."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE materials (material_id INTEGER PRIMARY KEY, name TEXT, formula TEXT)")
        conn.execute("INSERT INTO materials (name, formula) VALUES ('Diamond', 'C')")
        conn.execute("INSERT INTO materials (name, formula) VALUES ('Graphite', 'C')")
        row = _find_material(conn, "Diamond")
        assert row is not None
        assert row[1] == "Diamond"


class TestDbDrivenSubstrate:
    """export_stack()'s substrate used to be a fixed, non-DB-sourced
    Silicon placeholder -- every fit run before the ModalFit launcher used
    a substrate that never came from the database, even though the DB has
    real oxide-growth substrates (sapphire, quartz, MgO) alongside
    Silicon. Substrate is now resolved exactly like a film layer, via
    export_layer(role="substrate")."""

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_default_substrate_is_silicon_and_db_sourced(self, tmp_path):
        out = export_stack(str(_DB_PATH), layers=[], substrate_roughness_a=3.0,
                            out_dir=tmp_path, stack_id="default_substrate_test")
        sub = out["stack"][-1]
        assert sub["role"] == "substrate"
        assert sub["label"] == "Si_diamond cubic"  # formula_polymorph, same default rule export_layer() uses
        assert sub["molecular"]["formula"] == "Si"
        # A DB-sourced substrate must carry the same density_confidence
        # visibility a film layer does -- the old placeholder had none.
        assert "density_confidence" in sub["molecular"]
        assert "density_confidence" in sub["materials_db"]

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_sapphire_substrate_resolves_with_real_db_data(self, tmp_path):
        """Sapphire (Al2O3) is a real, common oxide-growth substrate
        already in the DB -- confirming substrate is genuinely DB-driven,
        not just defaulting correctly."""
        out = export_stack(str(_DB_PATH), layers=[], substrate="Aluminium oxide / sapphire",
                            substrate_roughness_a=3.0, out_dir=tmp_path,
                            stack_id="sapphire_substrate_test")
        sub = out["stack"][-1]
        assert sub["molecular"]["formula"] == "Al2O3"
        assert sub["molecular"]["density_g_cm3"] > 0
        assert sub["xray"]["sld_real"]["value"] > 0
        assert (tmp_path / sub["optical"]["params"]["file"]).exists()

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_unknown_substrate_raises_export_error(self, tmp_path):
        with pytest.raises(ExportError, match="Substrate material .* not found"):
            export_stack(str(_DB_PATH), layers=[], substrate="Unobtainium",
                         out_dir=tmp_path, stack_id="bad_substrate_test")

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_film_layer_colliding_with_substrate_label_is_disambiguated(self, tmp_path):
        """A film layer that happens to resolve to the SAME label as the
        substrate (Silicon-on-Silicon, an unusual but not physically
        meaningless stack) must not collide -- the substrate keeps its
        plain label (there is only one substrate) and the film layer gets
        "#2", the same disambiguation direction as two colliding film
        layers."""
        out = export_stack(str(_DB_PATH), layers=[
            dict(material="Silicon", thickness_a=100.0, roughness_a=2.0),
        ], substrate="Silicon", substrate_roughness_a=3.0, out_dir=tmp_path,
           stack_id="si_on_si_test")
        film = [e for e in out["stack"] if e["role"] == "layer"][0]
        sub = out["stack"][-1]
        assert sub["label"] == "Si_diamond cubic"
        assert film["label"] == "Si_diamond cubic#2"
        nk_files = {e["optical"]["params"]["file"] for e in out["stack"] if e["role"] in ("layer", "substrate")}
        assert len(nk_files) == 2
        for fname in nk_files:
            assert (tmp_path / fname).exists()


class TestAmbientPresets:
    """ambient accepts the literal string "air" (default, unchanged
    behavior) or a pre-built entry dict from
    materials_db.launcher.ambient.build_ambient_entry() -- checked here
    that export_stack() actually plumbs a dict through untouched, and
    rejects anything else rather than silently guessing."""

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_default_ambient_is_air(self, tmp_path):
        out = export_stack(str(_DB_PATH), layers=[], out_dir=tmp_path, stack_id="air_default_test")
        amb = out["stack"][0]
        assert amb["role"] == "ambient"
        assert amb["xray"]["sld_real"]["value"] == 0.0

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_ambient_dict_is_passed_through(self, tmp_path):
        """PORTED: upstream built this entry with
        materials_db.launcher.ambient.build_ambient_entry("d2o"), which
        does not travel with this package. The literal below is that
        function's output for D2O; the assertion -- that export_stack()
        plumbs a caller-supplied ambient dict through UNTOUCHED -- is
        what this test is actually about, and is unchanged."""
        d2o_entry = {
            "label": "D2O (heavy water)", "role": "ambient", "material_type": "ambient",
            "molecular": {"formula": "D2O", "density_g_cm3": 1.1044},
            "neutron": {"sld_real": {"value": 6.36}, "sld_imag": {"value": 0.0}},
        }
        out = export_stack(str(_DB_PATH), layers=[], ambient=d2o_entry,
                           out_dir=tmp_path, stack_id="d2o_ambient_test")
        amb = out["stack"][0]
        assert amb["label"] == "D2O (heavy water)"
        assert amb["molecular"]["formula"] == "D2O"
        assert amb["neutron"]["sld_real"]["value"] > 6.0  # real D2O contrast, not 0

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_unknown_ambient_string_raises(self, tmp_path):
        with pytest.raises(ExportError, match="Unknown ambient"):
            export_stack(str(_DB_PATH), layers=[], ambient="helium",
                         out_dir=tmp_path, stack_id="bad_ambient_test")


class TestWholeCatalogAsSubstrateOrFilm:
    """The launcher's whole premise is that ANY of the 133 exportable
    materials can be picked as a substrate or a film layer, not just the
    one combination (HfO2 on sapphire) exercised by hand end-to-end.
    Substrate especially was never bulk-tested before this launcher --
    only Silicon (the fixed placeholder) had ever been used in that role
    across this whole project. These run the real DB, once per material,
    catching exactly the class of bug the Sapphire nk-filename collision
    was (something that only shows up on a specific real polymorph
    string, not on the one or two materials a hand-written test happens
    to pick)."""

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_every_selectable_material_works_as_substrate(self, tmp_path):
        """PORTED: upstream enumerated materials via
        materials_db.launcher.catalog.list_materials(), which pre-filters
        to `selectable` rows and does its own polymorph resolution. This
        package's list_materials() reads the DB directly, so the sweep
        below tolerates a genuinely-ambiguous polymorph (export_stack
        raises ExportError asking for a dataset_label -- correct behavior,
        not a failure) and counts against the database rather than a
        hardcoded 133."""
        rows = list_materials(str(_DB_PATH))
        assert rows, "database has no materials"

        failures, skipped = [], []
        for r in rows:
            d = tmp_path / str(r["material_id"])
            d.mkdir()
            try:
                out = export_stack(str(_DB_PATH), layers=[], substrate=r["name"],
                                    substrate_roughness_a=3.0, out_dir=d,
                                    stack_id="whole_catalog_substrate_test")
                sub = out["stack"][-1]
                csv_files = list(d.glob("*.csv"))
                # Exactly one sidecar file, and it must be a FLAT file in
                # out_dir (not nested) -- the Sapphire "corundum/sapphire"
                # regression this whole class exists to catch.
                if len(csv_files) != 1:
                    failures.append((r["name"], f"expected 1 sidecar csv, found {len(csv_files)}"))
                elif "/" in sub["optical"]["params"]["file"]:
                    failures.append((r["name"], f"nested path in optical.params.file: {sub['optical']['params']['file']}"))
            except ExportError:
                # Expected for a material with no citable density, no
                # optical data, or several polymorphs and no dataset_label
                # to choose between them. "Raise, don't guess" is the
                # contract -- this class is hunting silent WRONG output
                # (a nested sidecar path, a colliding filename), not
                # refusals.
                skipped.append(r["name"])
            except Exception as e:
                failures.append((r["name"], f"{type(e).__name__}: {e}"))

        assert not failures, f"{len(failures)}/{len(rows)} materials failed as substrate:\n" + "\n".join(
            f"  {name}: {msg}" for name, msg in failures
        )
        assert len(skipped) < len(rows) // 2, (
            f"{len(skipped)}/{len(rows)} materials raised ExportError as a substrate -- "
            f"far more than the handful of known gaps; something broader is wrong."
        )

    @pytest.mark.skipif(not _DB_PATH.exists(), reason=_NO_DB)
    def test_every_selectable_material_works_as_a_film_layer(self, tmp_path):
        """PORTED: see the substrate sweep above for why ExportError is
        counted rather than failed on."""
        rows = list_materials(str(_DB_PATH))
        assert rows, "database has no materials"

        failures, skipped = [], []
        for r in rows:
            d = tmp_path / f"film_{r['material_id']}"
            d.mkdir()
            spec = dict(material=r["name"], thickness_a=100.0, roughness_a=2.0)
            try:
                export_stack(str(_DB_PATH), layers=[spec], substrate="Silicon",
                             substrate_roughness_a=3.0, out_dir=d, stack_id="whole_catalog_film_test")
            except ExportError:
                skipped.append(r["name"])
            except Exception as e:
                failures.append((r["name"], f"{type(e).__name__}: {e}"))

        assert not failures, f"{len(failures)}/{len(rows)} materials failed as a film layer:\n" + "\n".join(
            f"  {name}: {msg}" for name, msg in failures
        )
        assert len(skipped) < len(rows) // 2, (
            f"{len(skipped)}/{len(rows)} materials raised ExportError as a film layer -- "
            f"far more than the handful of known gaps; something broader is wrong."
        )
