"""Integration tests for the stack schema / exporter / simulation pipeline.

Run with:
    pytest tests/test_stack_pipeline.py -v
"""

import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "materials.db"
STACKS_DIR = ROOT / "data" / "stacks"

# Shared SLD constants (match verify_all.py exactly)
_NA = 6.02214076e23
_R_E = 2.8179403e-5


def _xsld(rho: float, mw: float, z: int) -> float:
    return float((rho * _NA * z) / (mw * 1e24) * _R_E)


SLD_SI = _xsld(2.329, 28.085, 14)
SLD_SIO2 = _xsld(2.196, 60.085, 30)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    if not DB_PATH.exists():
        pytest.skip(f"materials.db not found: {DB_PATH}")
    return DB_PATH


@pytest.fixture(scope="module")
def ps_gold_stack(db):
    """PS:1000 Å / Gold:50 Å / quartz stack exported from the live DB."""
    from materials_db.pipeline.stack_exporter import build_stack

    return build_stack(
        [
            {"material": "Polystyrene", "thickness": 1000.0},
            {"material": "Gold", "thickness": 50.0},
            {"material": "quartz", "substrate": True},
        ],
        sample_id="test-ps-gold",
        user="pytest",
        proposal_id="P-test",
        db_path=db,
    )


@pytest.fixture(scope="module")
def sio2_si_stack():
    """Minimal vacuum / SiO2(20 Å) / Si StackFile built inline for XRR tests."""
    from materials_db.core.stack_schema import (
        BoundedValue,
        Layer,
        Scattering,
        StackFile,
        Structural,
    )

    return StackFile(
        stack_id="test-xrr",
        sample_id="SiO2-on-Si",
        material="SiO2",
        n_layers=3,
        stack=[
            Layer(
                label="Vacuum",
                material_type="vacuum",
                role="ambient",
                scattering=Scattering(sld_real=0.0),
            ),
            Layer(
                label="SiO2",
                material_type="oxide",
                structural=Structural(thickness=BoundedValue(value=20.0)),
                scattering=Scattering(sld_real=SLD_SIO2),
            ),
            Layer(
                label="Silicon",
                material_type="semiconductor",
                role="substrate",
                scattering=Scattering(sld_real=SLD_SI),
            ),
        ],
    )


# ── 1. Schema round-trip ───────────────────────────────────────────────────────

class TestStackSchemaRoundtrip:
    @pytest.mark.parametrize("name", ["pmma_gold_si.json", "dppc_bilayer_si.json"])
    def test_json_roundtrip(self, name):
        path = STACKS_DIR / name
        if not path.exists():
            pytest.skip(f"Stack file not found: {path}")
        from materials_db.core.stack_schema import _round_trip_check
        _round_trip_check(path)  # raises AssertionError on mismatch

    def test_physics_valid_pmma_gold(self):
        path = STACKS_DIR / "pmma_gold_si.json"
        if not path.exists():
            pytest.skip(f"Stack file not found: {path}")
        from materials_db.core.stack_schema import StackFile
        sf = StackFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        violations = sf.validate_physics()
        assert violations == [], f"Unexpected physics violations: {violations}"


# ── 2. Export PS / Gold ────────────────────────────────────────────────────────

class TestStackExportPsGold:
    def test_n_polystyrene(self, ps_gold_stack):
        # stack[0]=Air, stack[1]=Polystyrene, stack[2]=Gold, stack[3]=SiO2
        ps = ps_gold_stack.stack[1]
        assert ps.molecular is not None, "Polystyrene layer has no molecular block"
        assert ps.molecular.n_at_633nm == pytest.approx(1.5875, abs=0.01)

    def test_xray_sld_polystyrene(self, ps_gold_stack):
        ps = ps_gold_stack.stack[1]
        assert ps.molecular is not None
        assert ps.molecular.xray_sld_A2_CuKa == pytest.approx(9.58e-6, rel=0.05)

    def test_gold_shear_modulus_from_defaults(self, ps_gold_stack):
        """Gold has no DB viscoelasticity row; physics default gives G'=27 GPa."""
        from materials_db.pipeline.stack_to_sim import to_voigt_params

        gold = ps_gold_stack.stack[2]
        params = to_voigt_params(gold)
        assert params["modulus_storage"] == pytest.approx(27e9)

    def test_n_layers(self, ps_gold_stack):
        # Air + PS + Gold + SiO2 = 4 layers
        assert ps_gold_stack.n_layers == 4

    def test_substrate_is_sio2(self, ps_gold_stack):
        sub = ps_gold_stack.stack[3]
        assert sub.role == "substrate"
        assert sub.label == "SiO2"


# ── 3. Physics rejection ───────────────────────────────────────────────────────

