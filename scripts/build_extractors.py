"""
Custom ChemDataExtractor models for refractive index (n) and dielectric constant (eps_r).

Both are dimensionless quantities.  Each model captures:
  - canonical material name / formula (via Compound)
  - numeric value with range guard
  - contextual wavelength_nm or frequency_hz
  - contextual temperature_c (defaults to 25.0 when unspecified)
  - structural phase metadata (thin_film, bulk, amorphous, single_crystal)

Requires CDE2.  On Python ≥ 3.13 the `dawg` C extension is unavailable;
the module installs the dawg-python shim automatically at import time.
"""

import sys

# Python 3.13: dawg C extension cannot build; shim with pure-python fallback.
try:
    import dawg  # noqa: F401
except ImportError:
    import dawg_python as _dp
    sys.modules["dawg"] = _dp

from chemdataextractor.model.model import Compound, DimensionlessModel
from chemdataextractor.model import StringType, FloatType, ModelType, ListType
from chemdataextractor.parse.elements import (
    W, R, I, Optional, OneOrMore, Any, Group
)
from chemdataextractor.parse.actions import join
from chemdataextractor.parse.template import (
    QuantityModelTemplateParser,
    MultiQuantityModelTemplateParser,
)
from chemdataextractor.model.base import BaseModel

# ── specifier parse expressions ──────────────────────────────────────────────

# Refractive index triggers: "refractive index", "n =", "index of refraction", "n_d", "RI"
_N_SPECIFIER = (
    (I("refractive") + I("index"))
    | (I("index") + I("of") + I("refraction"))
    | I("RI")
    | R(r"^n_?[dDeEFgG]?$")           # n, nD, nE, n_d …
).add_action(join)

# Dielectric constant triggers
_EPS_SPECIFIER = (
    (Optional(I("static") | I("optical") | I("relative"))
     + (
         (I("dielectric") + (I("constant") | I("permittivity")))
         | (I("permittivity"))
         | (I("relative") + I("permittivity"))
     ))
    | R(r"^[eεɛ]r?[_′\']?$")          # ε, εr, ε', er
    | (R(r"^[eεɛ]$") + Optional(R(r"^[_r′]$")))
).add_action(join)


# ── value guard: reject out-of-range extractions before they reach the DB ────

def _guard_n(value: float) -> bool:
    """Refractive index must be in [0.9, 6.0]; absorbing media can be < 1."""
    return 0.9 <= value <= 6.0


def _guard_eps(value: float) -> bool:
    """Dielectric constant: metals have negative ε at optical freq (Drude)."""
    return -100.0 <= value <= 5000.0


# ── contextual wavelength / frequency parser ──────────────────────────────────

# Matches patterns like "633 nm", "1550 nm", "1 kHz", "1 MHz", "10 GHz"
_WL_PATTERN   = R(r"^\d+(\.\d+)?$") + R(r"^[nNuUmM]?m$")
_FREQ_PATTERN = R(r"^\d+(\.\d+)?$") + R(r"^[kKmMgGtT]?[hH][zZ]$")


# ── structural phase vocabulary ───────────────────────────────────────────────

PHASE_KEYWORDS = {
    "thin film":      ["thin film", "thin-film", "deposited film"],
    "bulk":           ["bulk", "bulk crystal", "bulk material"],
    "amorphous":      ["amorphous", "glassy", "non-crystalline"],
    "single crystal": ["single crystal", "single-crystal", "monocrystal"],
    "polycrystalline":["polycrystalline", "poly-crystalline", "ceramic"],
    "solution":       ["solution", "dissolved", "in solution"],
    "melt":           ["melt", "molten", "liquid phase"],
}


# ── model definitions ─────────────────────────────────────────────────────────

class RefractiveIndexModel(DimensionlessModel):
    """
    Extracts the real part of the refractive index (n) from text.

    Fields
    ------
    value           : extracted numeric value(s); validated to [0.9, 6.0]
    compound        : linked Compound record (name / formula)
    wavelength_nm   : measurement wavelength in nm (contextual, may be None)
    frequency_hz    : measurement frequency in Hz (contextual, may be None)
    temperature_c   : measurement temperature in °C (contextual; None → 25.0 applied downstream)
    phase           : structural/phase descriptor string (contextual, may be None)
    dataset_label   : free-text provenance label (contextual)
    """

    specifier = StringType(
        parse_expression=_N_SPECIFIER,
        required=True,
        updatable=True,
    )
    compound        = ModelType(Compound, contextual=True, required=True)
    wavelength_nm   = StringType(contextual=True)
    frequency_hz    = StringType(contextual=True)
    temperature_c   = StringType(contextual=True)
    phase           = StringType(contextual=True)
    dataset_label   = StringType(contextual=True)

    parsers = [
        MultiQuantityModelTemplateParser(),
        QuantityModelTemplateParser(),
    ]

    # [1.0, 5.0] for typical dielectrics; metals below plasma edge can have n<1
    # so the guard is intentionally slightly wider to avoid silent loss of valid records
    value_range = (1.0, 5.0)


