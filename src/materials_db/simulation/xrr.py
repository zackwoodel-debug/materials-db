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
        (N,) interfacial RMS roughness in Å.  ``roughness[j]`` is the
        Nevot-Croce roughness at the interface between layer j and j+1;
        ``roughness[-1]`` is unused.

    Returns
    -------
    R:
        (M,) reflectivity, clamped to [0, 1].

    Notes
    -----
    Wavevector in layer j:  k_zj = sqrt((Q/2)² − 4π·SLD_j)
    Nevot-Croce factor:     exp(−2·k_zj·k_z(j+1)·σ_j²)
    Parratt phase factor:   exp(2i·k_z(j+1)·d_(j+1))
    Recursion initialised at the deepest interface and propagated toward
    the superstrate; R = |X_0|².
    """
    if len(sld) < 2:
        raise ValueError("parratt() requires at least 2 layers (substrate + one film)")

    n_layers = len(sld)

    # k_z in each layer; shape (N, M)
    k_z: np.ndarray = np.sqrt(
        (Q[np.newaxis, :] / 2.0) ** 2
        - 4.0 * np.pi * sld[:, np.newaxis]
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

    # Nevot-Croce roughness correction; sigma shape (N-1, 1) → broadcasts over M
    sigma = roughness[:-1, np.newaxis]
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
