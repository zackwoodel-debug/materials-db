#!/usr/bin/env python3
"""
export/modalfit.py
===================
Export layers from data/materials_oxide_test.db into ModalFit slab-model
JSON. Schema/units confirmed in docs/modalfit_schema_notes.md (CHECKPOINT 1)
and re-confirmed against the ModalFit source directly for this step -- see
docs/for_aiden.md for the gaps found along the way.

Targets physics.py's live-app convention: top-level "xray"/"neutron" blocks
per layer (NOT the GUI builder's "scattering" block -- physics.py:_get_sld,
the function the live web app actually calls, never reads "scattering").
A "scattering" alias is also emitted for the standalone model_predictor.py
tool's compatibility, since extra keys are tolerated everywhere.

Tabulated n,k optical data is written as a sidecar CSV per (material,
dataset_label axis) -- ModalFit's `optical.params.file` is a path to a
separate CSV, not inline JSON arrays (physics.py:nk_tabulated). The path is
written relative to wherever export_stack() writes the JSON, which is the
ONLY resolution path that actually works today: physics.py's
_resolve_nk_path() falls back to `json_dir + file`, but `json_dir` comes
from `entry["_json_dir"]`, which the live web app's upload flow
(server.py -> physics.normalize_stack) never sets, and there is no upload
route for a companion CSV at all -- only the standalone desktop tool
(model_predictor.py) tracks the on-disk file location and can resolve a
relative sidecar path. See docs/for_aiden.md.

Units: SLD in 1e-6 A^-2, thickness/roughness in A, wavelength in nm,
density in g/cm3 -- all match this repo's DB conventions with no
conversion needed today (confirmed empirically in Step 1). All DB->
ModalFit unit handling is centralized in _to_modalfit_units() below rather
than scattered per-field, so if any of these ever need a real conversion,
there's exactly one place to change.
"""

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = _ROOT / "data" / "materials_oxide_test.db"

sys.path.insert(0, str(_ROOT / "scripts"))
from oxide_material_list import RESOLVED_OPTICAL_SOURCE_CITATION as _OXIDE_CITATIONS  # noqa: E402
from fluoride_nitride_sulfide_material_list import (  # noqa: E402
    RESOLVED_OPTICAL_SOURCE_CITATION as _BATCH2_CITATIONS,
)

# Single merged citation lookup across every batch -- a later batch (metals,
# TMDCs, etc.) extends this same way rather than starting its own dict, so
# no batch has to re-litigate what an earlier one already settled.
RESOLVED_OPTICAL_SOURCE_CITATION = {**_OXIDE_CITATIONS, **_BATCH2_CITATIONS}

# Standard crystalline Si substrate, NOT sourced from materials_oxide_test.db
# (an oxides-only dataset with no elemental Si row) -- same values used and
# labeled the same way in scripts/xrr_smoke_test_oxide_db.py.
_SILICON_SUBSTRATE = dict(density_g_cm3=2.329, xray_sld_real=20.0620, xray_sld_imag=0.457236)


class ExportError(ValueError):
    """Raised for anything this exporter refuses to silently paper over:
    an ambiguous dataset_label, a missing density, no optical data, etc.
    Never emit a null/guessed value where the task requires an explicit
    error instead."""


# Named, asserted-against exclusions from the 50-material set -- a bulk
# export producing exactly these (and only these) ExportErrors is a known,
# expected outcome, not a partial failure. See
# scripts/export_all_oxides_modalfit.py, which asserts the skip set matches
# this exactly: an unexpected skip (regression) or an unexpected SUCCESS
# (this material's underlying gap got fixed) both fail loudly rather than
# silently changing what "49/50" means.
KNOWN_EXCLUSIONS = {
    "LuAl3(BO3)4": "no density available from either PubChem or Materials Project "
                   "(see data/CHECKPOINT_2_report.md) -- export_layer correctly "
                   "refuses to export a layer with no density rather than emitting "
                   "a null. Accepted, expected exclusion, not a bug.",
    "GdF3": "named exclusion (batch 2, see scripts/fluoride_nitride_sulfide_material_list.py "
            "EXCLUSION_STATE) -- MP's only entry is theoretical/unverified and structurally "
            "inconsistent with GdF3's documented room-temperature phase; no citable "
            "experimental density found within the timebox. Same shape as LuAl3(BO3)4: "
            "accepted, expected exclusion, not a bug.",
}


# ---------------------------------------------------------------------------
# Unit boundary -- the one place DB units become ModalFit units
# ---------------------------------------------------------------------------