class DielectricConstantModel(DimensionlessModel):
    """
    Extracts the real part of the relative permittivity / dielectric constant (ε_r).

    Fields
    ------
    value               : extracted numeric value(s)
    compound            : linked Compound record
    wavelength_nm       : measurement wavelength in nm (contextual)
    frequency_hz        : measurement frequency in Hz (contextual)
    temperature_c       : measurement temperature in °C (contextual)
    measurement_regime  : [static, low_frequency, RF, microwave, optical] — tagged downstream
    phase               : structural descriptor (contextual)
    dataset_label       : provenance label (contextual)
    """

    specifier = StringType(
        parse_expression=_EPS_SPECIFIER,
        required=True,
        updatable=True,
    )
    compound            = ModelType(Compound, contextual=True, required=True)
    wavelength_nm       = StringType(contextual=True)
    frequency_hz        = StringType(contextual=True)
    temperature_c       = StringType(contextual=True)
    measurement_regime  = StringType(contextual=True)
    phase               = StringType(contextual=True)
    dataset_label       = StringType(contextual=True)

    parsers = [
        MultiQuantityModelTemplateParser(),
        QuantityModelTemplateParser(),
    ]

    value_range = (-100.0, 5000.0)


# ── raw-record dataclass (used by normalize_extracted.py) ────────────────────

from dataclasses import dataclass, field
from typing import Optional as Opt, List


@dataclass
class RawExtractionRecord:
    """
    Intermediate record between CDE extraction output and DB ingestion.
    All optional fields are strictly None when not found in source text.
    """
    material_name:      str
    property_type:      str            # "n" | "dielectric_constant"
    raw_value:          float
    raw_units:          Opt[str]       = None
    wavelength_str:     Opt[str]       = None   # as found in text, e.g. "633 nm"
    frequency_str:      Opt[str]       = None   # as found in text, e.g. "1 kHz"
    temperature_str:    Opt[str]       = None   # as found in text, e.g. "25 °C"
    phase_raw:          Opt[str]       = None   # raw phase keyword found
    source_label:       Opt[str]       = None   # file / DOI / dataset label
    sentence:           Opt[str]       = None   # originating sentence for audit


# ── helper: extract records from a CDE Document ──────────────────────────────

def extract_from_document(doc) -> List[RawExtractionRecord]:
    """
    Run both custom models over a CDE Document and return RawExtractionRecord list.
    Values outside their physical range are dropped here (not stored).
    """
    records: List[RawExtractionRecord] = []

    model_map = [
        (RefractiveIndexModel,    "n"),
        (DielectricConstantModel, "dielectric_constant"),
    ]

    for model_cls, prop_type in model_map:
        lo, hi = model_cls.value_range
        for rec in doc.models_dict.get(model_cls.__name__, []):
            vals = rec.value
            if vals is None:
                continue
            for v in (vals if isinstance(vals, list) else [vals]):
                if not (lo <= v <= hi):
                    continue  # out-of-physics range — discard silently
                cname = None
                if rec.compound and rec.compound.names:
                    cname = rec.compound.names[0]
                records.append(RawExtractionRecord(
                    material_name=cname or "UNKNOWN",
                    property_type=prop_type,
                    raw_value=v,
                    raw_units=getattr(rec, "raw_units", None),
                    wavelength_str=getattr(rec, "wavelength_nm", None),
                    frequency_str=getattr(rec, "frequency_hz", None),
                    temperature_str=getattr(rec, "temperature_c", None),
                    phase_raw=getattr(rec, "phase", None),
                    source_label=getattr(rec, "dataset_label", None),
                ))

    return records


# ── quick smoke-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, dawg_python as _dp; sys.modules.setdefault("dawg", _dp)
    from chemdataextractor import Document

    sample = (
        "The refractive index of SiO2 thin film was measured to be 1.46 at 633 nm and 25 °C. "
        "For bulk TiO2, the dielectric constant ε is 86 at 1 kHz."
    )
    doc = Document(sample, models=[RefractiveIndexModel, DielectricConstantModel])
    recs = extract_from_document(doc)
    print(f"Extracted {len(recs)} record(s):")
    for r in recs:
        print(f"  {r.property_type:22s}  {r.raw_value}  mat={r.material_name!r}  "
              f"wl={r.wavelength_str}  freq={r.frequency_str}  "
              f"T={r.temperature_str}  phase={r.phase_raw}")
