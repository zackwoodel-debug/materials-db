"""Tests for src/materials_db/pipeline/process_condition.py: the
process_condition encoding helpers and the DENSITY_STATE four-way gate.

The density-state distinction is deliberate, not incidental: a
bulk_elemental_approximation density (the majority case for batch 3's
pure elements -- 14/359 RI.info pages state a real measured film density,
the rest would silently inherit bulk elemental density) must NOT count as
verified, because a verification_note disclosing the approximation
doesn't change what a query returns -- see docs/batch3_scoping_report.md.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.pipeline.process_condition import (  # noqa: E402
    DENSITY_BULK_APPROXIMATION,
    DENSITY_NAMED_EXCLUSION,
    DENSITY_UNRESOLVED,
    DENSITY_VERIFIED,
    bulk_approximation_density_bounds,
    crosscheck_element_density_periodictable,
    density_state_from_source,
    format_process_condition,
    looks_like_process_condition,
    materials_with_density_state,
    materials_with_uncrosschecked_mp_density,
    open_tasks,
    parse_process_condition,
    task_detail,
    verified_density_bounds,
)

_DB_PATH = ROOT / "data" / "materials_oxide_test.db"


class TestProcessConditionEncoding:
    def test_format_round_trips_through_parse(self):
        segment = format_process_condition(deposition="evaporated", thickness="25nm")
        assert segment == "deposition:evaporated;thickness:25nm"
        assert parse_process_condition(segment) == {"deposition": "evaporated", "thickness": "25nm"}

    def test_unrecognized_axis_raises(self):
        with pytest.raises(ValueError, match="Unrecognized process_condition axis"):
            format_process_condition(not_a_real_axis="x")

    def test_empty_call_raises(self):
        with pytest.raises(ValueError):
            format_process_condition()

    def test_looks_like_process_condition_true_for_real_segment(self):
        assert looks_like_process_condition("deposition:evaporated") is True
        assert looks_like_process_condition("deposition:evaporated;temperature:225C") is True

    def test_looks_like_process_condition_false_for_polymorph_or_source_label(self):
        """A process_condition segment must not be confused with a
        polymorph name or an AuthorYYYY source label -- the exact
        ambiguity that caused batch 1's polymorph-fallback bug."""
        assert looks_like_process_condition("rutile") is False
        assert looks_like_process_condition("Devore1951") is False
        assert looks_like_process_condition("K2NiF4-type") is False


class TestDensityStateGate:
    def test_bulk_elemental_approximation_is_not_verified(self):
        """The core requirement: this must be its own state, never folded
        into DENSITY_VERIFIED."""
        assert density_state_from_source("bulk_elemental_approximation") == DENSITY_BULK_APPROXIMATION
        assert DENSITY_BULK_APPROXIMATION != DENSITY_VERIFIED

    def test_trusted_sources_are_verified(self):
        assert density_state_from_source("MP_DFT") == DENSITY_VERIFIED
        assert density_state_from_source("experimental lattice params") == DENSITY_VERIFIED
        assert density_state_from_source("literature") == DENSITY_VERIFIED

    def test_unrecognized_source_is_unresolved_not_verified(self):
        assert density_state_from_source("something_new") == DENSITY_UNRESOLVED

    def test_bulk_approximation_bounds_are_asymmetric_and_below_bulk(self):
        """Films are commonly less dense than bulk (voids, porous/columnar
        growth), rarely denser -- bounds must reflect that direction, not
        a naive symmetric +-X%."""
        bounds = bulk_approximation_density_bounds(10.0)
        assert bounds["min"] < 10.0
        assert bounds["max"] > 10.0
        # asymmetric: allows more room below bulk than above it
        assert (10.0 - bounds["min"]) > (bounds["max"] - 10.0)

    def test_verified_bounds_are_pinned(self):
        """A verified density must be pinned (zero-width bounds) so a
        caller who marks every layer's density vary=True can't
        accidentally move a value this pipeline is confident in --
        physics.py's extract_params() auto-generates a density ParamSpec
        for ANY layer with molecular.density_g_cm3 set, regardless of
        confidence, with a wide [0.5x, 2x] fallback if no bounds are
        given."""
        bounds = verified_density_bounds(4.5)
        assert bounds["min"] == bounds["max"] == 4.5