def _to_modalfit_units(*, density_g_cm3=None, xray_sld_real=None, xray_sld_imag=None,
                        neutron_sld_real=None, neutron_sld_imag=None,
                        wavelength_nm=None, thickness_a=None, roughness_a=None) -> dict:
    """Single conversion boundary from materials-db units to ModalFit units.
    Every field here is currently an identity pass-through (confirmed in
    docs/modalfit_schema_notes.md Q2 -- SLD in 1e-6 A^-2, density in
    g/cm3, wavelength in nm, thickness/roughness in A, matching our DB
    exactly). Kept as an explicit function, not scattered per call site, so
    a future real mismatch has exactly one place to fix.
    """
    return dict(
        density_g_cm3=density_g_cm3,        # g/cm3 -> g/cm3 (MaterialSLD units="g / cm**3")
        xray_sld_real=xray_sld_real,        # 1e-6 A^-2 -> 1e-6 A^-2 (physics.py Q2)
        xray_sld_imag=xray_sld_imag,
        neutron_sld_real=neutron_sld_real,
        neutron_sld_imag=neutron_sld_imag,
        wavelength_nm=wavelength_nm,         # nm -> nm (nk_cauchy, nk_tabulated)
        thickness_a=thickness_a,             # A -> A (slab_model_builder.py labels, Q2)
        roughness_a=roughness_a,
    )


def _bounded(value, vmin=None, vmax=None, log_default=None):
    """dict for a ModalFit {"value","min","max"} field. Logs (via the
    returned 'used_default' flag) when we had no bound and are falling
    through to ModalFit's own auto-default rather than emitting one."""
    used_default = vmin is None and vmax is None
    if log_default and used_default:
        print(f"[modalfit export] no explicit bounds for {log_default}={value}; "
              f"ModalFit will auto-default them.")
    return {"value": value, "min": vmin, "max": vmax}


# ---------------------------------------------------------------------------
# DB lookups
# ---------------------------------------------------------------------------

def _find_material(conn, name):
    row = conn.execute(
        "SELECT material_id, name, formula FROM materials WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT material_id, name, formula FROM materials WHERE formula = ?", (name,)
        ).fetchone()
    return row


# dataset_label shapes (see scripts/load_oxides_db.py / build_checkpoint1_report.py):
#   with polymorph:    "rutile | xray_sld_real | periodictable_CuKalpha"
#                       "rutile | Devore1951 | o-ray"
#   without polymorph: "xray_sld_real | periodictable_CuKalpha"   (physical_properties)
#                       "density_MP_DFT"                          (physical_properties, no " | " at all)
#                       "Devore1951 | o-ray"                      (optical_dispersion)
#                       "Devore1951"                              (optical_dispersion, isotropic, no axis)
# A naive split(" | ")[0] cannot tell these apart -- for a polymorph-less
# material it would treat each quantity type (or each paper) as its own
# "polymorph". Detect the absence of a polymorph segment instead by
# recognizing what the first segment looks like when one isn't there: a
# physical_properties quantity marker, or an optical "AuthorYYYY" source
# label (never a real polymorph name in this dataset -- polymorph names
# here are words like "rutile"/"wurtzite"/"K2NiF4-type", never
# Letters+4-digits).
_QUANTITY_MARKERS = ("density_", "xray_sld_real", "xray_sld_imag",
                     "neutron_sld_real", "neutron_sld_imag")
_SOURCE_LABEL_RE = re.compile(r"^[A-Za-z]+\d{4}$")


def _polymorph_prefix(dataset_label: str) -> Optional[str]:
    first = dataset_label.split(" | ", 1)[0]
    if any(first.startswith(m) for m in _QUANTITY_MARKERS) or _SOURCE_LABEL_RE.match(first):
        return None
    return first


