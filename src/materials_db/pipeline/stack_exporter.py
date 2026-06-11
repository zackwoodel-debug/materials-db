"""Build a slab JSON v1 StackFile by querying materials.db.

Public API
----------
build_stack(layers, sample_id, user, proposal_id, db_path=None) -> StackFile

Each element of *layers* is a dict with keys:
  material        str   (required) – name as stored in DB, or a known alias
  thickness       float (Å)        – absent ⇒ structural sub-model omitted
  thickness_min   float (Å)        – optional bound
  thickness_max   float (Å)        – optional bound
  roughness       float (Å)        – optional
  roughness_min   float (Å)        – optional bound
  roughness_max   float (Å)        – optional bound
  substrate       bool             – True ⇒ role="substrate"

An air ambient layer is always prepended automatically.
If the substrate material is quartz / SiO2, qcm_substrate is populated.

CLI
---
python -m materials_db.pipeline.stack_exporter \\
    --sample "PS-on-Au" --layers "Polystyrene:1000,Gold:50" \\
    --substrate quartz --out data/stacks/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import date, timezone
from pathlib import Path
from typing import Optional

from materials_db.core.stack_schema import (
    BoundedValue,
    Layer,
    Molecular,
    Provenance,
    QcmSubstrate,
    Scattering,
    StackFile,
    Structural,
    Viscoelastic,
)

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB = _ROOT / "data" / "materials.db"

_CUKA_EV: float = 8047.8   # Cu-Kα photon energy (eV)
_WL_TARGET: float = 633.0  # Optical target wavelength (nm)

# Air ambient layer – values from spec
_AIR_LABEL = "Air"
_AIR_N = 1.0
_AIR_K = 0.0
_AIR_VISCOSITY = 1.81e-5   # Pa·s (dynamic viscosity at 20 °C)
_AIR_DENSITY = 1.2         # specification value (kg/m³ convention)

# α-quartz QCM acoustic impedance (Pa·s/m = kg m⁻² s⁻¹)
_QCM_IMPEDANCE = 8.8e6

# Lower-cased names that indicate a quartz / SiO2 QCM sensor substrate
_QCM_SUBSTRATES: frozenset[str] = frozenset(
    {"quartz", "sio2", "silica", "fused silica", "fused-silica"}
)

# User-supplied name → canonical DB name (lower-case keys)
_ALIASES: dict[str, str] = {
    "quartz": "SiO2",
    "fused silica": "SiO2",
    "fused-silica": "SiO2",
    "silica": "SiO2",
    "ps": "Polystyrene",
    "au": "Gold",
    "cr": "Chromium",
    "si": "Silicon",
    "tio2": "TiO2",
    "pdms": "PDMS",
    "pmma": "PMMA",
    "peg": "PEG",
    "h2o": "Water",
    "water": "Water",
}

# chemical_descriptors names to try for logP and TPSA (in preference order)
_LOGP_KEYS = ("logP", "MolLogP")
_TPSA_KEYS = ("TPSA", "tpsa")


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _open_ro(db_path: Path) -> sqlite3.Connection:
    """Open the DB read-only; row_factory → sqlite3.Row."""
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_name(conn: sqlite3.Connection, name: str) -> tuple[sqlite3.Row | None, str]:
    """Return (row, resolved_name).

    Tries exact match, then ALIASES lookup, then case-insensitive match.
    Logs a WARNING and returns (None, name) when not found.
    """
    def _query(n: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT id, formula, molecular_weight, density_g_cm3, "
            "       material_class, smiles "
            "FROM materials WHERE name = ?",
            (n,),
        ).fetchone()

    # 1. Exact match
    row = _query(name)
    if row is not None:
        return row, name

    # 2. Alias map
    alias = _ALIASES.get(name.lower())
    if alias:
        row = _query(alias)
        if row is not None:
            log.info("Resolved %r → %r via alias", name, alias)
            return row, alias

    # 3. Case-insensitive fallback
    row = conn.execute(
        "SELECT id, formula, molecular_weight, density_g_cm3, "
        "       material_class, smiles "
        "FROM materials WHERE LOWER(name) = LOWER(?)",
        (name,),
    ).fetchone()
    if row is not None:
        resolved = row["formula"] or name  # best effort; just use it
        log.info("Case-insensitive match: %r found in DB", name)
        return row, name

    log.warning("Material %r not found in materials.db — all DB fields will be null", name)
    return None, name


def _interp_nk(
    conn: sqlite3.Connection, material_id: int, label: str
) -> tuple[float | None, float | None]:
    """Linearly interpolate n and k at 633 nm from the two nearest rows.

    Uses the row at or below 633 nm as the lower bracket (so an exact 633 nm
    row is returned directly with interpolation factor t = 0).  Returns
    (None, None) and logs a WARNING when no optical data exists.
    """
    lo = conn.execute(
        "SELECT wavelength_nm, n, k FROM optical_nk "
        "WHERE material_id = ? AND wavelength_nm <= ? "
        "ORDER BY wavelength_nm DESC LIMIT 1",
        (material_id, _WL_TARGET),
    ).fetchone()

    hi = conn.execute(
        "SELECT wavelength_nm, n, k FROM optical_nk "
        "WHERE material_id = ? AND wavelength_nm > ? "
        "ORDER BY wavelength_nm ASC LIMIT 1",
        (material_id, _WL_TARGET),
    ).fetchone()

    if lo is None and hi is None:
        log.warning(
            "%r: no optical data in optical_nk — n_at_633nm and k_at_633nm set to null",
            label,
        )
        return None, None

    # Extrapolation (only one bracket available)
    if lo is None:
        log.warning("%r: no optical data at or below 633 nm; using nearest value above", label)
        return hi["n"], hi["k"]

    if hi is None:
        log.warning("%r: no optical data above 633 nm; using nearest value below", label)
        return lo["n"], lo["k"]

    # Exact hit (lo wavelength == target means t = 0)
    lo_wl, hi_wl = lo["wavelength_nm"], hi["wavelength_nm"]
    if lo_wl == _WL_TARGET:
        return lo["n"], lo["k"]

    t = (_WL_TARGET - lo_wl) / (hi_wl - lo_wl)
    n = lo["n"] + t * (hi["n"] - lo["n"])

    lo_k, hi_k = lo["k"], hi["k"]
    if lo_k is None or hi_k is None:
        if lo_k is not None or hi_k is not None:
            log.warning(
                "%r: k missing on one interpolation bracket at 633 nm — k set to null",
                label,
            )
        k: float | None = None
    else:
        k = lo_k + t * (hi_k - lo_k)

    return n, k


def _fetch_sld_cuka(
    conn: sqlite3.Connection, material_id: int, label: str
) -> tuple[float | None, float | None]:
    """Return (xray_sld, neutron_sld) at the Cu-Kα energy (8047.8 eV).

    Picks the row whose energy is closest to _CUKA_EV.
    """
    row = conn.execute(
        "SELECT sld_xray_real, sld_neutron_real FROM calculated_sld "
        "WHERE material_id = ? "
        "ORDER BY ABS(energy_ev - ?) LIMIT 1",
        (material_id, _CUKA_EV),
    ).fetchone()

    if row is None:
        log.warning(
            "%r: no SLD data in calculated_sld — neutron/x-ray SLDs set to null", label
        )
        return None, None

    return row["sld_xray_real"], row["sld_neutron_real"]


def _fetch_visco(
    conn: sqlite3.Connection, material_id: int
) -> sqlite3.Row | None:
    """Return the most representative viscoelasticity row (nearest 25 °C, lowest f).

    Returns None (with no warning) when the table has no rows for this material,
    since many materials have no viscoelastic entry.
    """
    return conn.execute(
        "SELECT storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s, "
        "       frequency_hz, temperature_C "
        "FROM viscoelasticity WHERE material_id = ? "
        "ORDER BY ABS(COALESCE(temperature_C, 25) - 25), frequency_hz LIMIT 1",
        (material_id,),
    ).fetchone()


def _fetch_descriptors(conn: sqlite3.Connection, material_id: int) -> dict[str, float]:
    """Return all chemical descriptor name→value pairs for this material."""
    rows = conn.execute(
        "SELECT descriptor_name, value FROM chemical_descriptors WHERE material_id = ?",
        (material_id,),
    ).fetchall()
    return {r["descriptor_name"]: r["value"] for r in rows}


def _clean_citation(doi: str | None, citation: str | None) -> str | None:
    """Prefer DOI; fall back to HTML-stripped, whitespace-normalised citation."""
    if doi:
        return f"doi:{doi}"
    if citation:
        stripped = re.sub(r"<[^>]+>", "", citation)
        normalised = " ".join(stripped.split())
        return normalised[:140] if len(normalised) > 140 else normalised
    return None


def _build_source_optical(conn: sqlite3.Connection, material_id: int) -> str | None:
    """Build a citation string from references_db for the material's optical data."""
    rows = conn.execute(
        "SELECT DISTINCT r.doi, r.citation_text "
        "FROM optical_nk o "
        "JOIN references_db r ON r.id = o.reference_id "
        "WHERE o.material_id = ? "
        "ORDER BY r.id",
        (material_id,),
    ).fetchall()

    if not rows:
        # Fall back to source_ref text in optical_nk itself
        src_row = conn.execute(
            "SELECT source_ref FROM optical_nk "
            "WHERE material_id = ? AND source_ref IS NOT NULL LIMIT 1",
            (material_id,),
        ).fetchone()
        if src_row:
            text = re.sub(r"<[^>]+>", "", src_row["source_ref"])
            text = " ".join(text.split())[:140]
            return text or None
        return None

    parts = [_clean_citation(r["doi"], r["citation_text"]) for r in rows]
    return "; ".join(p for p in parts if p) or None


