#!/usr/bin/env python3
"""
pipeline/process_condition.py
================================
Canonical, cross-batch definitions for two concepts pioneered in batch 3
(pure elements) but not specific to it -- defined once here, the way
polymorph was consolidated into scripts/oxide_material_list.py, so a later
batch (metals, more elements) imports these rather than redefining them
locally.

1. PROCESS_CONDITION: an axis orthogonal to polymorph. Polymorph answers
   "which crystal structure/allotrope is this" (diamond vs. graphite,
   alpha-Sn vs. beta-Sn); process_condition answers "how was THIS SPECIFIC
   SAMPLE of that structure made or measured" (deposition method, film
   thickness as an optically-significant condition, measurement
   temperature, single-crystal vs. polycrystalline vs. amorphous grain
   state). A material can have both, one, or neither -- see
   docs/batch3_scoping_report.md Part B for the corpus evidence (carbon
   needs both; gold needs only this).

2. DENSITY_STATE: a four-way gate, DISTINCT from (and orthogonal to) the
   structural EXCLUSION_STATE gate a material list module (e.g.
   fluoride_nitride_sulfide_material_list.py) uses for polymorph/structure
   resolution. A material can be structurally VERIFIED (correct MP
   polymorph) while its density is only BULK_APPROXIMATION, or vice versa.
   bulk_elemental_approximation is explicitly NOT folded into "verified" --
   see the rationale below, this was a deliberate, argued decision, not an
   oversight.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# 1. PROCESS_CONDITION
# ---------------------------------------------------------------------------

# Controlled vocabulary of recognized axes. Not exhaustive by design --
# add an axis here (once) when a real corpus demonstrates it, the same
# discipline EXPECTED_SPACEGROUP/RESOLVED_OPTICAL_SOURCE_CITATION follow:
# evidence-driven, not speculative.
PROCESS_CONDITION_AXES = (
    "deposition",   # evaporated, sputtered, single_crystal, template_stripped, CVD, ALD, arc_grown, aerosol_CVD, HiPco
    "structure",    # polycrystalline, amorphous, single_crystal -- grain/microstructure, distinct from polymorph
    "thickness",    # an explicit film thickness the OPTICAL DATA was measured at (e.g. "25nm") --
                    # not the structural.thickness of a layer in an assembled stack; a property of
                    # which SOURCE DATASET is correct to use, analogous to picking an optical axis
    "temperature",  # measurement temperature (e.g. "225C", "78K") -- the temperature the OPTICAL
                    # MEASUREMENT was taken at (Au: Magnozzi 25/225/350C; Sn: Golovashkin 293/78/4.2K)
    "anneal_temperature",  # a one-time POST-DEPOSITION heat-treatment step, permanently changing
                    # the film (TiN: Shkondin as-deposited/700/800/900C) -- genuinely distinct from
                    # "temperature" above: an anneal changes the sample once; a measurement
                    # temperature describes the condition of ONE measurement of a fixed sample.
                    # Conflating the two was the first mistake this axis's own design almost made.
)

_AXIS_VALUE_RE_FRAGMENT = r"[A-Za-z0-9_.]+"


def format_process_condition(**axis_values: str) -> str:
    """Build the dataset_label segment for a process condition, e.g.
    format_process_condition(deposition="evaporated", thickness="25nm")
    -> "deposition:evaporated;thickness:25nm"

    Uses ";" between axis:value pairs (not " | ", which is dataset_label's
    own top-level separator) and ":" within a pair. Raises on an
    unrecognized axis name rather than silently accepting a typo -- the
    same "raise, don't guess" discipline as _classify_material_type()."""
    unknown = set(axis_values) - set(PROCESS_CONDITION_AXES)
    if unknown:
        raise ValueError(
            f"Unrecognized process_condition axis/axes: {sorted(unknown)}. "
            f"Recognized axes: {PROCESS_CONDITION_AXES}. Add a new axis to "
            f"PROCESS_CONDITION_AXES (once, here) before using it, rather "
            f"than inventing a batch-local one."
        )
    if not axis_values:
        raise ValueError("format_process_condition() called with no axis values.")
    return ";".join(f"{axis}:{value}" for axis, value in axis_values.items())


def parse_process_condition(segment: str) -> dict:
    """Inverse of format_process_condition(). Returns {} for a segment
    that doesn't look like axis:value pairs at all (e.g. it's actually a
    polymorph name or a source label) -- callers should use this only
    after already identifying the segment as a process_condition one."""
    out = {}
    for pair in segment.split(";"):
        if ":" not in pair:
            return {}
        axis, _, value = pair.partition(":")
        if axis not in PROCESS_CONDITION_AXES:
            return {}
        out[axis] = value
    return out


def looks_like_process_condition(segment: str) -> bool:
    """True if `segment` parses as one or more recognized axis:value
    pairs. Used by dataset_label parsers (e.g. modalfit.py's
    _polymorph_prefix-family logic) to recognize a process_condition
    segment and not mis-file it as a polymorph name or a source label --
    the same class of ambiguity that caused batch 1's polymorph-fallback
    bug, addressed here deliberately rather than discovered later."""
    return bool(parse_process_condition(segment))


# ---------------------------------------------------------------------------
# 2. DENSITY_STATE -- a four-way gate, not three
# ---------------------------------------------------------------------------

DENSITY_VERIFIED = "verified"
DENSITY_BULK_APPROXIMATION = "bulk_approximation"
DENSITY_NAMED_EXCLUSION = "named_exclusion"
DENSITY_UNRESOLVED = "unresolved"

DENSITY_STATES = (DENSITY_VERIFIED, DENSITY_BULK_APPROXIMATION,
                  DENSITY_NAMED_EXCLUSION, DENSITY_UNRESOLVED)

# The density_source value stored in physical_properties.dataset_label
# (via the existing "density_{density_source}" convention -- see
# scripts/build_oxides_csv.py's density_source field and
# scripts/load_oxides_db.py's label_join()) for a bulk-approximation
# density. Distinct from "MP_DFT"/"experimental lattice params"/
# "literature", all of which mean a value that IS trusted for the actual
# sample measured (a genuinely bulk/single-crystal sample's bulk density
# is correct, not an approximation) and so count as DENSITY_VERIFIED.
#
# Named for the case that motivated it (pure elements with no measured
# film density -- 345/359 batch-3 RI.info pages), but the mechanism is
# not element-specific: a COMPOUND whose only optical data is an
# uncharacterized sputtered/ALD/annealed thin film with no stated density
# (TiN, VN, EuS) has the identical problem -- MP_DFT bulk crystal density
# stands in for an unmeasured film, same as an element's bulk density
# would. Use this same value for that case too, rather than inventing a
# second bulk-fallback marker.
BULK_ELEMENTAL_APPROXIMATION = "bulk_elemental_approximation"


def density_state_from_source(density_source: str) -> str:
    """Map a density_source string (as stored in dataset_label / recorded
    per-material) to its DENSITY_STATE. bulk_elemental_approximation is
    deliberately NOT mapped to DENSITY_VERIFIED -- see
    docs/batch3_scoping_report.md's density-state rationale: a
    verification_note disclosing the approximation doesn't change what a
    query returns, so it must be its own distinct, queryable state."""
    if density_source == BULK_ELEMENTAL_APPROXIMATION:
        return DENSITY_BULK_APPROXIMATION
    if density_source in ("MP_DFT", "experimental lattice params", "literature"):
        return DENSITY_VERIFIED
    return DENSITY_UNRESOLVED


def bulk_approximation_density_bounds(bulk_density_g_cm3: float) -> dict:
    """Physically-motivated fit bounds for a bulk_elemental_approximation
    density: evaporated/sputtered films are commonly LESS dense than bulk
    (voids, columnar/porous growth), rarely denser (occasional
    ion-bombardment-compacted sputtered films aside) -- asymmetric bounds
    matching that direction, not a naive +-X% or the ParamSpec fallback's
    generic [0.5x, 2x] (physically implausible on the high side for a
    single-element film). Used by the exporter to emit "molecular.
    density_bounds" so a fit can vary density within a defensible range
    instead of either trusting a wrong fixed value or an unconstrained one."""
    return dict(min=bulk_density_g_cm3 * 0.70, max=bulk_density_g_cm3 * 1.02)


def verified_density_bounds(density_g_cm3: float) -> dict:
    """Zero-width bounds for a DENSITY_VERIFIED value: pins it so a caller
    who naively marks every layer's density as vary=True (physics.py's
    extract_params() auto-generates a density ParamSpec for every layer
    with molecular.density_g_cm3 set, regardless of confidence) can't
    accidentally move a value this pipeline is confident in."""
    return dict(min=density_g_cm3, max=density_g_cm3)


def materials_with_density_state(db, state: str) -> list:
    """Query the live DB (not a static per-batch dict -- any material in
    any batch can land in DENSITY_BULK_APPROXIMATION) for every material
    whose density row's dataset_label matches the given DENSITY_STATE.
    This is the concrete answer to "which layers have an approximated
    density?" -- a real query, not a note a reader has to go looking for.
    `db` is a path/str (a short-lived connection is opened and closed) or
    an existing sqlite3.Connection."""
    import sqlite3
    from pathlib import Path as _Path

    if state not in DENSITY_STATES:
        raise ValueError(f"Unrecognized density state {state!r}. Valid: {DENSITY_STATES}")

    conn = sqlite3.connect(str(db)) if isinstance(db, (str, _Path)) else db
    close_after = isinstance(db, (str, _Path))
    try:
        rows = conn.execute(
            "SELECT DISTINCT m.name, m.formula, p.dataset_label "
            "FROM physical_properties p JOIN materials m ON m.material_id = p.material_id "
            "WHERE p.density_g_cm3 IS NOT NULL"
        ).fetchall()
    finally:
        if close_after:
            conn.close()

    out = []
    for name, formula, dataset_label in rows:
        row_state = density_state_from_source(_extract_density_source(dataset_label))
        if row_state == state:
            out.append(dict(name=name, formula=formula, dataset_label=dataset_label))
    return out


_KNOWN_DENSITY_SOURCES = (BULK_ELEMENTAL_APPROXIMATION, "MP_DFT", "experimental lattice params", "literature")


def _extract_density_source(dataset_label: str) -> Optional[str]:
    """Pull the density_source value back out of a "density_{source}"
    dataset_label segment (see load_oxides_db.py's label_join()). Returns
    None for a label that doesn't contain a recognized density_source at
    all (a genuinely unresolved/unrecognized case, not silently treated
    as verified)."""
    for src in _KNOWN_DENSITY_SOURCES:
        if f"density_{src}" in dataset_label:
            return src
    return None


# ---------------------------------------------------------------------------
# 3. TRACKED_OPEN_TASKS -- known, scoped work that's deliberately not being
# done right now. Lives in the repo, queryable, the same way EXCLUSION_STATE
# and DENSITY_STATE are -- not just a note left in a conversation. A task
# recorded here has a fixed scope and a cost estimate; it stops being
# "tracked" only when it's actually done (remove the entry) or explicitly
# decided against (move it to a "won't do" note with the reason, don't just
# delete it silently).
# ---------------------------------------------------------------------------

TRACKED_OPEN_TASKS = {
    "oxide_amorphous_migration": dict(
        description=(
            "The oxide batch's polymorph=\"amorphous\" (Nb2O5, SiO, SiO2, Ta2O5) is really a "
            "process_condition value (structure:amorphous) sitting in the polymorph slot -- "
            "the same informal shortcut this batch's own As2S3 uses, predating "
            "process_condition's existence. GeO2 is a related, separate inconsistency: it's "
            "FORCE_NO_MP with a literature amorphous/vitreous density but was never labeled "
            "polymorph=\"amorphous\" at all (polymorph=None) -- found while scoping this "
            "task, not previously noticed."
        ),
        affected_materials=["Nb2O5", "SiO", "SiO2", "Ta2O5", "GeO2"],
        affected_call_sites=[
            "scripts/oxide_material_list.py (the 4-5 polymorph fields themselves)",
            "data/step1_selections.json (the ACTUAL load-bearing source for the optical side -- "
            "stores polymorph/effective_polymorph/dataset_label per-axis independently of the "
            "Python module; load_oxides_db.py reads this file, not MATERIALS_50's polymorph "
            "field, for optical_dispersion rows)",
            "scripts/xrr_smoke_test_oxide_db.py (hardcodes "
            "read_layer_by_dataset_label(conn, \"SiO2\", \"amorphous\"))",
            "src/materials_db/calculators/simulate_xrr.py (docstring CLI examples: "
            "\"SiO2[amorphous]:100\")",
            "tests/test_modalfit_export.py::TestExportStackLabelDisambiguation (uses SiO2/"
            "\"amorphous\" as its fixture)",
        ],
        cost_estimate=(
            "Small-to-moderate, not a five-minute edit: no open design questions (unlike "
            "inventing process_condition itself), but requires editing 2 data files + 1 "
            "canonical module, then a MANDATORY full DB rebuild in sequence (load_oxides_db.py's "
            "fresh_db() wipes and recreates the DB from scratch; batch 2 and the pure-element "
            "triage are appended on top and would need re-appending after), plus updating the "
            "3 dependent call sites above, plus a full-suite + full-export re-verification pass. "
            "Contained, half-day scale."
        ),
        blocking_on=None,  # not blocked on anything -- deliberately deferred, not stuck
        status="open",  # "open" | "done" | "wont_do" -- update in place, don't delete silently
    ),
    "mp_density_crosscheck_compounds": dict(
        description=(
            "Ce and Yb (batch 3, pure elements) showed MP_DFT density can diverge from an "
            "independent value by 35-41% -- both lanthanides with documented anomalous valence "
            "behavior, a known hard case for standard DFT exchange-correlation functionals. An "
            "MP_DFT density that has never been cross-checked against anything is not "
            "meaningfully more trustworthy than DENSITY_BULK_APPROXIMATION; it just hasn't been "
            "looked at. Across all 131 currently-loaded materials, 71 have a density row that "
            "is raw, uncrosschecked MP_DFT (55% of the 129 materials with any density at all). "
            "Of those 71: 5 are pure elements (Ag, Ge, Se, Si, Te) -- cross-checked against "
            "periodictable's independent handbook density (a free, already-available second "
            "source for elements): all 5 within 6.1% deviation, none flagged at the 10% "
            "threshold. The other 66 are COMPOUNDS, for which periodictable has no equivalent "
            "compound-density table -- no equally cheap independent source exists. A targeted "
            "spot-check of 6 compounds chosen for the SAME anomalous-valence/complex-magnetism "
            "risk profile as Ce/Yb (Fe3O4, CuO, Dy2O3, Lu2O3, CeF3, LaAlO3) against handbook/"
            "literature values found via web search came back reassuring, not alarming: worst "
            "case CuO at -7.9% (measured tenorite: 6.45 g/cm3 vs. our MP_DFT: 5.938 g/cm3), "
            "Fe3O4 -1.2%, CeF3 +1.2%, Lu2O3 +4.1% -- none near Ce/Yb's 35-41% scale. This is "
            "reassuring for those 6, not proof the other 60 are fine -- it is a spot-check, not "
            "an exhaustive pass."
        ),
        affected_materials=[
            'Al2O3', 'AlN', 'BN', 'BaB2O4', 'BaF2', 'BaTiO3', 'BeAl2O4', 'BeAl6O10', 'BeO',
            'Bi12GeO20', 'CaCO3', 'CaF2', 'CaMoO4', 'CdF2', 'CdS', 'CeF3', 'CsF', 'CsLiB6O10',
            'Cu2O', 'CuO', 'Dy2O3', 'Fe2O3', 'Fe3O4', 'GaN', 'GaS', 'GeS2', 'HfO2', 'KF', 'KNbO3',
            'LaAlO3', 'LaF3', 'LiB3O5', 'LiCaAlF6', 'LiF', 'LiIO3', 'LiNbO3', 'Lu2O3', 'Lu3Al5O12',
            'MgAl2O4', 'MgF2', 'MgO', 'MoO2', 'MoO3', 'NaF', 'Pb5Ge3O11', 'PbF2', 'PbMoO4', 'PbS',
            'RbF', 'Sc2O3', 'SrF2', 'SrMoO4', 'SrTiO3', 'Tb3Ga5O12', 'TeO2', 'ThF4', 'TiO2', 'VO2',
            'WO3', 'Y2O3', 'Y3Al5O12', 'YLiF4', 'YVO4', 'YbF3', 'ZnO', 'ZnS',
        ],  # 66 compounds; the 6 already spot-checked (Fe3O4, CuO, Dy2O3, Lu2O3, CeF3, LaAlO3)
            # are deliberately left IN this list -- a spot-check is not the same as the
            # systematic per-material citation this task is tracking; don't let their presence
            # in a paragraph above be mistaken for them being done.
        cost_estimate=(
            "No cheap, already-available second source exists for compounds the way "
            "periodictable covers elements -- each of the 66 needs an actual literature/"
            "handbook density lookup (a WebSearch or primary-source check per material, similar "
            "effort to a single EXPECTED_SPACEGROUP resolution). Rough scale: 60 remaining "
            "materials x a few minutes each of real verification work, not a bulk/automatable "
            "pass -- a multi-session effort, not a half-day task like the amorphous migration. "
            "Prioritize by DFT-difficulty risk profile first (mixed-valence transition metals, "
            "lanthanide/actinide-containing compounds, magnetic materials -- the same profile "
            "that flagged Ce/Yb) rather than working through the list in an arbitrary order."
        ),
        blocking_on=None,
        status="open",
    ),
}


def open_tasks() -> list:
    """Query: what's tracked as open work right now? Returns task ids
    with status == "open" -- the same "don't leave it in a conversation"
    discipline as EXCLUSION_STATE/DENSITY_STATE."""
    return sorted(k for k, v in TRACKED_OPEN_TASKS.items() if v["status"] == "open")


def task_detail(task_id: str) -> dict:
    if task_id not in TRACKED_OPEN_TASKS:
        raise ValueError(f"Unrecognized task id {task_id!r}. Known: {sorted(TRACKED_OPEN_TASKS)}")
    return TRACKED_OPEN_TASKS[task_id]


# ---------------------------------------------------------------------------
# 4. MP density cross-check -- Ce and Yb (batch 3) showed MP_DFT density can
# diverge from a real independent value by 35-41% (both lanthanides with
# documented anomalous valence behavior, a known hard case for standard DFT
# functionals). An MP_DFT density that has never been cross-checked against
# ANY independent source is not meaningfully more trustworthy than
# DENSITY_BULK_APPROXIMATION -- it just doesn't look that way, because
# nothing has looked. This section makes "how many materials are in that
# position" a real, queryable answer instead of a two-material footnote.
# ---------------------------------------------------------------------------

def materials_with_uncrosschecked_mp_density(db) -> list:
    """Every material whose ONLY density value is raw MP_DFT (no
    EXPERIMENTAL_DENSITY_OVERRIDE, no literature citation, no independent
    cross-check ever performed) -- the same DB-query pattern as
    materials_with_density_state(), because this is a live, growing risk,
    not a fixed list. `db` is a path/str or an existing sqlite3.Connection."""
    import sqlite3
    from pathlib import Path as _Path

    conn = sqlite3.connect(str(db)) if isinstance(db, (str, _Path)) else db
    close_after = isinstance(db, (str, _Path))
    try:
        rows = conn.execute(
            "SELECT DISTINCT m.name, m.formula, p.density_g_cm3, p.dataset_label "
            "FROM physical_properties p JOIN materials m ON m.material_id = p.material_id "
            "WHERE p.density_g_cm3 IS NOT NULL"
        ).fetchall()
    finally:
        if close_after:
            conn.close()

    return [dict(name=name, formula=formula, density_g_cm3=density, dataset_label=dataset_label)
            for name, formula, density, dataset_label in rows
            if "density_MP_DFT" in dataset_label]


def crosscheck_element_density_periodictable(formula: str, db_density_g_cm3: float,
                                              threshold_pct: float = 10.0) -> dict:
    """Cross-check a PURE ELEMENT's density against periodictable's
    built-in handbook bulk density -- a real, free, independent second
    source already available in this repo's dependencies (distinct from
    both MP's DFT calculation and any RI.info-cited thin-film
    measurement). Only meaningful for single-element formulas; raises for
    a compound, where periodictable has no compound-density table (no
    equally cheap independent source exists for compounds -- see
    TRACKED_OPEN_TASKS["mp_density_crosscheck_compounds"]).

    Returns {formula, db_density, periodictable_density, deviation_pct,
    flagged} -- flagged=True when |deviation_pct| exceeds threshold_pct
    (default 10%, chosen to sit comfortably above the ~1-8% scatter
    normal DFT/handbook/thin-film differences show, and far below the
    35-41% Ce/Yb divergence that motivated this check)."""
    import periodictable

    try:
        pt_density = getattr(periodictable, formula).density
    except AttributeError:
        raise ValueError(
            f"'{formula}' is not a recognized single element in periodictable -- "
            f"this cross-check is element-only, not for compounds."
        )
    deviation_pct = 100.0 * (db_density_g_cm3 - pt_density) / pt_density
    return dict(formula=formula, db_density=db_density_g_cm3, periodictable_density=pt_density,
                deviation_pct=deviation_pct, flagged=abs(deviation_pct) > threshold_pct)