def _resolve_physical_properties(conn, material_id, material_label, dataset_label):
    rows = conn.execute(
        "SELECT dataset_label, density_g_cm3, xray_sld, neutron_sld, source_id "
        "FROM physical_properties WHERE material_id = ?",
        (material_id,),
    ).fetchall()
    if not rows:
        raise ExportError(f"'{material_label}' has no physical_properties rows at all.")

    prefixes = sorted({_polymorph_prefix(r[0]) for r in rows}, key=lambda p: (p is None, p or ""))
    if dataset_label:
        matches = [p for p in prefixes if p is not None and
                   (dataset_label == p or dataset_label.startswith(p) or p.startswith(dataset_label))]
        if not matches:
            raise ExportError(
                f"dataset_label '{dataset_label}' does not match any physical_properties "
                f"polymorph for '{material_label}'. Available: {prefixes}"
            )
        chosen_prefix = matches[0]
    else:
        if len(prefixes) > 1:
            raise ExportError(
                f"'{material_label}' has {len(prefixes)} distinct polymorphs in "
                f"physical_properties and no dataset_label was given: {prefixes}. "
                f"Specify dataset_label to disambiguate."
            )
        chosen_prefix = prefixes[0]

    selected = [r for r in rows if _polymorph_prefix(r[0]) == chosen_prefix]

    out = dict(polymorph=chosen_prefix, density_g_cm3=None, xray_sld_real=None,
               xray_sld_imag=None, neutron_sld_real=None, neutron_sld_imag=None,
               density_source_id=None, density_dataset_label=None)
    for label, density, xray, neutron, source_id in selected:
        if density is not None:
            out["density_g_cm3"] = density
            out["density_source_id"] = source_id
            out["density_dataset_label"] = label
        elif "xray_sld_real" in label:
            out["xray_sld_real"] = xray
        elif "xray_sld_imag" in label:
            out["xray_sld_imag"] = xray
        elif "neutron_sld_real" in label:
            out["neutron_sld_real"] = neutron
        elif "neutron_sld_imag" in label:
            out["neutron_sld_imag"] = neutron

    if out["density_g_cm3"] is None:
        raise ExportError(
            f"'{material_label}' (polymorph '{chosen_prefix}') has no density in "
            f"physical_properties -- refusing to export a layer with no density."
        )
    return out


def _resolve_optical_axis(conn, material_id, material_label, polymorph_prefix, dataset_label):
    """Pick ONE optical_dispersion axis. ModalFit's optical block models an
    isotropic material; a birefringent material's o/e (or biaxial
    alpha/beta/gamma) axes can't both be represented in one layer. This is
    a real simplification -- see docs/for_aiden.md -- not something to hide."""
    labels = [r[0] for r in conn.execute(
        "SELECT DISTINCT dataset_label FROM optical_dispersion WHERE material_id = ?",
        (material_id,),
    ).fetchall()]
    if not labels:
        raise ExportError(f"'{material_label}' has no optical_dispersion rows at all.")

    candidates = [l for l in labels if _polymorph_prefix(l) == polymorph_prefix]
    if not candidates:
        raise ExportError(
            f"'{material_label}' has optical_dispersion data, but none under polymorph "
            f"'{polymorph_prefix}'. Available optical dataset_labels: {labels}"
        )

    if dataset_label and dataset_label in candidates:
        chosen = dataset_label
    elif len(candidates) == 1:
        chosen = candidates[0]
    else:
        # prefer an isotropic (no-axis-suffix) entry, else ordinary ray,
        # else the alphabetically-first axis -- and always report the choice.
        isotropic = [l for l in candidates if not any(s in l for s in
                     ("o-ray", "e-ray", "alpha-axis", "beta-axis", "gamma-axis"))]
        ordinary = [l for l in candidates if "o-ray" in l]
        chosen = (isotropic or ordinary or sorted(candidates))[0]
        print(f"[modalfit export] '{material_label}' has {len(candidates)} optical axes "
              f"({candidates}); no exact dataset_label given, defaulting to isotropic "
              f"approximation using '{chosen}'.")

    rows = conn.execute(
        "SELECT wavelength_nm, n, k FROM optical_dispersion "
        "WHERE material_id = ? AND dataset_label = ? ORDER BY wavelength_nm",
        (material_id, chosen),
    ).fetchall()
    source_id = conn.execute(
        "SELECT source_id FROM optical_dispersion WHERE material_id = ? AND dataset_label = ? LIMIT 1",
        (material_id, chosen),
    ).fetchone()
    return chosen, rows, (source_id[0] if source_id else None)


def _source_citation(conn, source_id):
    if source_id is None:
        return None
    row = conn.execute(
        "SELECT doi, title, authors, journal, year FROM sources WHERE source_id = ?", (source_id,)
    ).fetchone()
    if row is None:
        return None
    doi, title, authors, journal, year = row
    return dict(doi=doi, title=title, authors=authors, journal=journal, year=year)


_ANION_TO_MATERIAL_TYPE = (
    # Checked in this order: a formula containing oxygen is classified as
    # an oxide even if it also contains another anion (e.g. a borate,
    # molybdate, or vanadate -- all 50 oxide-batch formulas fit this).
    ("O", "oxide"),
    ("F", "fluoride"),
    ("N", "nitride"),
    ("S", "sulfide"),
)