class TestStackPhysicsRejects:
    def test_rejects_low_n_polymer(self):
        """n < 1.0 on a non-metal polymer must produce a validate_physics violation."""
        from materials_db.core.stack_schema import Layer, Molecular, StackFile

        bad = StackFile(
            stack_id="bad-n",
            sample_id="reject-test",
            material="FakePolymer",
            n_layers=2,
            stack=[
                Layer(label="Vacuum", role="ambient"),
                Layer(
                    label="FakePolymer",
                    material_type="polymer",
                    molecular=Molecular(n_at_633nm=0.5),
                ),
            ],
        )
        violations = bad.validate_physics()
        assert any("n_at_633nm" in v for v in violations), (
            f"Expected n_at_633nm violation, got: {violations}"
        )

    def test_rejects_negative_thickness(self):
        """Negative film thickness must produce a validate_physics violation."""
        from materials_db.core.stack_schema import (
            BoundedValue,
            Layer,
            StackFile,
            Structural,
        )

        bad = StackFile(
            stack_id="bad-d",
            sample_id="reject-test",
            material="Polymer",
            n_layers=2,
            stack=[
                Layer(label="Vacuum", role="ambient"),
                Layer(
                    label="Polymer",
                    material_type="polymer",
                    structural=Structural(thickness=BoundedValue(value=-10.0)),
                ),
            ],
        )
        violations = bad.validate_physics()
        assert any("thickness" in v for v in violations), (
            f"Expected thickness violation, got: {violations}"
        )

    def test_metal_with_low_n_is_allowed(self):
        """n < 1 is physically valid for metals; validate_physics must not flag it."""
        from materials_db.core.stack_schema import Layer, Molecular, StackFile

        sf = StackFile(
            stack_id="metal-ok",
            sample_id="metal-test",
            material="Gold",
            n_layers=2,
            stack=[
                Layer(label="Vacuum", role="ambient"),
                Layer(
                    label="Gold",
                    material_type="metal",
                    molecular=Molecular(n_at_633nm=0.18, k_at_633nm=3.45),
                ),
            ],
        )
        violations = sf.validate_physics()
        assert violations == [], f"Metal low-n should not be flagged: {violations}"


# ── 4. XRR simulation ─────────────────────────────────────────────────────────

class TestStackXrrRuns:
    def test_ter_plateau(self, sio2_si_stack):
        """R should be ≈1 below the critical edge (TER)."""
        from materials_db.pipeline.stack_to_sim import simulate_stack_xrr

        Q = np.linspace(0.01, 0.60, 500)
        R = simulate_stack_xrr(sio2_si_stack, Q=Q)

        q_c_approx = np.sqrt(16.0 * np.pi * SLD_SI)
        plateau_mask = Q < 0.8 * q_c_approx
        assert np.all(R[plateau_mask] > 0.999), (
            f"TER plateau failed: min R = {R[plateau_mask].min():.6f}"
        )

    def test_high_q_decay(self, sio2_si_stack):
        """R should be small at high Q (above the critical edge)."""
        from materials_db.pipeline.stack_to_sim import simulate_stack_xrr

        Q = np.linspace(0.01, 0.60, 500)
        R = simulate_stack_xrr(sio2_si_stack, Q=Q)

        assert R[Q > 0.4].max() < 0.01, (
            f"High-Q decay failed: max R = {R[Q > 0.4].max():.4f}"
        )

    def test_r_bounds(self, sio2_si_stack):
        """Reflectivity must stay in [0, 1] for all Q."""
        from materials_db.pipeline.stack_to_sim import simulate_stack_xrr

        R = simulate_stack_xrr(sio2_si_stack)
        assert np.all((R >= 0.0) & (R <= 1.0)), (
            f"R out of [0, 1]: min={R.min():.6f}, max={R.max():.6f}"
        )

    def test_default_q_length(self, sio2_si_stack):
        from materials_db.pipeline.stack_to_sim import simulate_stack_xrr

        R = simulate_stack_xrr(sio2_si_stack)
        assert len(R) == 500


# ── 5. QCM substrate mapping ──────────────────────────────────────────────────

class TestStackQcmMapping:
    def test_impedance(self, ps_gold_stack):
        """Quartz substrate impedance must be 8.8e6 Pa·s/m."""
        from materials_db.pipeline.stack_to_sim import to_qcm_input

        qcm = to_qcm_input(ps_gold_stack)
        assert qcm["impedance"] == pytest.approx(8.8e6)

    def test_density_present(self, ps_gold_stack):
        from materials_db.pipeline.stack_to_sim import to_qcm_input

        qcm = to_qcm_input(ps_gold_stack)
        assert qcm["density"] is not None
        assert qcm["density"] > 0.0

    def test_no_qcm_substrate_returns_none(self):
        """A stack with no QCM substrate must return None impedance without error."""
        from materials_db.core.stack_schema import Layer, StackFile
        from materials_db.pipeline.stack_to_sim import to_qcm_input

        sf = StackFile(
            stack_id="no-qcm",
            sample_id="bare",
            material="Vacuum",
            n_layers=2,
            stack=[
                Layer(label="Vacuum", role="ambient"),
                Layer(label="Silicon", material_type="semiconductor", role="substrate"),
            ],
        )
        qcm = to_qcm_input(sf)
        assert qcm["impedance"] is None
        assert qcm["density"] is None
