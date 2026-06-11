"""
Apples-to-apples validation and normalization layer for raw CDE extraction records.

Enforces:
  1. Frequency/regime segregation — tags measurement_regime; refuses to merge regimes.
  2. Structural/phase isolation — appends phase tag; thin-film values never silently
     merge with bulk.
  3. Unit unification — all wavelengths → nm, frequencies → Hz, temperatures → °C,
     viscosities → Pa·s (÷1000 from mPa·s).

Returns NormalizedRecord instances ready for SQL UPSERT.
No values are invented; if source text does not declare a field it stays None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── measurement-regime thresholds (Hz) ───────────────────────────────────────
# These boundaries define the regime tags used in the DB column measurement_regime.
_REGIME_BANDS = [
    (0.0,       1e3,    "static"),        # DC / quasi-static
    (1e3,       1e7,    "low_frequency"), # kHz range
    (1e7,       3e9,    "RF"),            # MHz → low GHz
    (3e9,       3e12,   "microwave"),     # GHz
    (3e12,      None,   "optical"),       # THz and above
]

# Optical wavelength → ~THz and above; flag via wavelength instead of frequency
_OPTICAL_WL_THRESHOLD_NM = 1e6  # anything with a wavelength tag is optical regime


def classify_regime(
    frequency_hz: Optional[float],
    wavelength_nm: Optional[float],
) -> Optional[str]:
    """Return the measurement regime string, or None if neither freq nor wl given."""
    if wavelength_nm is not None:
        return "optical"
    if frequency_hz is None:
        return None
    for lo, hi, label in _REGIME_BANDS:
        if hi is None or lo <= frequency_hz < hi:
            return label
    return None


# ── unit conversion helpers ───────────────────────────────────────────────────

_WL_PATTERNS = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*nm",  re.I), 1.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[uµ]m", re.I), 1e3),
    (re.compile(r"(\d+(?:\.\d+)?)\s*mm",  re.I), 1e6),
    (re.compile(r"(\d+(?:\.\d+)?)\s*cm",  re.I), 1e7),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[aA]",  re.I), 0.1),   # Ångström
]

_FREQ_PATTERNS = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*[tT][hH][zZ]"), 1e12),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[gG][hH][zZ]"), 1e9),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[mM][hH][zZ]"), 1e6),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[kK][hH][zZ]"), 1e3),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[hH][zZ]"),     1.0),
]

_TEMP_PATTERNS = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*°?[Cc](?!\w)"), "C"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[Kk](?!\w)"),   "K"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*°?[Ff](?!\w)"), "F"),
]


def parse_wavelength_nm(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    for pat, factor in _WL_PATTERNS:
        m = pat.search(raw)
        if m:
            return float(m.group(1)) * factor
    # bare number: assume nm
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return None


def parse_frequency_hz(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    for pat, factor in _FREQ_PATTERNS:
        m = pat.search(raw)
        if m:
            return float(m.group(1)) * factor
    return None


def parse_temperature_c(raw: Optional[str]) -> Optional[float]:
    """Convert temperature string to °C.  Returns None if unparseable."""
    if not raw:
        return None
    for pat, unit in _TEMP_PATTERNS:
        m = pat.search(raw)
        if m:
            v = float(m.group(1))
            if unit == "C":
                return v
            if unit == "K":
                return v - 273.15
            if unit == "F":
                return (v - 32.0) * 5.0 / 9.0
    return None


def convert_viscosity_to_pas(value_mpa_s: float) -> float:
    """1 mPa·s = 0.001 Pa·s."""
    return value_mpa_s / 1000.0


# ── phase extraction ──────────────────────────────────────────────────────────

from scripts.build_extractors import PHASE_KEYWORDS  # noqa: E402


def extract_phase(phase_raw: Optional[str], sentence: Optional[str] = None) -> Optional[str]:
    """
    Return a canonical phase tag or None.
    Priority: explicit field from CDE > keyword scan of originating sentence.
    """
    sources = [s for s in (phase_raw, sentence) if s]
    for text in sources:
        lower = text.lower()
        for canonical, variants in PHASE_KEYWORDS.items():
            if any(v in lower for v in variants):
                return canonical
    return None


# ── n vs. ε_r consistency guard (Maxwell relation for optical regime) ─────────

def maxwell_consistent(n: float, k: float, eps_real: float, tol: float = 0.05) -> bool:
    """eps_real ≈ n² - k² at optical frequencies within relative tolerance."""
    expected = n * n - k * k
    if abs(expected) < 1e-9:
        return True
    return abs(eps_real - expected) / abs(expected) <= tol


# ── value-range guards per property and regime ───────────────────────────────

_RANGE_GUARDS = {
    # (property_type, regime)  ->  (lo, hi)
    ("n",                  "optical"):       (0.9,  6.0),
    ("n",                  None):            (0.9,  6.0),
    ("dielectric_constant","static"):        (1.0,  5000.0),
    ("dielectric_constant","low_frequency"): (1.0,  5000.0),
    ("dielectric_constant","RF"):            (1.0,  1000.0),
    ("dielectric_constant","microwave"):     (1.0,  1000.0),
    ("dielectric_constant","optical"):       (-200.0, 50.0),  # metals can be negative
    ("dielectric_constant",None):            (-200.0, 5000.0),
}


def value_in_range(
    prop_type: str, value: float, regime: Optional[str]
) -> bool:
    key = (prop_type, regime)
    bounds = _RANGE_GUARDS.get(key) or _RANGE_GUARDS.get((prop_type, None))
    if bounds is None:
        return True
    lo, hi = bounds
    return lo <= value <= hi


# ── normalized record ─────────────────────────────────────────────────────────

@dataclass
class NormalizedRecord:
    """
    Fully validated, unit-unified record ready for DB insertion.
    Every field that could not be determined from source text is explicitly None.
    """
    material_name:      str
    property_type:      str               # "n" | "dielectric_constant"
    value:              float
    wavelength_nm:      Optional[float]   = None
    frequency_hz:       Optional[float]   = None
    temperature_c:      Optional[float]   = None
    measurement_regime: Optional[str]     = None
    phase:              Optional[str]     = None
    source_label:       Optional[str]     = None
    sentence:           Optional[str]     = None
    rejection_reason:   Optional[str]     = None  # non-None → record rejected
    flags:              list              = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.rejection_reason is None


# ── main normalization function ───────────────────────────────────────────────

def normalize_record(raw) -> NormalizedRecord:
    """
    Accept a RawExtractionRecord (from build_extractors.py) and return a
    NormalizedRecord.  Sets rejection_reason if physics rules are violated.
    Never invents field values: missing source fields stay None.
    """
    from scripts.build_extractors import RawExtractionRecord  # noqa: F401

    wl_nm   = parse_wavelength_nm(raw.wavelength_str)
    freq_hz = parse_frequency_hz(raw.frequency_str)
    temp_c  = parse_temperature_c(raw.temperature_str)
    regime  = classify_regime(freq_hz, wl_nm)
    phase   = extract_phase(raw.phase_raw, raw.sentence)

    flags = []
    rejection = None

    # Rule 1: value within physics range for this regime
    if not value_in_range(raw.property_type, raw.raw_value, regime):
        rejection = (
            f"value {raw.raw_value} outside allowed range for "
            f"{raw.property_type} / regime={regime}"
        )

    # Rule 2: never accept n < 1 for non-metallic / non-optical materials
    if raw.property_type == "n" and raw.raw_value < 1.0 and regime not in ("optical", None):
        rejection = rejection or f"n={raw.raw_value} < 1.0 but regime is {regime}"

    # Rule 3: dielectric_constant < 1 at static/low-frequency is suspicious
    if (
        raw.property_type == "dielectric_constant"
        and raw.raw_value < 1.0
        and regime in ("static", "low_frequency", None)
    ):
        flags.append(f"dielectric_constant={raw.raw_value} < 1.0 in {regime} regime — review")

    # Rule 4: flag thin-film extractions explicitly so they never silently
    #          merge with bulk rows in the DB
    if phase == "thin film" and regime in ("static", "low_frequency"):
        flags.append("thin_film+low_freq: verify this is not a bulk constant")

    return NormalizedRecord(
        material_name=raw.material_name,
        property_type=raw.property_type,
        value=raw.raw_value,
        wavelength_nm=wl_nm,
        frequency_hz=freq_hz,
        temperature_c=temp_c,
        measurement_regime=regime,
        phase=phase,
        source_label=raw.source_label,
        sentence=raw.sentence,
        rejection_reason=rejection,
        flags=flags,
    )


def normalize_records(raws) -> list[NormalizedRecord]:
    """Normalize a list of RawExtractionRecord objects."""
    return [normalize_record(r) for r in raws]


# ── smoke-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scripts.build_extractors import RawExtractionRecord

    samples = [
        RawExtractionRecord("SiO2",  "n",                 1.46,  wavelength_str="633 nm",
                            temperature_str="25 C", phase_raw="thin film"),
        RawExtractionRecord("TiO2",  "dielectric_constant", 86.0, frequency_str="1 kHz",
                            temperature_str="298 K"),
        RawExtractionRecord("Water", "dielectric_constant", 78.4, temperature_str="25°C"),
        RawExtractionRecord("Gold",  "dielectric_constant", -24.0, wavelength_str="633 nm"),
        # bad value → should be rejected
        RawExtractionRecord("PMMA",  "n", 99.0),
    ]

    for nr in normalize_records(samples):
        status = "REJECTED" if not nr.is_valid else "OK"
        print(
            f"[{status:8s}] {nr.material_name:12s} {nr.property_type:22s} "
            f"val={nr.value}  wl={nr.wavelength_nm}  freq={nr.frequency_hz}  "
            f"T={nr.temperature_c}  regime={nr.measurement_regime}  phase={nr.phase}"
        )
        if not nr.is_valid:
            print(f"            reason: {nr.rejection_reason}")
        if nr.flags:
            print(f"            flags:  {nr.flags}")
