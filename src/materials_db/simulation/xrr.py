"""Parratt XRR reflectivity with Nevot-Croce roughness."""

import numpy as np


def parratt(
    Q: np.ndarray,
    sld: np.ndarray,
    thickness: np.ndarray,
    roughness: np.ndarray,
) -> np.ndarray:
    """Parratt recursion for specular X-ray reflectivity.

    Parameters
    ----------
    Q:
        (M,) momentum transfer in Å⁻¹ (Q = 4π sinθ / λ).
    sld:
        (N,) X-ray SLD in Å⁻² per layer; ``sld[0]`` = superstrate,
        ``sld[-1]`` = substrate.
    thickness:
        (N,) layer thickness in Å; ``thickness[0]`` and ``thickness[-1]``
        are not used (semi-infinite bounding media).
    roughness:
        (N,) interfacial RMS roughness in Å.  ``roughness[k]`` is the
        Nevot-Croce roughness of the interface ABOVE layer k (between
        layer k-1 and layer k) -- i.e. the same "this slab's own
        roughness describes its upper interface" convention refnx uses
        (verified empirically against refnx directly, see
        docs/xrr_fit_findings.md). ``roughness[0]`` (ambient has nothing
        above it) is unused.

    Returns
    -------
    R:
        (M,) reflectivity, clamped to [0, 1].

    Notes
    -----
    Wavevector in layer j:  k_zj = sqrt((Q/2)² − 4π·conj(SLD_j))
    Nevot-Croce factor:     exp(−2·k_zj·k_z(j+1)·σ_(j+1)²)
    Parratt phase factor:   exp(2i·k_z(j+1)·d_(j+1))
    Recursion initialised at the deepest interface and propagated toward
    the superstrate; R = |X_0|².

    The k_z formula uses conj(SLD) (i.e. SLD.real - 1j*SLD.imag), NOT
    SLD directly -- SLD is stored here (and everywhere else in this repo:
    periodictable's xray_sld(), the materials_oxide_test.db xray_sld_imag
    column, ModalFit's own refnx-based exporter) with a POSITIVE
    imaginary part meaning absorption, e.g. HfO2's xray_sld_imag=4.41.
    Using that value directly in this formula, without the conjugate,
    silently inverts the sign of absorptive damping through any film with
    non-negligible imaginary SLD -- found by cross-checking this function
    against refnx (which ModalFit's real fits actually use) on a real
    HfO2-on-Si stack: the two curves matched to machine precision with
    non-absorbing SLDs, and diverged by orders of magnitude at fringe
    minima the moment realistic absorption was reintroduced. See
    docs/xrr_fit_findings.md for the full diagnosis.
    """
    if len(sld) < 2:
        raise ValueError("parratt() requires at least 2 layers (substrate + one film)")

    n_layers = len(sld)

    # k_z in each layer; shape (N, M). conj(sld): see the absorption-sign
    # note in the docstring above -- this is not a stylistic choice.
    sld_eff = sld.real - 1j * sld.imag
    k_z: np.ndarray = np.sqrt(
        (Q[np.newaxis, :] / 2.0) ** 2
        - 4.0 * np.pi * sld_eff[:, np.newaxis]
        + 0j
    )
    # Physical root: non-negative real part (evanescent waves decay downward)
    k_z = np.where(k_z.real < 0.0, -k_z, k_z)

    # Fresnel reflection coefficients; shape (N-1, M)
    k_lo = k_z[:-1]
    k_hi = k_z[1:]
    denom = k_lo + k_hi
    with np.errstate(divide="ignore", invalid="ignore"):
        r: np.ndarray = np.where(
            denom == 0.0,
            np.complex128(-1.0),
            (k_lo - k_hi) / denom,
        )

    # Nevot-Croce roughness correction; sigma shape (N-1, 1) -> broadcasts
    # over M. roughness[1:], NOT roughness[:-1]: interface i (between
    # layer i and i+1) takes its roughness from layer i+1 (the layer
    # BELOW it, i.e. the one whose own "rough" attribute describes this
    # interface in refnx's convention) -- see the roughness parameter
    # note above.
    sigma = roughness[1:, np.newaxis]
    r = r * np.exp(-2.0 * k_lo * k_hi * sigma ** 2)

    # Parratt recursion: substrate → superstrate
    # Init at the deepest interface (between layer N-2 and substrate N-1)
    X: np.ndarray = r[-1].copy()
    for j in range(n_layers - 3, -1, -1):
        phase = np.exp(2j * k_z[j + 1] * thickness[j + 1])
        rj = r[j]
        X = (rj + X * phase) / (1.0 + rj * X * phase)

    R = np.abs(X) ** 2
    np.clip(R, 0.0, 1.0, out=R)
    return R
