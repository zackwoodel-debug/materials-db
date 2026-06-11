#!/usr/bin/env python3
"""
calculators/sld_calculator.py
=============================
Physical constants and calculations for X-ray and Neutron Scattering Length Densities (SLD).
Supports energy/frequency/wavelength conversions and isotope-specific scattering lengths.
"""

import re
from typing import Dict, Optional, Tuple, Union

# Avogadro constant (CODATA 2018)
NA = 6.02214076e23

# Classical electron radius in Angstroms
R_E = 2.8179403e-5

# Atomic numbers and weights for common elements/isotopes
ATOMS: Dict[str, Tuple[int, float]] = {
    "H":  (1,   1.00794),
    "D":  (1,   2.01410),  # Deuterium
    "C":  (6,  12.0107),
    "N":  (7,  14.0067),
    "O":  (8,  15.9994),
    "F":  (9,  18.9984),
    "Al": (13, 26.9815),
    "Si": (14, 28.0855),
    "P":  (15, 30.97376),
    "S":  (16, 32.065),
    "Ti": (22, 47.867),
    "Zn": (30, 65.380),
    "Cr": (24, 51.996),
    "Ag": (47, 107.868),
    "In": (49, 114.818),
    "Sn": (50, 118.710),
    "Au": (79, 196.9665),
}

# Bound coherent neutron scattering lengths in Angstroms (1 fm = 1e-5 Angstroms)
# Values: NIST neutron scattering lengths (2018), https://www.nist.gov/ncnr/neutron-scattering-lengths-list
B_COH: Dict[str, float] = {
    "H": -3.7406e-5,
    "D":  6.6710e-5,
    "C":  6.6460e-5,
    "N":  9.3600e-5,
    "O":  5.8030e-5,
    "F":  5.6540e-5,   # NIST 2018
    "Al": 3.4490e-5,   # NIST 2018
    "P":  5.1300e-5,
    "S":  2.8470e-5,
    "Si": 4.1491e-5,
    "Ti":-3.3700e-5,  # natural Ti; negative b_coh (NIST)
    "Zn": 5.6800e-5,   # NIST 2018
    "Cr": 3.6350e-5,  # natural Cr (NIST)
    "Ag": 5.9220e-5,  # natural Ag (NIST)
    "In": 4.0650e-5,  # natural In (NIST)
    "Sn": 6.2250e-5,  # natural Sn (NIST)
    "Au": 7.6300e-5,
}


class EnergyConverter:
    """Utility class to convert between wavelength, energy, and frequency."""
    H_PLANCK_EV_S = 4.135667697e-15  # Planck constant in eV·s
    C_NM_S = 2.99792458e17          # Speed of light in nm/s
    HC_EV_NM = 1239.84193           # hc in eV·nm

    @classmethod
    def wl_to_energy(cls, wl_nm: float) -> float:
        """Convert wavelength (nm) to photon energy (eV)."""
        if wl_nm <= 0:
            raise ValueError(f"Input must be strictly positive, got {wl_nm}")
        return cls.HC_EV_NM / wl_nm

    @classmethod
    def energy_to_wl(cls, energy_ev: float) -> float:
        """Convert photon energy (eV) to wavelength (nm)."""
        if energy_ev <= 0:
            raise ValueError(f"Input must be strictly positive, got {energy_ev}")
        return cls.HC_EV_NM / energy_ev

    @classmethod
    def frequency_to_energy(cls, freq_hz: float) -> float:
        """Convert frequency (Hz) to photon energy (eV)."""
        return cls.H_PLANCK_EV_S * freq_hz

    @classmethod
    def energy_to_frequency(cls, energy_ev: float) -> float:
        """Convert photon energy (eV) to frequency (Hz)."""
        return energy_ev / cls.H_PLANCK_EV_S

    @classmethod
    def wl_to_frequency(cls, wl_nm: float) -> float:
        """Convert wavelength (nm) to frequency (Hz)."""
        if wl_nm <= 0:
            raise ValueError(f"Input must be strictly positive, got {wl_nm}")
        return cls.C_NM_S / wl_nm

    @classmethod
    def frequency_to_wl(cls, freq_hz: float) -> float:
        """Convert frequency (Hz) to wavelength (nm)."""
        if freq_hz <= 0:
            raise ValueError(f"Input must be strictly positive, got {freq_hz}")
        return cls.C_NM_S / freq_hz


def parse_formula(formula: str) -> Dict[str, int]:
    """Parse a chemical formula string into element counts."""
    clean = re.sub(r"^\((.+)\)[A-Za-z]?\d*$", r"\1", formula.strip())
    counts: Dict[str, int] = {}
    for elem, num_str in re.findall(r"([A-Z][a-z]?)(\d*)", clean):
        if not elem:
            continue
        counts[elem] = counts.get(elem, 0) + (int(num_str) if num_str else 1)
    return counts


def compute_xray_sld(
    formula_counts: Dict[str, int], 
    density_g_cm3: float, 
    mw_g_mol: float, 
    energy_ev: Optional[float] = None,
    f1_f2_lookup = None
) -> complex:
    """
    Compute complex energy-dependent X-ray SLD in Å⁻².
    """
    z_eff = 0.0
    for elem, count in formula_counts.items():
        if elem not in ATOMS:
            raise ValueError(f"Unknown element: {elem}")
        z = ATOMS[elem][0]
        
        # anomalous dispersion corrections
        f1, f2 = 0.0, 0.0
        if f1_f2_lookup and energy_ev is not None:
            f1, f2 = f1_f2_lookup(elem, energy_ev)
            
        z_eff += count * (z + f1 + 1j * f2)

    # Electron density: (density * NA * z_eff) / (mw * 1e24)
    rho_e = (density_g_cm3 * NA * z_eff) / (mw_g_mol * 1e24)
    sld = rho_e * R_E
    return sld


def compute_neutron_sld(
    formula_counts: Dict[str, int], 
    density_g_cm3: float, 
    mw_g_mol: float
) -> float:
    """
    Compute real Neutron SLD in Å⁻² based on isotopic composition.
    """
    b_total = 0.0
    for elem, count in formula_counts.items():
        if elem not in B_COH:
            raise ValueError(f"Neutron scattering length unknown for element {elem}")
        b_total += count * B_COH[elem]
        
    sld_n = (density_g_cm3 * NA * b_total) / (mw_g_mol * 1e24)
    return float(sld_n)
