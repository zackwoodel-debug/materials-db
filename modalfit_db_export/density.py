"""
density.py -- vendored density-confidence constants and fit bounds
===================================================================
The five symbols exporter.py needs from materials-db's
src/materials_db/pipeline/process_condition.py, lifted verbatim.

Vendored rather than imported because process_condition.py is a 399-line
module wired into the ingestion pipeline (process-condition parsing, live
DB queries); the exporter uses exactly these five names and nothing else,
so carrying the whole module -- and the package layout it assumes --
would be dead weight in a drop-in.

The distinction these encode, in one line: a density is VERIFIED when the
stored value is trustworthy for the actual sample the optical data was
measured on, and a BULK_APPROXIMATION when a bulk/single-crystal density
is standing in for an unmeasured thin film. That difference is not
cosmetic -- it changes the fit bounds emitted below, and therefore what a
fit is allowed to do with the density.

UPSTREAM: materials-db src/materials_db/pipeline/process_condition.py
          (DENSITY_* constants, BULK_ELEMENTAL_APPROXIMATION,
           bulk_approximation_density_bounds, verified_density_bounds)
"""

DENSITY_VERIFIED = "verified"
DENSITY_BULK_APPROXIMATION = "bulk_approximation"

# The density_source value stored inside physical_properties.dataset_label
# (via the "density_{density_source}" convention) for a bulk-approximation
# density. Distinct from "MP_DFT" / "experimental lattice params" /
# "literature", all of which mean a value that IS trusted for the actual
# sample measured -- a genuinely bulk/single-crystal sample's bulk density
# is correct, not an approximation -- and so count as DENSITY_VERIFIED.
#
# Named for the case that motivated it (pure elements with no measured
# film density), but the mechanism is not element-specific: a COMPOUND
# whose only optical data is an uncharacterized sputtered/ALD/annealed
# thin film with no stated density (TiN, VN, EuS) has the identical
# problem -- a DFT bulk crystal density standing in for an unmeasured
# film. Use this same value for that case rather than inventing a second
# bulk-fallback marker.
BULK_ELEMENTAL_APPROXIMATION = "bulk_elemental_approximation"


def bulk_approximation_density_bounds(bulk_density_g_cm3: float) -> dict:
    """Physically-motivated fit bounds for a bulk_elemental_approximation
    density: evaporated/sputtered films are commonly LESS dense than bulk
    (voids, columnar/porous growth), rarely denser (occasional
    ion-bombardment-compacted sputtered films aside) -- asymmetric bounds
    matching that direction, not a naive +-X% or ModalFit's generic
    [0.5x, 2x] ParamSpec fallback (physically implausible on the high side
    for a single-element film). Emitted as "molecular.density_bounds" so a
    fit can vary density within a defensible range instead of either
    trusting a wrong fixed value or an unconstrained one."""
    return dict(min=bulk_density_g_cm3 * 0.70, max=bulk_density_g_cm3 * 1.02)


def verified_density_bounds(density_g_cm3: float) -> dict:
    """Zero-width bounds for a DENSITY_VERIFIED value: pins it, so a
    caller who naively marks every layer's density vary=True (ModalFit's
    physics.py extract_params() auto-generates a density ParamSpec for
    every layer with molecular.density_g_cm3 set, regardless of
    confidence) cannot accidentally move a value this pipeline is
    confident in."""
    return dict(min=density_g_cm3, max=density_g_cm3)
