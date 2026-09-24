"""Regression tests for materials_db.simulation.xrr.parratt, for the two
bugs found running a real fit through the full DB -> exporter -> ModalFit
chain (see docs/xrr_fit_findings.md):

  1. Used the imaginary SLD directly (not conjugated) in its k_z formula,
     inverting the sign of absorptive damping through any film with
     non-negligible imaginary SLD.
  2. roughness[j] meant "interface between layer j and j+1"; the correct
     (refnx-matching) convention is "interface ABOVE layer j" -- i.e.
     roughness[j+1], not roughness[j].

Golden values below were computed directly against refnx (the reference
reflectometry package ModalFit's fitting code actually uses) on a real
HfO2-on-Si stack with non-negligible absorption -- deliberately NOT the
non-absorbing case, which passes under bug 1 either way and would not have
caught it. refnx itself is NOT a test dependency (it's not declared
anywhere in this repo); these are pinned reference numbers, not a live
cross-check, matching the "pin a stored reference curve instead of taking
on a dependency for tests alone" preference. See docs/xrr_fit_findings.md
for the full diagnosis and how these numbers were produced.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.simulation.xrr import parratt as parratt_sim  # noqa: E402

# air / HfO2 (250 A, rough=4 A) / SiO2 (15 A, rough=3 A) / Si (rough=3 A),
# real DB SLD values (xray, Cu K-alpha) -- the exact stack used in the real
# fit exercise. HfO2 and SiO2 both carry non-negligible imaginary SLD.
_HFO2 = complex(67.67877469252173, 4.414052717836418)
_SIO2 = complex(18.865310054981503, 0.2437777561546431)
_SI = complex(20.062, 0.457236)
_Q = np.array([0.02, 0.05, 0.1, 0.15, 0.2, 0.3])

# Golden values from a direct refnx build of the identical stack
# (ReflectModel(structure, scale=1.0, bkg=0.0, dq=0.0)(Q)), reproduced
# independently by the fixed parratt() to machine precision (~1e-16 in
# log10(R)) at the time this test was written.
_GOLDEN_WITH_ROUGHNESS = np.array([
    9.53014132e-01, 8.03804495e-01, 1.08278994e-02,
    3.32115752e-03, 7.26870104e-04, 5.18822603e-05,
])


class TestSimulationXrrParratt:
    """materials_db.simulation.xrr.parratt -- supports roughness."""

    def test_matches_refnx_on_absorbing_multilayer_stack(self):
        sld = np.array([0.0, _HFO2, _SIO2, _SI]) * 1e-6
        thickness = np.array([0.0, 250.0, 15.0, 0.0])
        roughness = np.array([0.0, 4.0, 3.0, 3.0])  # roughness[k] = interface ABOVE layer k
        R = parratt_sim(_Q, sld, thickness, roughness)
        np.testing.assert_allclose(np.log10(R), np.log10(_GOLDEN_WITH_ROUGHNESS), atol=1e-6)

    def test_absorption_sign_matters(self):
        """Regression for bug 1: flipping the imaginary SLD's sign must
        change the result -- if it didn't, absorption wouldn't be doing
        anything (the old, unconjugated code silently produced a DIFFERENT
        but self-consistent-looking curve, not an obviously-broken one)."""
        sld = np.array([0.0, _HFO2, _SIO2, _SI]) * 1e-6
        sld_flipped = np.array([0.0, _HFO2.conjugate(), _SIO2.conjugate(), _SI.conjugate()]) * 1e-6
        thickness = np.array([0.0, 250.0, 15.0, 0.0])
        roughness = np.array([0.0, 4.0, 3.0, 3.0])
        R = parratt_sim(_Q, sld, thickness, roughness)
        R_flipped = parratt_sim(_Q, sld_flipped, thickness, roughness)
        assert not np.allclose(R, R_flipped), (
            "flipping the imaginary SLD sign produced no change -- "
            "absorption isn't affecting the result at all"
        )
        # And specifically: the correctly-signed (as-stored) SLD must match
        # the refnx golden value; the flipped one must NOT.
        np.testing.assert_allclose(np.log10(R), np.log10(_GOLDEN_WITH_ROUGHNESS), atol=1e-6)
        assert np.max(np.abs(np.log10(R_flipped) - np.log10(_GOLDEN_WITH_ROUGHNESS))) > 0.1

    def test_roughness_attaches_above_not_below(self):
        """Regression for bug 2: roughness on the WRONG layer (the old,
        off-by-one convention) must NOT match the refnx golden value."""
        sld = np.array([0.0, _HFO2, _SIO2, _SI]) * 1e-6
        thickness = np.array([0.0, 250.0, 15.0, 0.0])
        roughness_correct = np.array([0.0, 4.0, 3.0, 3.0])
        # old (wrong) convention: roughness[:-1] used to be read as sigma,
        # i.e. as if each layer's OWN roughness governed the interface
        # BELOW it. Reproduce that misattachment explicitly here.
        roughness_shifted_wrong = np.array([4.0, 3.0, 3.0, 0.0])
        R_correct = parratt_sim(_Q, sld, thickness, roughness_correct)
        R_wrong = parratt_sim(_Q, sld, thickness, roughness_shifted_wrong)
        np.testing.assert_allclose(np.log10(R_correct), np.log10(_GOLDEN_WITH_ROUGHNESS), atol=1e-6)
        assert np.max(np.abs(np.log10(R_wrong) - np.log10(_GOLDEN_WITH_ROUGHNESS))) > 0.1

    def test_critical_angle_matches_theory(self):
        """Bare-interface sanity check: the bugs above only manifest with a
        film and/or absorption, so this must have kept passing throughout."""
        si_r = 20.062
        Qc_theory = np.sqrt(16 * np.pi * si_r * 1e-6)
        Q = np.linspace(0.001, 0.08, 500)
        sld = np.array([0.0, si_r]) * 1e-6
        R = parratt_sim(Q, sld, np.array([0.0, 0.0]), np.array([0.0, 0.0]))
        q_half = Q[np.argmin(np.abs(R - 0.5))]
        assert abs(q_half - Qc_theory) < 0.002