def _classify_material_type(formula: str) -> str:
    """Derive the ModalFit "material_type" field from the formula's anion
    rather than a fixed string. export_layer() used to hardcode
    "material_type": "oxide" for every layer regardless of formula -- found
    during the batch-2 audit: every fluoride/nitride/sulfide layer (ZnS,
    CaF2, GaN, ...) was silently mislabeled "oxide" in its exported JSON.
    Returns "unknown" rather than guessing if none of the recognized
    anions are present (never silently mislabels)."""
    elements = set(re.findall(r"[A-Z][a-z]?", formula))
    for anion, material_type in _ANION_TO_MATERIAL_TYPE:
        if anion in elements:
            return material_type
    return "unknown"


def _lookup_mp_id(material_formula: str) -> Optional[str]:
    """Best-effort enrichment: mp_id isn't a DB column (only dataset_label
    is, by the schema-freeze decision), but it IS in the per-batch enrichment
    CSVs. Checks every known batch's CSV (not just the oxide batch's --
    checking only oxides_50.csv silently returned None for every batch-2
    material even though a real mp_id was on file). Returns None (never
    raises) if no CSV has a match -- this is supplementary provenance, not
    a required field."""
    import pandas as pd
    for csv_name in ("oxides_50.csv", "batch2_28.csv"):
        csv_path = _ROOT / "data" / csv_name
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path)
            match = df[df["formula"] == material_formula]
            if match.empty:
                continue
            val = match.iloc[0].get("mp_id")
            if pd.notna(val):
                return str(val)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Sidecar n,k CSV
# ---------------------------------------------------------------------------