# ── Sub-model builders ─────────────────────────────────────────────────────────

def _build_structural(d: dict) -> Structural | None:
    """Build Structural from layer dict keys thickness / roughness with optional bounds."""
    t_val = d.get("thickness")
    r_val = d.get("roughness")

    if t_val is None and r_val is None:
        return None

    thickness: BoundedValue | None = None
    if t_val is not None:
        thickness = BoundedValue(
            value=float(t_val),
            min=float(d["thickness_min"]) if d.get("thickness_min") is not None else None,
            max=float(d["thickness_max"]) if d.get("thickness_max") is not None else None,
        )

    roughness: BoundedValue | None = None
    if r_val is not None:
        roughness = BoundedValue(
            value=float(r_val),
            min=float(d["roughness_min"]) if d.get("roughness_min") is not None else None,
            max=float(d["roughness_max"]) if d.get("roughness_max") is not None else None,
        )

    return Structural(thickness=thickness, roughness=roughness)


def _kw(**kwargs: object) -> dict:
    """Return a dict with None values removed (used for model constructors)."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _air_ambient() -> Layer:
    """Return the pre-canned air ambient layer."""
    return Layer(
        label=_AIR_LABEL,
        material_type="ambient",
        role="ambient",
        molecular=Molecular(
            **_kw(
                formula="N₂/O₂",
                n_at_633nm=_AIR_N,
                k_at_633nm=_AIR_K,
            )
        ),
        scattering=Scattering(sld_real=0.0, sld_imag=0.0),
        viscoelastic=Viscoelastic(
            **_kw(viscosity=_AIR_VISCOSITY, density=_AIR_DENSITY)
        ),
    )


def _build_layer(
    conn: sqlite3.Connection,
    layer_dict: dict,
    is_substrate: bool = False,
) -> Layer:
    """Query materials.db and assemble one Layer from *layer_dict*."""
    name: str = layer_dict["material"]
    mat, resolved = _resolve_name(conn, name)

    if mat is None:
        # Material not in DB: return a skeleton with what we know from the dict
        if not is_substrate and layer_dict.get("thickness") is None:
            log.warning("%r: no thickness specified and material not in DB", name)
        return Layer(
            label=name,
            role="substrate" if is_substrate else None,
            structural=_build_structural(layer_dict),
        )

    material_id: int = mat["id"]
    label = resolved  # use the canonical name as the layer label

    # ── Optical constants at 633 nm ────────────────────────────────────────────
    n_633, k_633 = _interp_nk(conn, material_id, label)

    # ── SLD at Cu-Kα ──────────────────────────────────────────────────────────
    xray_sld, neutron_sld = _fetch_sld_cuka(conn, material_id, label)

    # ── Viscoelastic data ──────────────────────────────────────────────────────
    visco_row = _fetch_visco(conn, material_id)

    # ── Chemical descriptors ───────────────────────────────────────────────────
    desc = _fetch_descriptors(conn, material_id)

    logp: float | None = next(
        (desc[k] for k in _LOGP_KEYS if k in desc), None
    )
    tpsa: float | None = next(
        (desc[k] for k in _TPSA_KEYS if k in desc), None
    )

    # Log chemical descriptors and SMILES (schema has no dedicated fields for them)
    log.info(
        "%r  formula=%s  density=%s  n_633=%s  k_633=%s  "
        "xray_sld=%s  neutron_sld=%s  logP=%s  TPSA=%s  SMILES=%s",
        label,
        mat["formula"],
        mat["density_g_cm3"],
        n_633,
        k_633,
        xray_sld,
        neutron_sld,
        logp,
        tpsa,
        mat["smiles"],
    )

    if mat["density_g_cm3"] is None:
        log.warning("%r: density_g_cm3 not in DB — stored as null", label)

    # ── Build viscoelastic_notes string ───────────────────────────────────────
    # Combines measurement context with chemical descriptor summary (logP, TPSA)
    # since Molecular has no dedicated logP/TPSA fields.
    visco_notes_parts: list[str] = []
    if visco_row is not None:
        if visco_row["storage_modulus_pa"] is not None:
            visco_notes_parts.append(f"G'={visco_row['storage_modulus_pa']:.2e} Pa")
        if visco_row["loss_modulus_pa"] is not None:
            visco_notes_parts.append(f"G''={visco_row['loss_modulus_pa']:.2e} Pa")
        if visco_row["frequency_hz"] is not None:
            visco_notes_parts.append(f"@{visco_row['frequency_hz']} Hz")
        if visco_row["temperature_C"] is not None:
            visco_notes_parts.append(f"{visco_row['temperature_C']} °C")
    if logp is not None:
        visco_notes_parts.append(f"logP={logp}")
    if tpsa is not None:
        visco_notes_parts.append(f"TPSA={tpsa}")
    visco_notes: str | None = "; ".join(visco_notes_parts) or None

    # ── Source optical ─────────────────────────────────────────────────────────
    source_optical = _build_source_optical(conn, material_id)

    # ── Molecular ─────────────────────────────────────────────────────────────
    mol_kw = _kw(
        formula=mat["formula"],
        mw_repeat_g_mol=mat["molecular_weight"],
        density_g_cm3=mat["density_g_cm3"],
        neutron_sld_A2=neutron_sld,
        xray_sld_A2_CuKa=xray_sld,
        n_at_633nm=n_633,
        k_at_633nm=k_633,
        viscoelastic_notes=visco_notes,
        source_optical=source_optical,
    )
    molecular = Molecular(**mol_kw) if mol_kw else None

    # ── Viscoelastic sub-model ─────────────────────────────────────────────────
    visco_kw: dict = {}
    if visco_row is not None:
        visco_kw = _kw(
            modulus_storage=visco_row["storage_modulus_pa"],
            modulus_loss=visco_row["loss_modulus_pa"],
            viscosity=visco_row["viscosity_mpa_s"],
            density=mat["density_g_cm3"],
        )
    viscoelastic = Viscoelastic(**visco_kw) if visco_kw else None

    # ── Scattering sub-model ──────────────────────────────────────────────────
    # Use x-ray SLD as the primary sld_real for XRR / SPR context.
    scattering = Scattering(**_kw(sld_real=xray_sld)) if xray_sld is not None else None

    # ── QCM substrate (quartz / SiO2 only) ────────────────────────────────────
    qcm_substrate: QcmSubstrate | None = None
    if is_substrate and name.lower() in _QCM_SUBSTRATES:
        qcm_substrate = QcmSubstrate(
            **_kw(density=mat["density_g_cm3"], impedance=_QCM_IMPEDANCE)
        )

    # Warn if a film layer has no thickness
    if not is_substrate and layer_dict.get("thickness") is None:
        log.warning("%r: no thickness supplied in layer dict", label)

    return Layer(
        **_kw(
            label=label,
            material_type=mat["material_class"],
            role="substrate" if is_substrate else None,
            molecular=molecular,
            structural=_build_structural(layer_dict),
            scattering=scattering,
            viscoelastic=viscoelastic,
            qcm_substrate=qcm_substrate,
        )
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def build_stack(
    layers: list[dict],
    sample_id: str,
    user: str,
    proposal_id: str,
    db_path: Path | None = None,
) -> StackFile:
    """Build a StackFile from a list of layer dicts.

    Parameters
    ----------
    layers:
        Each dict must have a ``"material"`` key; thickness and bounds are
        optional.  Set ``"substrate": True`` on the last dict to mark it as
        the semi-infinite substrate.
    sample_id:
        Human-readable sample identifier (becomes ``StackFile.sample_id``).
    user:
        Operator name stored in the provenance block.
    proposal_id:
        Proposal / experiment reference stored in provenance notes.
    db_path:
        Override the default ``data/materials.db`` path.

    Returns
    -------
    StackFile
        Fully populated Pydantic model.  Missing DB values are stored as
        ``None``; no numbers are invented.
    """
    db = Path(db_path) if db_path is not None else _DEFAULT_DB
    if not db.exists():
        raise FileNotFoundError(f"materials.db not found: {db}")

    conn = _open_ro(db)
    try:
        built: list[Layer] = [_air_ambient()]

        for layer_dict in layers:
            is_sub = bool(layer_dict.get("substrate", False))
            built.append(_build_layer(conn, layer_dict, is_substrate=is_sub))

        primary = layers[0]["material"] if layers else "unknown"

        provenance = Provenance(
            **_kw(
                operator=user,
                date=date.today().isoformat(),
                notes=f"proposal_id={proposal_id}",
            )
        )

        return StackFile(
            stack_id=str(uuid.uuid4()),
            sample_id=sample_id,
            provenance=provenance,
            material=primary,
            n_layers=len(built),
            stack=built,
        )
    finally:
        conn.close()


# ── Atomic file writer ─────────────────────────────────────────────────────────

def _write_atomic(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via a sibling .tmp file."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)  # POSIX rename is atomic; also works on Windows Python 3.3+


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_layers_arg(spec: str) -> list[dict]:
    """Parse ``"Material:thickness[,Material:thickness,...]"`` into layer dicts.

    Thickness is optional; omitting it produces a layer with no structural data.
    Example: ``"Polystyrene:1000,Gold:50"``
    """
    layers: list[dict] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            mat, thick_str = token.split(":", 1)
            layers.append({"material": mat.strip(), "thickness": float(thick_str)})
        else:
            layers.append({"material": token})
    return layers


def _sanitise_filename(s: str) -> str:
    """Replace whitespace and filesystem-unsafe chars with underscores."""
    return re.sub(r"[^\w\-.]", "_", s).strip("_") or "stack"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m materials_db.pipeline.stack_exporter",
        description="Export a slab JSON v1 stack file from materials.db",
    )
    parser.add_argument(
        "--sample", required=True, metavar="SAMPLE_ID",
        help="Sample identifier, e.g. 'PS-on-Au'",
    )
    parser.add_argument(
        "--layers", required=True, metavar="MAT:THICK[,...]",
        help="Comma-separated Material:thickness(Å) list, e.g. 'Polystyrene:1000,Gold:50'",
    )
    parser.add_argument(
        "--substrate", metavar="MATERIAL",
        help="Substrate material name (appended with role=substrate), e.g. 'quartz'",
    )
    parser.add_argument(
        "--out", default="data/stacks/", metavar="DIR",
        help="Output directory (default: data/stacks/)",
    )
    parser.add_argument(
        "--user", default="unknown", metavar="NAME",
        help="Operator name for provenance",
    )
    parser.add_argument(
        "--proposal", default="", metavar="ID",
        help="Proposal / experiment ID for provenance",
    )
    parser.add_argument(
        "--db", default=None, metavar="PATH",
        help="Override path to materials.db",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    film_layers = _parse_layers_arg(args.layers)

    if args.substrate:
        film_layers.append({"material": args.substrate, "substrate": True})

    db_path = Path(args.db) if args.db else None

    stack = build_stack(
        layers=film_layers,
        sample_id=args.sample,
        user=args.user,
        proposal_id=args.proposal,
        db_path=db_path,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    safe_id = _sanitise_filename(args.sample)
    filename = f"{today}_{safe_id}_slab_v1.json"
    out_path = out_dir / filename

    payload = stack.model_dump(mode="json", exclude_none=True)
    _write_atomic(out_path, json.dumps(payload, indent=2))

    log.info("Wrote %d-layer stack → %s", stack.n_layers, out_path)

    # Surface any physics violations immediately
    issues = stack.validate_physics()
    if issues:
        log.warning("%d physics violation(s) in exported stack:", len(issues))
        for v in issues:
            log.warning("  %s", v)
    else:
        log.info("Physics check: all constraints satisfied")


if __name__ == "__main__":
    main()
