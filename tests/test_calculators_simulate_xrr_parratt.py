"""Regression tests for materials_db.calculators.simulate_xrr.parratt, for
the two bugs found running a real fit through the full DB -> exporter ->
ModalFit chain (see docs/xrr_fit_findings.md):

  1. The same imaginary-SLD-not-conjugated bug as materials_db.simulation.
     xrr.parratt (see tests/test_simulation_xrr_parratt.py) -- inverts the
     sign of absorptive damping through any film with non-negligible
     imaginary SLD.
  2. An independent phase-factor bug: exp(2i*q_j*d) instead of exp(i*q_j*d),
     double what this function's own "full-Q" convention (q_j = 2*k_z)
     needs -- doubling every Kiessig fringe frequency, independent of
     absorption. This function has no roughness parameter, so this bug is
     visible even without any roughness involved.

Golden values were computed directly against refnx (the reference
reflectometry package ModalFit's fitting code actually uses) on a real
HfO2-on-Si stack with non-negligible absorption -- deliberately NOT the
non-absorbing case, which passes under bug 1 either way and would not have
caught it. refnx itself is NOT a test dependency (it's not declared
anywhere in this repo); these are pinned reference numbers, not a live
cross-check. See docs/xrr_fit_findings.md for the full diagnosis and how
these numbers were produced.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.calculators.simulate_xrr import parratt as parratt_calc  # noqa: E402

_HFO2 = complex(67.67877469252173, 4.414052717836418)
_SIO2 = complex(18.865310054981503, 0.2437777561546431)
_SI = complex(20.062, 0.457236)
_Q = np.array([0.02, 0.05, 0.1, 0.15, 0.2, 0.3])

# Golden values from a direct refnx build of the identical stack (no
# roughness, since this function has no roughness parameter), reproduced
# by the fixed parratt() to machine precision (~1e-16 in log10(R)) at the
# time this test was written.
_GOLDEN_NO_ROUGHNESS = np.array([
    9.53631397e-01, 8.06174493e-01, 1.21858463e-02,
    4.36522968e-03, 1.20303963e-03, 1.65938266e-04,
])


class TestCalculatorsSimulateXrrParratt:
    """materials_db.calculators.simulate_xrr.parratt -- full-Q convention, no roughness param."""

    def test_matches_refnx_on_absorbing_multilayer_stack(self):
        sld = np.array([0.0, _HFO2, _SIO2, _SI]) * 1e-6
        thickness = np.array([0.0, 250.0, 15.0, 0.0])
        R = parratt_calc(_Q, sld, thickness)
        np.testing.assert_allclose(np.log10(R), np.log10(_GOLDEN_NO_ROUGHNESS), atol=1e-6)

    def test_absorption_sign_matters(self):
        sld = np.array([0.0, _HFO2, _SIO2, _SI]) * 1e-6
        sld_flipped = np.array([0.0, _HFO2.conjugate(), _SIO2.conjugate(), _SI.conjugate()]) * 1e-6
        thickness = np.array([0.0, 250.0, 15.0, 0.0])
        R = parratt_calc(_Q, sld, thickness)
        R_flipped = parratt_calc(_Q, sld_flipped, thickness)
        assert not np.allclose(R, R_flipped)
        np.testing.assert_allclose(np.log10(R), np.log10(_GOLDEN_NO_ROUGHNESS), atol=1e-6)
        assert np.max(np.abs(np.log10(R_flipped) - np.log10(_GOLDEN_NO_ROUGHNESS))) > 0.1

    def test_phase_factor_is_not_doubled(self):
        """Regression for bug 2: the old exp(2i*q_j*d) phase factor doubled
        the fringe frequency for EVERY stack with a film, independent of
        absorption -- reproduce it explicitly and confirm it disagrees."""
        sld = np.array([0.0, _HFO2, _SIO2, _SI]) * 1e-6
        thickness = np.array([0.0, 250.0, 15.0, 0.0])

        def parratt_doubled_phase(q_arr, slds, thicknesses):
            n_media = len(slds)
            slds_eff = slds.real - 1j * slds.imag
            q_j = np.sqrt(q_arr[np.newaxis, :] ** 2 - 16.0 * np.pi * slds_eff[:, np.newaxis] + 0j)
            q_j = np.where(q_j.real < 0.0, -q_j, q_j)
            num, denom = q_j[:-1] - q_j[1:], q_j[:-1] + q_j[1:]
            with np.errstate(divide="ignore", invalid="ignore"):
                r = np.where(denom == 0.0, np.complex128(-1.0), num / denom)
            X = r[-1].copy()
            for j in range(n_media - 3, -1, -1):
                phase = np.exp(2j * q_j[j + 1] * thicknesses[j + 1])  # the old bug
                rj = r[j]
                X = (rj + X * phase) / (1.0 + rj * X * phase)
            R = np.abs(X) ** 2
            np.clip(R, 0.0, 1.0, out=R)
            return R

        R_fixed = parratt_calc(_Q, sld, thickness)
        R_doubled = parratt_doubled_phase(_Q, sld, thickness)
        np.testing.assert_allclose(np.log10(R_fixed), np.log10(_GOLDEN_NO_ROUGHNESS), atol=1e-6)
        assert np.max(np.abs(np.log10(R_doubled) - np.log10(_GOLDEN_NO_ROUGHNESS))) > 0.5

    def test_critical_angle_matches_theory(self):
        """Bare-interface sanity check: the bugs above only manifest with a
        film and/or absorption, so this must have kept passing throughout."""
        si_r = 20.062
        Qc_theory = np.sqrt(16 * np.pi * si_r * 1e-6)
        Q = np.linspace(0.001, 0.08, 500)
        sld = np.array([0.0, si_r]) * 1e-6
        R = parratt_calc(Q, sld, np.array([0.0, 0.0]))
        q_half = Q[np.argmin(np.abs(R - 0.5))]
        assert abs(q_half - Qc_theory) < 0.002
