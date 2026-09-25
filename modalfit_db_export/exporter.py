#!/usr/bin/env python3
"""
exporter.py -- materials-db SQLite -> ModalFit slab-model JSON
===============================================================
Reads a materials database (SQLite) and emits ModalFit slab-model JSON,
plus the sidecar tabulated-n,k CSV each layer's optical block points at.

Drop-in copy of materials-db's src/materials_db/export/modalfit.py. The
translation logic below is UNCHANGED; only three couplings to the
materials-db repo layout were rewired, each marked `# DROP-IN:` inline:

  1. The citation table and the density-confidence helpers, previously
     imported from scripts/ (via sys.path.insert) and from the ingestion
     pipeline package, are now vendored siblings (citations.py, density.py).
  2. DEFAULT_DB / _ROOT -- a hardcoded path into the materials-db checkout
     -- are gone. The database path is now always an explicit argument.
  3. _lookup_mp_id() globbed that same hardcoded data/ directory and
     imported pandas at call time. It now takes the directory to search
     as a parameter (defaulting to the database's OWN directory, which
     reproduces the original behavior exactly, since materials-db keeps
     materials_oxide_test.db and the enrichment CSVs side by side in
     data/), and degrades to returning None when pandas isn't installed
     rather than raising -- mp_id is supplementary provenance, never
     required.

Schema/units were confirmed against the ModalFit source directly at the
pinned commit -- see contract.py for the file:line citations, and
SCHEMA_NOTES.md for the full derivation.

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
relative sidecar path. See contract.py's optical_nk_path_resolution
entry for the file:line evidence, and README.md's LIMITATIONS section
for what it means in practice.

Units: SLD in 1e-6 A^-2, thickness/roughness in A, wavelength in nm,
density in g/cm3 -- all match this repo's DB conventions with no
conversion needed today (confirmed empirically in Step 1). All DB->
ModalFit unit handling is centralized in _to_modalfit_units() below rather
than scattered per-field, so if any of these ever need a real conversion,
there's exactly one place to change.
"""

import csv
import re
import sqlite3
from pathlib import Path
from typing import Optional

# DROP-IN (1): vendored siblings. Upstream these were
#   sys.path.insert(_ROOT/"scripts") + `from oxide_material_list import ...`
#   + `from fluoride_nitride_sulfide_material_list import ...`, merged here
#   into one dict, and `from materials_db.pipeline.process_condition import ...`.
# See each module's docstring for what was lifted and how to regenerate it.
from .citations import RESOLVED_OPTICAL_SOURCE_CITATION
from .density import (
    BULK_ELEMENTAL_APPROXIMATION, DENSITY_VERIFIED, DENSITY_BULK_APPROXIMATION,
    bulk_approximation_density_bounds, verified_density_bounds,
)

# DROP-IN (2): _ROOT / DEFAULT_DB removed. Upstream they were
#   _ROOT = Path(__file__).resolve().parents[3]
#   DEFAULT_DB = _ROOT / "data" / "materials_oxide_test.db"
# -- a path that only resolves inside a materials-db checkout. Every public
# function here takes the database as its first argument instead; there is
# no default and no implicit lookup, so this package can never silently
# read the wrong database.

# Historical note: substrate used to be a fixed, non-DB-sourced Si
# placeholder here (density_g_cm3=2.329, xray_sld_real=20.0620,
# xray_sld_imag=0.457236). Silicon is now a real materials_oxide_test.db
# material (batch 3, verified bulk/single-crystal) and export_stack()
# resolves ANY substrate the same way it resolves a film layer -- see
# export_stack()'s docstring. Cross-checked once, for the record: routing
# "Silicon" through export_layer() reproduces these exact legacy numbers
# to displayed precision (confirmed via refnx.MaterialSLD("Si", 2.329,
# probe="x-ray") -> 20.0620+0.4573j, matching this constant exactly), so
# the switch changes WHERE the number comes from, not its value.


class ExportError(ValueError):
    """Raised for anything this exporter refuses to silently paper over:
    an ambiguous dataset_label, a missing density, no optical data, etc.
    Never emit a null/guessed value where the task requires an explicit
    error instead."""


