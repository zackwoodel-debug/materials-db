"""Invariants of the published database: each has a name, a rationale, a severity and a check. FAIL invariants block a release
(scripts/build_release.py validation stage); WARN invariants are reported (release MANIFEST and data card, core.audit for the
legacy DB). INVARIANTS.md is generated from this registry (scripts/write_invariants_md.py); tests/test_invariants.py proves each
FAIL check catches a planted violation and that the newest local release passes.

Reuses existing definitions instead of restating them: density states from materials_db.pipeline.process_condition, and the
reviewed negative-k allow-list passed in by the caller (scripts/build_release.py NEGATIVE_K_ALLOWED).
"""
import collections
import unicodedata
from dataclasses import dataclass
from typing import Callable

from materials_db.pipeline.process_condition import DENSITY_UNRESOLVED, _extract_density_source, density_state_from_source

FAIL, WARN = "FAIL", "WARN"


@dataclass(frozen=True)
class Invariant:
    name: str
    group: str  # A provenance, B physical sanity, D identity, L legacy
    severity: str
    rationale: str
    check: Callable  # (conn, context) -> list of violation strings (empty = holds)
    scope: str = "release"  # "release" or "legacy" (data/materials.db)


def _rows(conn, sql):
    return conn.execute(sql).fetchall()


def _unsourced(table):
    def check(conn, ctx):
        n = _rows(conn, f"SELECT COUNT(*) FROM {table} WHERE source_id IS NULL")[0][0]
        return [f"{n} {table} rows have no source_id"] if n else []
    return check


def _dangling(table):
    def check(conn, ctx):
        n = _rows(conn, f"SELECT COUNT(*) FROM {table} t LEFT JOIN sources s ON s.source_id = t.source_id "
                        "WHERE t.source_id IS NOT NULL AND s.source_id IS NULL")[0][0]
        return [f"{n} {table} rows cite a source_id that is not in sources"] if n else []
    return check


def _sources_without_locator(conn, ctx):
    rows = _rows(conn, "SELECT source_id, title FROM sources WHERE COALESCE(doi, '') = '' AND COALESCE(url, '') = ''")
    return [f"source {sid} has neither DOI nor URL: {title!r}" for sid, title in rows]


def _density_states(conn, ctx):
    bad = [label for (label,) in _rows(conn, "SELECT dataset_label FROM physical_properties WHERE density_g_cm3 IS NOT NULL")
           if density_state_from_source(_extract_density_source(label or "")) == DENSITY_UNRESOLVED]
    return [f"{len(bad)} density rows map to no recognized density state, e.g. {bad[:3]}"] if bad else []


def _n_positive(conn, ctx):
    n = _rows(conn, "SELECT COUNT(*) FROM optical_dispersion WHERE n IS NULL OR n <= 0 OR n != n OR ABS(n) > 1e300")[0][0]
    return [f"{n} optical rows have n <= 0, NULL or non-finite"] if n else []


def _negative_k_allow_listed(conn, ctx):
    allowed = ctx.get("negative_k_allowed", {})
    out = []
    for name, label, kmin in _rows(conn, "SELECT m.name, o.dataset_label, MIN(o.k) FROM optical_dispersion o "
                                         "JOIN materials m USING (material_id) WHERE o.k < 0 GROUP BY 1, 2"):
        floor = allowed.get((name, label))
        if floor is None:
            out.append(f"{name} / {label}: k down to {kmin}, not on the reviewed allow-list")
        elif kmin < floor:
            out.append(f"{name} / {label}: k down to {kmin}, below its allowed floor {floor}")
    return out


def _wavelength_positive(conn, ctx):
    n = _rows(conn, "SELECT COUNT(*) FROM optical_dispersion WHERE wavelength_nm IS NULL OR wavelength_nm <= 0 "
                    "OR wavelength_nm != wavelength_nm OR ABS(wavelength_nm) > 1e300")[0][0]
    return [f"{n} optical rows have a wavelength <= 0, NULL or non-finite"] if n else []


