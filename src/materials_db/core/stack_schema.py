"""Pydantic v2 models for the slab JSON v1 stack file format.

Top-level structure
-------------------
StackFile
  stack_id, sample_id, provenance, material, n_layers
  stack: list[Layer]

Each Layer
----------
  label, material_type, role?
  molecular  : Molecular
  structural : Structural  (thickness/roughness as BoundedValue)
  optical    : Optical
  scattering : Scattering
  viscoelastic : Viscoelastic
  qcm_substrate : QcmSubstrate  (substrate role only)

role is either "ambient", "substrate", or absent (film layer).
"""

import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

log = logging.getLogger(__name__)

# Material types for which n < 1.0 is physically expected at visible wavelengths.
_METAL_TYPES: frozenset[str] = frozenset(
    {"metal", "metallic", "conductor", "noble_metal"}
)


# ── Leaf models ────────────────────────────────────────────────────────────────

class BoundedValue(BaseModel):
    """Scalar with optional lower / upper confidence bounds.

    Validator: when both *min* and *max* are present, enforces min <= value <= max.
    """

    value: float
    min: Optional[float] = None
    max: Optional[float] = None

    @model_validator(mode="after")
    def _check_bounds(self) -> "BoundedValue":
        if self.min is not None and self.max is not None:
            if not (self.min <= self.value <= self.max):
                raise ValueError(
                    f"value {self.value!r} is outside bounds "
                    f"[{self.min!r}, {self.max!r}]"
                )
        return self


class Provenance(BaseModel):
    """Flexible provenance block.

    Declared fields cover common cases; arbitrary extra keys are stored and
    faithfully round-tripped via model_dump(exclude_unset=True).
    """

    model_config = ConfigDict(extra="allow")

    source: Optional[str] = None
    doi: Optional[str] = None
    date: Optional[str] = None
    operator: Optional[str] = None
    notes: Optional[str] = None


class Molecular(BaseModel):
    """Molecular identity and pre-computed material properties for one layer."""

    formula: Optional[str] = None
    mw_repeat_g_mol: Optional[float] = None
    density_g_cm3: Optional[float] = None
    neutron_sld_A2: Optional[float] = None
    xray_sld_A2_CuKa: Optional[float] = None
    n_at_633nm: Optional[float] = None
    k_at_633nm: Optional[float] = None
    viscoelastic_notes: Optional[str] = None
    source_optical: Optional[str] = None


class Structural(BaseModel):
    """Physical dimensions with fitted / prior uncertainty bounds."""

    thickness: Optional[BoundedValue] = None
    roughness: Optional[BoundedValue] = None


class Optical(BaseModel):
    """Optical dispersion model label and its parameter dict."""

    model: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class Scattering(BaseModel):
    """Complex scattering length density (SLD) in Å⁻²."""

    sld_real: Optional[float] = None
    sld_imag: Optional[float] = None


class Viscoelastic(BaseModel):
    """Bulk viscoelastic and rheological properties."""

    modulus_storage: Optional[float] = None
    modulus_loss: Optional[float] = None
    viscosity: Optional[float] = None
    density: Optional[float] = None


class QcmSubstrate(BaseModel):
    """QCM substrate constants required by the Sauerbrey / Voigt acoustic model."""

    density: Optional[float] = None
    impedance: Optional[float] = None


# ── Layer ──────────────────────────────────────────────────────────────────────

class Layer(BaseModel):
    """One layer in the stack.

    *role* is enforced by the ``Literal`` annotation:
    - ``"ambient"``   – semi-infinite superstrate (no physical thickness)
    - ``"substrate"`` – semi-infinite substrate  (no physical thickness)
    - absent / ``None`` – film layer with a physical thickness
    """

    label: str
    material_type: Optional[str] = None
    role: Optional[Literal["ambient", "substrate"]] = None
    molecular: Optional[Molecular] = None
    structural: Optional[Structural] = None
    optical: Optional[Optical] = None
    scattering: Optional[Scattering] = None
    viscoelastic: Optional[Viscoelastic] = None
    qcm_substrate: Optional[QcmSubstrate] = None


# ── StackFile ──────────────────────────────────────────────────────────────────