# Named, asserted-against exclusions from the 50-material set -- a bulk
# export producing exactly these (and only these) ExportErrors is a known,
# expected outcome, not a partial failure. See
# materials-db scripts/export_all_oxides_modalfit.py, which asserts the skip set matches
# this exactly: an unexpected skip (regression) or an unexpected SUCCESS
# (this material's underlying gap got fixed) both fail loudly rather than
# silently changing what "49/50" means.
KNOWN_EXCLUSIONS = {
    "LuAl3(BO3)4": "no density available from either PubChem or Materials Project "
                   "(see materials-db data/CHECKPOINT_2_report.md) -- export_layer correctly "
                   "refuses to export a layer with no density rather than emitting "
                   "a null. Accepted, expected exclusion, not a bug.",
    "GdF3": "named exclusion (batch 2, see materials-db scripts/fluoride_nitride_sulfide_material_list.py "
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
    SCHEMA_NOTES.md Q2 -- SLD in 1e-6 A^-2, density in
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
    """Look up a materials row by exact name first, falling back to
    formula. Raises ExportError (does not silently pick one) if the
    formula fallback matches more than one row -- true for any formula
    with multiple genuinely distinct allotropes stored as separate
    materials rows (e.g. "C" resolves to both Diamond and Graphite,
    batch 3b). Before this check, .fetchone() on the formula query would
    silently return whichever row SQLite happened to return first for an
    ambiguous formula -- the same silent-wrong-answer shape this project
    has hunted down repeatedly elsewhere (_lookup_mp_id, material_type,
    batch 1's polymorph fallback). A caller hitting this must specify the
    exact material name instead of the formula."""
    row = conn.execute(
        "SELECT material_id, name, formula FROM materials WHERE name = ?", (name,)
    ).fetchone()
    if row is not None:
        return row

    matches = conn.execute(
        "SELECT material_id, name, formula FROM materials WHERE formula = ?", (name,)
    ).fetchall()
    if len(matches) > 1:
        names = [m[1] for m in matches]
        raise ExportError(
            f"Formula '{name}' matches {len(matches)} distinct materials: {names}. "
            f"Specify the exact material name instead of the formula to disambiguate."
        )
    return matches[0] if matches else None


# dataset_label shapes (see materials-db scripts/load_oxides_db.py and
# build_checkpoint1_report.py, which write them):
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


def _density_confidence(density_dataset_label: Optional[str]) -> str:
    """DENSITY_VERIFIED or DENSITY_BULK_APPROXIMATION, read off the
    density row's own dataset_label (which already carries the
    density_source via the "density_{density_source}" convention -- see
    load_oxides_db.py's label_join()). bulk_elemental_approximation is
    the one density_source value that does NOT count as verified -- see
    process_condition.density_state_from_source() and
    materials-db docs/batch3_scoping_report.md for why this is a deliberate, argued
    distinction, not an oversight."""
    if density_dataset_label and BULK_ELEMENTAL_APPROXIMATION in density_dataset_label:
        return DENSITY_BULK_APPROXIMATION
    return DENSITY_VERIFIED


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
    a real simplification -- see README.md's LIMITATIONS section -- not
    something to hide."""
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


def _lookup_mp_id(material_formula: str, enrichment_csv_dir: Optional[Path]) -> Optional[str]:
    """Best-effort enrichment: mp_id isn't a DB column (only dataset_label
    is, by the schema-freeze decision), but it IS in the per-batch enrichment
    CSVs. Globs <enrichment_csv_dir>/*.csv and checks any CSV with
    "formula"/"mp_id" columns, rather than a hardcoded filename list -- a
    hardcoded list of exactly two names ("oxides_50.csv", "batch2_28.csv")
    already caused this function to silently return None for every batch-2
    material once written, and then AGAIN, for every batch-2 AND batch-3
    material, the moment batch2_28.csv was renamed to batch2_31.csv (found
    by that rename's own test suite catching a newly-skipped test, not by
    this function failing loudly). Globbing removes the recurring failure
    mode instead of patching this instance of it. Returns None (never
    raises) if no CSV has a match -- this is supplementary provenance, not
    a required field.

    DROP-IN (3): upstream this took no directory argument and globbed
    _ROOT/"data"/*.csv. Callers now pass the directory; export_layer()
    defaults it to the database file's own parent, which IS _ROOT/"data"
    in a materials-db checkout -- so default behavior is unchanged. A
    caller with no enrichment CSVs passes None and gets None back.
    pandas is imported lazily and a missing pandas degrades to None
    rather than raising: this package's required dependencies are the
    standard library alone."""
    if enrichment_csv_dir is None:
        return None
    import glob as _glob
    try:
        import pandas as pd
    except ImportError:
        return None
    for csv_path_str in sorted(_glob.glob(str(Path(enrichment_csv_dir) / "*.csv"))):
        csv_path = Path(csv_path_str)
        try:
            df = pd.read_csv(csv_path)
            if "formula" not in df.columns or "mp_id" not in df.columns:
                continue
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
                  label: Optional[str] = None,
                  enrichment_csv_dir: Optional[Path] = None) -> dict:
    """Build one ModalFit layer dict from the materials database, writing
    its sidecar n,k CSV into nk_csv_dir. Raises ExportError rather than
    emitting a null for a missing density, an ambiguous dataset_label with
    no way to pick one, or missing optical data.

    Two conventions this layer's "structural.roughness" and
    "xray.sld_imag"/"neutron.sld_imag" fields commit to, verified directly
    against ModalFit's fitting code (physics.py's _make_xrr_slab/
    _make_xrr_boundary and refnx's Scatterer/MaterialSLD, not just against
    our own simulator) rather than assumed from how they parse -- see
    XRR_FIT_FINDINGS.md for the verification:

    1. roughness_a describes the interface ABOVE this layer (between the
       previous entry in the stack and this one), never below. This is
       refnx's own Scatterer convention (`sld_obj(thick, rough)`) --
       ModalFit's _make_xrr_slab/_make_xrr_boundary call it exactly that
       way, reading `rough` straight off THIS entry. Get this backwards
       (as src/materials_db/simulation/xrr.py's parratt() did until this
       was checked) and every interface's roughness silently attaches to
       the wrong side, with no error.
    2. A positive imaginary SLD means absorption (this repo's stored
       convention throughout: periodictable's xray_sld(), this DB's
       xray_sld_imag column, this field). Both of ModalFit's actual
       consumption paths agree with that sign as-is: refnx.reflect.SLD
       correctly treats a positive imaginary part as absorptive with no
       conjugation needed, and the DEFAULT path (MaterialSLD, used
       whenever molecular.formula + molecular.density are both present --
       i.e. every layer this exporter emits) recomputes SLD independently
       from refnx's own tables and agrees with this DB's periodictable
       value to 5 significant figures, confirming the two are consistent
       rather than one silently overriding the other with a different
       sign.
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
        # Sanitize the label into a flat, filesystem-safe filename -- a
        # bare .replace(" ", "_") missed "/", which two real polymorph
        # names contain ("corundum/sapphire", "scheelite/wulfenite").
        # Found live: export_stack() picking Sapphire as a substrate wrote
        # "Al2O3_corundum/sapphire_nk.csv" as the optical.params.file
        # value, which os.path.join'd into an ACCIDENTAL nested
        # subdirectory ("Al2O3_corundum/" containing "sapphire_nk.csv")
        # instead of the flat file in nk_csv_dir this function's own
        # docstring promises. It happened to still resolve (ModalFit's
        # _resolve_nk_path does the same os.path.join), so nothing ever
        # crashed -- but it's an accident, not a design, and a second
        # slash-containing label sharing the same prefix could collide in
        # ways the label-disambiguation logic never accounts for (it
        # tracks the full label string, not the sanitized filename). Same
        # sanitizer as export_all_materials_modalfit.py's _safe_dirname().
        nk_filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", label) + "_nk.csv"
        _write_nk_csv(Path(nk_csv_dir) / nk_filename, nk_rows)

        density_citation = _source_citation(conn, phys["density_source_id"])
        optical_citation = _source_citation(conn, opt_source_id)
        resolved = RESOLVED_OPTICAL_SOURCE_CITATION.get(formula)
        if optical_citation is not None and resolved is not None:
            optical_citation = dict(optical_citation, verification_note=resolved["verification_note"])
        # DROP-IN (3): default the enrichment-CSV search to the database's
        # own directory -- data/ in a materials-db checkout, where the
        # per-batch CSVs sit beside materials_oxide_test.db.
        if enrichment_csv_dir is None and isinstance(db, (str, Path)):
            enrichment_csv_dir = Path(db).parent
        mp_id = _lookup_mp_id(formula, enrichment_csv_dir)

        density_confidence = _density_confidence(phys["density_dataset_label"])
        density_bounds = (bulk_approximation_density_bounds(u["density_g_cm3"])
                          if density_confidence == DENSITY_BULK_APPROXIMATION
                          else verified_density_bounds(u["density_g_cm3"]))

        layer = {
            "label": label,
            "role": role,
            "material_type": _classify_material_type(formula),
            "molecular": {"formula": formula, "density_g_cm3": u["density_g_cm3"],
                          "density_confidence": density_confidence,
                          "density_bounds": density_bounds},
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
                "density_confidence": density_confidence,
                "density_source": density_citation,
                "optical_source": optical_citation,
            },
        }
        return layer
    finally:
        if close_after:
            conn.close()


def export_stack(db, layers: list, *, ambient="air", substrate: str = "Silicon",
                  substrate_dataset_label: Optional[str] = None,
                  substrate_roughness_a: Optional[float] = None,
                  substrate_roughness_min: Optional[float] = None,
                  substrate_roughness_max: Optional[float] = None,
                  stack_id: Optional[str] = None, sample_id: Optional[str] = None,
                  out_dir: Path = Path("."),
                  enrichment_csv_dir: Optional[Path] = None) -> dict:
    """Assemble a full ModalFit stack: ambient + film layers + substrate.

    substrate is DB-driven, exactly like a film layer -- pass any
    materials_oxide_test.db name or formula (default "Silicon", the pure
    element added in batch 3; previously a fixed, non-DB-sourced Si
    placeholder). Resolved via export_layer(role="substrate") internally,
    so a substrate carries the SAME density_confidence/density_bounds/
    citation fields a film layer does -- the old placeholder had none of
    that (no way to see whether the substrate's density was trustworthy,
    because it wasn't a DB lookup at all). `substrate_dataset_label`
    disambiguates a substrate material with more than one polymorph, same
    as a film layer's `dataset_label`. Raises ExportError if the substrate
    name/formula isn't found in `db` -- same "raise, don't guess" contract
    export_layer() already has for a film layer.

    ambient accepts either the literal string "air" (default, an exact-
    zero-SLD placeholder -- materials_oxide_test.db has no liquid/gas
    materials, so there is nothing to look up) or a pre-built ambient
    entry dict, e.g. from materials_db.launcher.ambient.build_ambient_entry
    ("vacuum"/"d2o"/"h2o") -- checked against ModalFit's actual ambient-
    handling code (physics.py:_make_xrr_boundary, compute_se) before that
    module was written; see its docstring for what's confirmed and what's
    a labeled approximation.

    substrate_roughness_a matters more than it looks: ModalFit's
    _make_xrr_boundary() reads the film/substrate interface roughness from
    the SUBSTRATE entry's own "structural.roughness", not from the last
    film layer's. export_layer() always keeps this field PRESENT with
    value=None when no roughness is given (same convention as a film
    layer's thickness_a/roughness_a, and the same "no explicit bounds"
    notice _bounded() prints for one) rather than omitting the key --
    before this parameter existed at all, the old hardcoded substrate had
    no "structural" key whatsoever, so roughness silently read back as 0.0
    (a perfectly sharp interface) with no error (see XRR_FIT_FINDINGS.md).
    Pass a real value for any stack meant to be fit against real
    reflectivity data.

    Layer labels (film AND substrate) are disambiguated BEFORE any layer
    is exported: the substrate's label is resolved first and seeded into
    the collision-tracking, so a film layer that happens to land on the
    SAME label the substrate resolved to (e.g. "Silicon" chosen as both a
    thin film AND the substrate -- unusual, but not physically
    meaningless, and the schema doesn't forbid it) gets a "#2" suffix
    rather than colliding with the substrate's own sidecar n,k CSV.
    Among film layers, two that would resolve to the same label (the same
    formula+polymorph, or two layers explicitly given the same `label`)
    get a "#2", "#3", ... suffix appended to every occurrence after the
    first. Without this, a repeated-unit stack (a Bragg mirror, a
    superlattice -- a real sample type, not a contrived one) would
    silently produce two layers with the IDENTICAL label: their sidecar
    n,k CSVs would collide in nk_csv_dir (the second write overwriting the
    first), and worse, physics.extract_params() builds each fittable
    parameter's key as f"{label}:thick" etc., so both layers would get the
    SAME key -- found by reproducing it directly (a SiO2/Ta2O5/SiO2 stack
    produced two ParamSpecs both keyed "SiO2_amorphous:thick"), meaning
    FitEngine could not move the two physically distinct layers
    independently. See XRR_FIT_FINDINGS.md."""
    out_dir = Path(out_dir)

    if isinstance(ambient, dict):
        ambient_entry = dict(ambient)
    elif isinstance(ambient, str) and ambient.lower() == "air":
        ambient_entry = {"label": "Air", "role": "ambient", "material_type": "ambient",
                          "xray": {"sld_real": {"value": 0.0}, "sld_imag": {"value": 0.0}},
                          "neutron": {"sld_real": {"value": 0.0}, "sld_imag": {"value": 0.0}}}
    else:
        raise ExportError(
            f"Unknown ambient {ambient!r} -- materials_oxide_test.db has no liquid/gas "
            f"materials, so ambient isn't DB-driven. Pass 'air' (default) or a pre-built "
            f"entry dict, e.g. materials_db.launcher.ambient.build_ambient_entry('vacuum'/"
            f"'d2o'/'h2o')."
        )

    # DROP-IN (3): resolve once here, before the connection is opened --
    # export_layer() is called below with an open Connection, from which a
    # database directory can no longer be derived.
    if enrichment_csv_dir is None and isinstance(db, (str, Path)):
        enrichment_csv_dir = Path(db).parent

    conn = sqlite3.connect(str(db)) if isinstance(db, (str, Path)) else db
    close_after = isinstance(db, (str, Path))
    try:
        # Resolve the substrate's label FIRST -- it's exempt from its own
        # "#N" suffix (there is exactly one substrate) but seeds
        # seen_counts below so a colliding FILM layer is the one that
        # gets disambiguated.
        sub_mat_row = _find_material(conn, substrate)
        if sub_mat_row is None:
            raise ExportError(f"Substrate material '{substrate}' not found in {db}")
        _sub_material_id, _sub_db_name, sub_formula = sub_mat_row
        sub_phys = _resolve_physical_properties(conn, _sub_material_id, substrate, substrate_dataset_label)
        substrate_label = f"{sub_formula}_{sub_phys['polymorph']}" if sub_phys["polymorph"] else sub_formula

        # Resolve every FILM layer's label next, using the exact same
        # default export_layer() would compute (formula_polymorph, or bare
        # formula with no polymorph) -- reusing its own resolution helpers
        # rather than re-deriving the rule, so this can never silently
        # diverge from what export_layer() would have picked on its own.
        # Then disambiguate any collision (whether from two identical
        # caller-supplied labels, two layers landing on the same default,
        # or a collision with the substrate's own label) before a single
        # export_layer() call runs, so no sidecar CSV is ever written
        # under a name a later layer (or the substrate) will overwrite.
        final_labels = []
        seen_counts: dict = {substrate_label: 1}
        for spec in layers:
            mat_row = _find_material(conn, spec["material"])
            if mat_row is None:
                raise ExportError(f"Material '{spec['material']}' not found in {db}")
            material_id, _db_name, formula = mat_row
            if spec.get("label"):
                base_label = spec["label"]
            else:
                phys = _resolve_physical_properties(conn, material_id, spec["material"], spec.get("dataset_label"))
                base_label = f"{formula}_{phys['polymorph']}" if phys["polymorph"] else formula
            seen_counts[base_label] = seen_counts.get(base_label, 0) + 1
            occurrence = seen_counts[base_label]
            final_labels.append(base_label if occurrence == 1 else f"{base_label}#{occurrence}")

        stack_layers = []
        for spec, final_label in zip(layers, final_labels):
            stack_layers.append(export_layer(
                conn, spec["material"], spec.get("dataset_label"),
                thickness_a=spec.get("thickness_a"), thickness_min=spec.get("thickness_min"),
                thickness_max=spec.get("thickness_max"),
                roughness_a=spec.get("roughness_a"), roughness_min=spec.get("roughness_min"),
                roughness_max=spec.get("roughness_max"),
                nk_csv_dir=out_dir, role="layer", label=final_label,
                enrichment_csv_dir=enrichment_csv_dir,
            ))

        substrate_entry = export_layer(
            conn, substrate, substrate_dataset_label,
            roughness_a=substrate_roughness_a, roughness_min=substrate_roughness_min,
            roughness_max=substrate_roughness_max,
            nk_csv_dir=out_dir, role="substrate", label=substrate_label,
            enrichment_csv_dir=enrichment_csv_dir,
        )
        substrate_entry["materials_db"]["note"] = (
            f"DB-sourced substrate ('{substrate}') -- see this entry's own "
            f"density_confidence/density_source above, same as any film layer."
        )
    finally:
        if close_after:
            conn.close()

    stack = [ambient_entry] + stack_layers + [substrate_entry]
    return {
        "stack_id": stack_id or "materials_db_export",
        "sample_id": sample_id or "materials_db_export",
        "version": 1,
        "provenance": {"generated_by": "modalfit_db_export.exporter", "source_db": str(db)},
        "n_layers": len(stack_layers),
        "stack": stack,
    }