def _unique_ids(conn, ctx):
    n = _rows(conn, "SELECT COUNT(*) - COUNT(DISTINCT material_id) FROM materials")[0][0]
    return [f"{n} duplicate material_id values"] if n else []


def _unique_names(conn, ctx):
    norm = collections.Counter(unicodedata.normalize("NFKC", " ".join(name.split())).casefold()
                               for (name,) in _rows(conn, "SELECT name FROM materials"))
    return [f"names collide after normalization: {k!r}" for k, v in norm.items() if v > 1]


def _legacy_unsourced(conn, ctx):
    out = []
    present = {name for (name,) in _rows(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    for table in ("calculated_slds", "dielectrics", "calculated_sld", "dielectric"):
        if table in present:
            n = _rows(conn, f"SELECT COUNT(*) FROM {table} WHERE reference_id IS NULL")[0][0]
            if n:
                out.append(f"{n} {table} rows have no reference_id")
    return out


INVARIANTS = [
    Invariant("optical_rows_have_a_source", "A", FAIL, "Every n,k value must be traceable to the paper or page it came from.",
              _unsourced("optical_dispersion")),
    Invariant("physical_rows_have_a_source", "A", FAIL, "Every density, SLD and dielectric value must be traceable to its origin.",
              _unsourced("physical_properties")),
    Invariant("optical_sources_exist", "A", FAIL, "A cited source must exist; a dangling id is provenance that cannot be followed.",
              _dangling("optical_dispersion")),
    Invariant("physical_sources_exist", "A", FAIL, "As above, for physical properties.", _dangling("physical_properties")),
    Invariant("density_has_a_known_state", "A", FAIL,
              "Every density is verified or a bulk approximation (process_condition DENSITY_STATE); an unclassified density "
              "would hide whether it describes the measured sample.", _density_states),
    Invariant("sources_have_a_locator", "A", WARN,
              "A source should carry a DOI or URL so a reader can find it; reports, datasheets and handbooks often have neither.",
              _sources_without_locator),
    Invariant("n_is_positive_and_finite", "B", FAIL, "A refractive index must be a finite positive number.", _n_positive),
    Invariant("negative_k_only_where_reviewed", "B", FAIL,
              "k < 0 is unphysical for a passive medium; it is allowed only as reviewed measurement noise, per dataset, down "
              "to a recorded floor (build_release.NEGATIVE_K_ALLOWED).", _negative_k_allow_listed),
    Invariant("wavelength_is_positive_and_finite", "B", FAIL, "Wavelengths are stored in nm and must be finite and positive.",
              _wavelength_positive),
    Invariant("material_ids_are_unique", "D", FAIL, "A material id names one material.", _unique_ids),
    Invariant("material_names_are_unique_after_normalization", "D", FAIL,
              "Two materials whose names differ only in case, spacing or Unicode form would make a name lookup ambiguous.",
              _unique_names),
    Invariant("legacy_rows_have_a_reference", "L", WARN,
              "The legacy data/materials.db SLD and dielectric tables should cite a reference; rows without one are kept, "
              "flagged, and never silently attributed (docs/adr/0002).", _legacy_unsourced, scope="legacy"),
]


def evaluate(conn, scope="release", context=None):
    """[(invariant, violations)] for every invariant of the scope, in registry order."""
    ctx = context or {}
    return [(inv, inv.check(conn, ctx)) for inv in INVARIANTS if inv.scope == scope]


def failures(results):
    return [(inv, v) for inv, v in results if v and inv.severity == FAIL]


def summary(results):
    """JSON-able {name: {severity, holds, violations (count), example}} for a manifest or a report."""
    return {inv.name: dict(severity=inv.severity, holds=not v, violations=len(v), example=v[0] if v else None)
            for inv, v in results}