class StackFile(BaseModel):
    """Root model for a slab JSON v1 stack file."""

    stack_id: str
    sample_id: str
    provenance: Optional[Provenance] = None
    material: str
    n_layers: int
    stack: list[Layer]

    # ── Physics validation ─────────────────────────────────────────────────────

    def validate_physics(self) -> list[str]:
        """Check physical self-consistency of all layers.

        Rules
        -----
        - ``n_at_633nm >= 1.0`` for non-metal layers (Kramers–Kronig causality
          for passive media; metals are excluded via ``material_type``).
        - ``k_at_633nm >= 0.0`` for all layers (no passive optical gain).
        - ``molecular.density_g_cm3 > 0.0`` where present.
        - ``viscoelastic.density > 0.0`` where present.
        - ``structural.thickness.value > 0.0`` for film layers (role absent).

        Returns
        -------
        list[str]
            Human-readable violation descriptions.  An empty list means all
            constraints pass.  Each violation is also emitted as a WARNING log
            entry so callers need not inspect the list to surface issues.
        """
        violations: list[str] = []

        for layer in self.stack:
            loc = f"layer '{layer.label}'"
            mol = layer.molecular

            if mol is not None:
                is_metal = (
                    layer.material_type is not None
                    and layer.material_type.lower() in _METAL_TYPES
                )

                if mol.n_at_633nm is not None and not is_metal:
                    if mol.n_at_633nm < 1.0:
                        msg = (
                            f"{loc}: n_at_633nm={mol.n_at_633nm!r} < 1.0 "
                            f"(material_type={layer.material_type!r} is not metallic)"
                        )
                        violations.append(msg)
                        log.warning("Physics violation — %s", msg)

                if mol.k_at_633nm is not None and mol.k_at_633nm < 0.0:
                    msg = f"{loc}: k_at_633nm={mol.k_at_633nm!r} < 0"
                    violations.append(msg)
                    log.warning("Physics violation — %s", msg)

                if mol.density_g_cm3 is not None and mol.density_g_cm3 <= 0.0:
                    msg = f"{loc}: density_g_cm3={mol.density_g_cm3!r} <= 0"
                    violations.append(msg)
                    log.warning("Physics violation — %s", msg)

            if (
                layer.viscoelastic is not None
                and layer.viscoelastic.density is not None
                and layer.viscoelastic.density <= 0.0
            ):
                msg = (
                    f"{loc}: viscoelastic.density="
                    f"{layer.viscoelastic.density!r} <= 0"
                )
                violations.append(msg)
                log.warning("Physics violation — %s", msg)

            # Thickness is only physically meaningful for film layers.
            is_film = layer.role is None
            if (
                is_film
                and layer.structural is not None
                and layer.structural.thickness is not None
                and layer.structural.thickness.value <= 0.0
            ):
                msg = (
                    f"{loc}: structural.thickness.value="
                    f"{layer.structural.thickness.value!r} <= 0"
                )
                violations.append(msg)
                log.warning("Physics violation — %s", msg)

        return violations


# ── Round-trip helper ──────────────────────────────────────────────────────────

def _round_trip_check(path: Path) -> None:
    """Assert JSON → StackFile → model_dump(exclude_unset=True) == original dict.

    ``exclude_unset=True`` is the correct mode here: fields absent in the source
    JSON stay absent in the dump, while intentional nulls (explicitly written as
    ``null``) and arbitrary extra provenance keys are faithfully reproduced.
    """
    raw: dict = json.loads(path.read_text(encoding="utf-8"))
    model = StackFile.model_validate(raw)
    dumped: dict = model.model_dump(mode="json", exclude_unset=True)

    if dumped != raw:
        diff_keys = {k for k in raw if raw.get(k) != dumped.get(k)}
        raise AssertionError(
            f"Round-trip mismatch for {path.name!r}; differing top-level keys: "
            f"{diff_keys or '(nested)'}\n"
            f"original : {json.dumps(raw,    indent=2)}\n"
            f"round-trip: {json.dumps(dumped, indent=2)}"
        )

    log.info("Round-trip OK: %s", path.name)


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    _stacks_dir = Path(__file__).resolve().parents[3] / "data" / "stacks"

    if not _stacks_dir.exists():
        log.warning("data/stacks/ not found — no round-trip tests to run")
    else:
        _files = sorted(_stacks_dir.glob("*.json"))
        if not _files:
            log.warning("data/stacks/ is empty — no round-trip tests to run")

        for _p in _files:
            _round_trip_check(_p)
            _sf = StackFile.model_validate(json.loads(_p.read_text(encoding="utf-8")))
            _issues = _sf.validate_physics()
            if _issues:
                for _v in _issues:
                    log.warning("  PHYS: %s", _v)
            else:
                log.info("  physics OK: %s (%d layers)", _p.name, len(_sf.stack))