class TestMaterialsWithDensityState:
    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_verified_returns_the_oxide_and_batch2_materials(self):
        verified = materials_with_density_state(str(_DB_PATH), DENSITY_VERIFIED)
        formulas = {m["formula"] for m in verified}
        assert "TiO2" in formulas
        assert "ZnS" in formulas
        # GdF3 and LuAl3(BO3)4 have NO density row at all (named
        # exclusions) -- must not appear as verified.
        assert "GdF3" not in formulas
        assert "LuAl3(BO3)4" not in formulas

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_bulk_approximation_includes_tin_vn_eus_au_and_most_pure_elements(self):
        """TiN/VN/EuS were folded into batch 2 once process_condition
        existed: no RI.info page for any of the three states a measured
        film density, so their MP-bulk-crystal density is relabeled
        bulk_elemental_approximation rather than trusted as verified.
        Gold and 32 other pure elements (36 total here, alongside
        TiN/VN/EuS) are the same: no entry in their corpus states a
        measured film density, and their default dataset isn't confirmed
        genuinely bulk/single-crystal either. Batch 3b adds one more, the
        element Tin (formula "Sn"): Golovashkin and Motulevich 1964 states
        no measured film density and no bulk/single-crystal claim for the
        beta-Sn sample, the same default-to-approximation policy as every
        other pure element here -- 37 total."""
        bulk = materials_with_density_state(str(_DB_PATH), DENSITY_BULK_APPROXIMATION)
        formulas = {m["formula"] for m in bulk}
        assert {"TiN", "VN", "EuS", "Au", "Sn"} <= formulas
        assert len(formulas) == 37

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_verified_includes_bulk_single_crystal_elements(self):
        """Se and Te are pure-element cases where MP_DFT bulk density IS
        verified, not approximated: their default RI.info datasets are
        genuinely bulk/single-crystal (Se explicitly stated; Te inferred
        from o/e polarization-resolved measurement), unlike Au's."""
        verified = materials_with_density_state(str(_DB_PATH), DENSITY_VERIFIED)
        formulas = {m["formula"] for m in verified}
        assert {"Se", "Te"} <= formulas
        assert "Au" not in formulas

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_invalid_state_raises(self):
        with pytest.raises(ValueError, match="Unrecognized density state"):
            materials_with_density_state(str(_DB_PATH), "not_a_real_state")


class TestTrackedOpenTasks:
    """The oxide-amorphous migration must be a tracked, queryable open
    item in the repo -- not just a note left in a conversation -- same
    treatment as EXCLUSION_STATE's blocking_on queries."""

    def test_oxide_amorphous_migration_is_open(self):
        assert "oxide_amorphous_migration" in open_tasks()

    def test_task_detail_has_scope_and_cost(self):
        detail = task_detail("oxide_amorphous_migration")
        assert set(detail["affected_materials"]) == {"Nb2O5", "SiO", "SiO2", "Ta2O5", "GeO2"}
        assert len(detail["affected_call_sites"]) >= 3
        assert detail["cost_estimate"]
        assert detail["status"] == "open"

    def test_unknown_task_raises(self):
        with pytest.raises(ValueError, match="Unrecognized task id"):
            task_detail("not_a_real_task")

    def test_mp_density_crosscheck_compounds_is_open_with_66_materials(self):
        assert "mp_density_crosscheck_compounds" in open_tasks()
        detail = task_detail("mp_density_crosscheck_compounds")
        assert len(detail["affected_materials"]) == 66
        assert "CuO" in detail["affected_materials"]  # one of the spot-checked-but-not-yet-cited


class TestMpDensityCrosscheck:
    """Ce and Yb showed MP_DFT density can be wrong by 35-41% -- an
    uncrosschecked MP_DFT density isn't meaningfully more trustworthy
    than DENSITY_BULK_APPROXIMATION. These make "how many materials are
    exposed" and "does this specific value check out" real, queryable
    answers instead of a two-material footnote."""

    @pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")
    def test_uncrosschecked_mp_density_count(self):
        """71 materials across all batches currently have a raw,
        uncrosschecked MP_DFT density -- the real count, not a guess.
        Batch 3b adds Diamond: its MP_DFT density (3.534 g/cm3, mp-66) is
        VERIFIED via VERIFIED_BULK_SAMPLE_FORMULAS (Taylor's page states
        "Single-crystal CVD" outright) rather than an approximation, but
        that trust rests on a manual literature comparison during this
        batch's resolution (matches real diamond's ~3.51-3.52 g/cm3), not
        an independent, citable, DB-recorded cross-check -- so it correctly
        still counts here. Graphite and Tin do NOT count: Graphite's
        density_source is "experimental lattice params" (an
        EXPERIMENTAL_DENSITY_OVERRIDE, not raw MP_DFT) and Tin's is
        bulk_elemental_approximation, neither of which matches this
        function's "density_MP_DFT" dataset_label filter -- 72 total."""
        uncrosschecked = materials_with_uncrosschecked_mp_density(str(_DB_PATH))
        assert len(uncrosschecked) == 72
        formulas = {m["formula"] for m in uncrosschecked}
        assert "Se" in formulas  # a pure element, cross-checked clean via periodictable
        assert "CuO" in formulas  # a compound, spot-checked clean via literature
        assert "C" in formulas  # Diamond (batch 3b) -- verified by domain knowledge, not a DB-recorded crosscheck

    def test_crosscheck_matches_known_good_value(self):
        """Se's DB density (4.4956) vs periodictable's handbook value
        (4.79) is a real, already-computed -6.1% deviation -- well under
        the flag threshold."""
        result = crosscheck_element_density_periodictable("Se", 4.495591)
        assert result["periodictable_density"] == pytest.approx(4.79, abs=0.01)
        assert not result["flagged"]

    def test_crosscheck_flags_a_large_deviation(self):
        """Reproduce the Ce case directly: MP_DFT's raw value (9.1237,
        before the literature override) vs periodictable's handbook value
        (6.77) is a +35% deviation -- exactly the case this mechanism
        exists to catch."""
        result = crosscheck_element_density_periodictable("Ce", 9.1237)
        assert result["flagged"] is True
        assert result["deviation_pct"] > 30

    def test_crosscheck_raises_for_a_compound(self):
        with pytest.raises(ValueError, match="not a recognized single element"):
            crosscheck_element_density_periodictable("TiO2", 4.23)
