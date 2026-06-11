"""Convert a StackFile to XRR Parratt inputs and QCM Voigt parameters.

Public API
----------
simulate_stack_xrr(sf, Q=None, roughness_A=3.0) -> np.ndarray
    Run the Parratt recursion on a StackFile; returns R(Q).

to_qcm_input(sf) -> dict
    Extract QCM substrate density and acoustic impedance.

to_voigt_params(layer) -> dict
    Return viscoelastic parameters, falling back to physics defaults for
    materials with no DB row (e.g. polycrystalline metal films).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from materials_db.core.stack_schema import Layer, StackFile
from materials_db.simulation.xrr import parratt

log = logging.getLogger(__name__)

# Bulk elastic constants for materials that are rarely measured by QCM-D and
# therefore have no viscoelasticity row in materials.db.
# Source: standard materials-science references (CRC Handbook, Kittel).
_PHYSICS_DEFAULTS: dict[str, dict[str, float]] = {
    "Gold":      {"modulus_storage": 27.0e9,  "modulus_loss": 0.0},
    "Chromium":  {"modulus_storage": 279.0e9, "modulus_loss": 0.0},
    "Silicon":   {"modulus_storage": 130.0e9, "modulus_loss": 0.0},
    "SiO2":      {"modulus_storage": 72.0e9,  "modulus_loss": 0.0},
    "Titanium":  {"modulus_storage": 116.0e9, "modulus_loss": 0.0},
}


def to_voigt_params(layer: Layer) -> dict[str, float | None]:
    """Return viscoelastic parameters for *layer*.

    Priority
    --------
    1. ``layer.viscoelastic`` if ``modulus_storage`` is set there.
    2. ``_PHYSICS_DEFAULTS[layer.label]`` for known crystalline materials.
    3. ``None`` for all fields when no data is available.
    """
    v = layer.viscoelastic
    if v is not None and v.modulus_storage is not None:
        return {
            "modulus_storage": v.modulus_storage,
            "modulus_loss": v.modulus_loss,
            "viscosity": v.viscosity,
            "density": v.density,
        }

    defaults = _PHYSICS_DEFAULTS.get(layer.label, {})
    if defaults:
        log.debug(
            "layer %r: using physics default G'=%.3g Pa (no DB row)",
            layer.label,
            defaults["modulus_storage"],
        )

    mol_density: float | None = (
        layer.molecular.density_g_cm3 if layer.molecular is not None else None
    )
    return {
        "modulus_storage": defaults.get("modulus_storage"),
        "modulus_loss": defaults.get("modulus_loss"),
        "viscosity": None,
        "density": mol_density,
    }


def simulate_stack_xrr(
    sf: StackFile,
    Q: Optional[np.ndarray] = None,
    roughness_A: float = 3.0,
) -> np.ndarray:
    """Run Parratt XRR reflectivity for a StackFile.

    Parameters
    ----------
    sf:
        Stack to simulate.  Each layer's ``scattering.sld_real`` is used as
        the X-ray SLD (Å⁻²).  Film layers (``role`` absent) contribute their
        ``structural.thickness.value`` (Å); ambient and substrate layers
        contribute 0 Å (semi-infinite).
    Q:
        Momentum transfer array in Å⁻¹.  Defaults to
        ``np.linspace(0.01, 0.60, 500)``.
    roughness_A:
        Uniform Nevot-Croce RMS roughness (Å) applied to every interface.

    Returns
    -------
    np.ndarray
        Reflectivity R(Q), same length as *Q*, values in [0, 1].
    """
    if Q is None:
        Q = np.linspace(0.01, 0.60, 500)

    sld_vals: list[float] = []
    d_vals: list[float] = []

    for layer in sf.stack:
        sld = 0.0
        if layer.scattering is not None and layer.scattering.sld_real is not None:
            sld = layer.scattering.sld_real
        sld_vals.append(sld)

        d = 0.0
        if (
            layer.role is None
            and layer.structural is not None
            and layer.structural.thickness is not None
        ):
            d = layer.structural.thickness.value
        d_vals.append(d)

    n = len(sld_vals)
    return parratt(
        Q,
        np.array(sld_vals),
        np.array(d_vals),
        np.full(n, roughness_A),
    )


def to_qcm_input(sf: StackFile) -> dict[str, float | None]:
    """Extract QCM substrate parameters from a StackFile.

    Returns
    -------
    dict
        ``{"density": float|None, "impedance": float|None}`` from the first
        layer whose ``role == "substrate"`` and ``qcm_substrate`` is set.
        Both values are ``None`` when no such layer exists.
    """
    for layer in sf.stack:
        if layer.role == "substrate" and layer.qcm_substrate is not None:
            return {
                "density": layer.qcm_substrate.density,
                "impedance": layer.qcm_substrate.impedance,
            }

    log.warning("stack %r: no substrate with qcm_substrate block found", sf.sample_id)
    return {"density": None, "impedance": None}