def _write_nk_csv(path: Path, rows) -> None:
    """physics.py's nk_tabulated() loads this with np.loadtxt(...), which
    requires every cell to parse as a float -- an empty string for a
    missing k (many of our RI.info datasets are n-only) crashes with
    'could not convert string '' to float64', not a graceful None. Write
    0.0 for missing k (a transparent/non-absorbing approximation, physically
    reasonable for the visible-range oxide data this exporter targets) and
    flag it in the returned row count so callers can see how many were
    defaulted rather than measured."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_k_defaulted = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wavelength_nm", "n", "k"])
        for wl, n, k in rows:
            if k is None:
                n_k_defaulted += 1
            w.writerow([wl, n, k if k is not None else 0.0])
    if n_k_defaulted:
        print(f"[modalfit export] {path.name}: {n_k_defaulted}/{len(rows)} rows had no "
              f"measured k, defaulted to 0.0 (transparent/non-absorbing approximation)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_layer(db, material_name: str, dataset_label: Optional[str] = None, *,
                  thickness_a: Optional[float] = None, thickness_min: Optional[float] = None,
                  thickness_max: Optional[float] = None,
                  roughness_a: Optional[float] = None, roughness_min: Optional[float] = None,
                  roughness_max: Optional[float] = None,
                  nk_csv_dir: Path = Path("."), role: str = "layer",
                  label: Optional[str] = None) -> dict:
    """Build one ModalFit layer dict from materials_oxide_test.db, writing
    its sidecar n,k CSV into nk_csv_dir. Raises ExportError rather than
    emitting a null for a missing density, an ambiguous dataset_label with
    no way to pick one, or missing optical data.
    """
    conn = sqlite3.connect(str(db)) if isinstance(db, (str, Path)) else db
    close_after = isinstance(db, (str, Path))
    try:
        mat_row = _find_material(conn, material_name)
        if mat_row is None:
            raise ExportError(f"Material '{material_name}' not found in {db}")
        material_id, db_name, formula = mat_row

        phys = _resolve_physical_properties(conn, material_id, material_name, dataset_label)
        opt_label, nk_rows, opt_source_id = _resolve_optical_axis(conn, material_id, material_name,
                                                                    phys["polymorph"], dataset_label)

        u = _to_modalfit_units(
            density_g_cm3=phys["density_g_cm3"],
            xray_sld_real=phys["xray_sld_real"], xray_sld_imag=phys["xray_sld_imag"],
            neutron_sld_real=phys["neutron_sld_real"], neutron_sld_imag=phys["neutron_sld_imag"],
            thickness_a=thickness_a, roughness_a=roughness_a,
        )

        label = label or (f"{formula}_{phys['polymorph']}" if phys["polymorph"] else formula)
        nk_filename = f"{label}_nk.csv".replace(" ", "_")
        _write_nk_csv(Path(nk_csv_dir) / nk_filename, nk_rows)

        density_citation = _source_citation(conn, phys["density_source_id"])
        optical_citation = _source_citation(conn, opt_source_id)
        resolved = RESOLVED_OPTICAL_SOURCE_CITATION.get(formula)
        if optical_citation is not None and resolved is not None:
            optical_citation = dict(optical_citation, verification_note=resolved["verification_note"])
        mp_id = _lookup_mp_id(formula)

        layer = {
            "label": label,
            "role": role,
            "material_type": _classify_material_type(formula),
            "molecular": {"formula": formula, "density_g_cm3": u["density_g_cm3"]},
            "structural": {
                "thickness": _bounded(u["thickness_a"], thickness_min, thickness_max,
                                      log_default=f"{label}.thickness" if u["thickness_a"] is not None else None),
                "roughness": _bounded(u["roughness_a"], roughness_min, roughness_max,
                                      log_default=f"{label}.roughness" if u["roughness_a"] is not None else None),
            },
            "optical": {"model": "Tabulated n,k", "params": {"file": nk_filename}},
            "xray": {
                "sld_real": {"value": u["xray_sld_real"], "min": None, "max": None},
                "sld_imag": {"value": u["xray_sld_imag"], "min": None, "max": None},
            },
            "neutron": {
                "sld_real": {"value": u["neutron_sld_real"], "min": None, "max": None},
                "sld_imag": {"value": u["neutron_sld_imag"], "min": None, "max": None},
            },
            # alias for the standalone model_predictor.py tool, which reads
            # "scattering" instead of "xray"/"neutron" -- see schema notes.
            "scattering": {
                "sld_real": {"value": u["xray_sld_real"], "min": None, "max": None},
                "sld_imag": {"value": u["xray_sld_imag"], "min": None, "max": None},
            },
            "materials_db": {
                "dataset_label": phys["density_dataset_label"],
                "optical_dataset_label": opt_label,
                "mp_id": mp_id,
                "density_source": density_citation,
                "optical_source": optical_citation,
            },
        }
        return layer
    finally:
        if close_after:
            conn.close()


def export_stack(db, layers: list, *, ambient: str = "air", substrate: str = "silicon",
                  stack_id: Optional[str] = None, sample_id: Optional[str] = None,
                  out_dir: Path = Path(".")) -> dict:
    """Assemble a full ModalFit stack: ambient + oxide layers (from the DB,
    via export_layer) + substrate. ambient/substrate are NOT read from
    materials_oxide_test.db (an oxides-only dataset -- e.g. no elemental Si
    row) -- they're minimal fixed placeholders, clearly not DB-sourced."""
    out_dir = Path(out_dir)

    ambient_entry = {"label": ambient, "role": "ambient", "material_type": "ambient",
                      "xray": {"sld_real": {"value": 0.0}, "sld_imag": {"value": 0.0}},
                      "neutron": {"sld_real": {"value": 0.0}, "sld_imag": {"value": 0.0}}}

    if substrate.lower() in ("silicon", "si"):
        sub = _SILICON_SUBSTRATE
        substrate_entry = {
            "label": "Silicon", "role": "substrate", "material_type": "substrate",
            "molecular": {"formula": "Si", "density_g_cm3": sub["density_g_cm3"]},
            "xray": {"sld_real": {"value": sub["xray_sld_real"]}, "sld_imag": {"value": sub["xray_sld_imag"]}},
            "neutron": {"sld_real": {"value": None}, "sld_imag": {"value": None}},
            "materials_db": {"note": "standard crystalline Si constants, NOT from "
                                      "materials_oxide_test.db (an oxides-only dataset)"},
        }
    else:
        raise ExportError(f"Unknown substrate '{substrate}' -- only 'silicon' is supported "
                           f"as a non-DB placeholder right now.")

    stack_layers = []
    for spec in layers:
        stack_layers.append(export_layer(
            db, spec["material"], spec.get("dataset_label"),
            thickness_a=spec.get("thickness_a"), thickness_min=spec.get("thickness_min"),
            thickness_max=spec.get("thickness_max"),
            roughness_a=spec.get("roughness_a"), roughness_min=spec.get("roughness_min"),
            roughness_max=spec.get("roughness_max"),
            nk_csv_dir=out_dir, role="layer", label=spec.get("label"),
        ))

    stack = [ambient_entry] + stack_layers + [substrate_entry]
    return {
        "stack_id": stack_id or "materials_db_export",
        "sample_id": sample_id or "materials_db_export",
        "version": 1,
        "provenance": {"generated_by": "materials_db.export.modalfit", "source_db": str(db)},
        "n_layers": len(stack_layers),
        "stack": stack,
    }
