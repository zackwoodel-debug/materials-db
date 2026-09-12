"""launcher/catalog.py
======================
DB browsing for the ModalFit launcher: search/list materials with their
density confidence visible at selection time, and named exclusions marked
unselectable -- the SAME interface for picking a film layer or a
substrate, per the launcher's design (a substrate is "a layer with
role=substrate", nothing more special than that -- see export/modalfit.py).

Reuses export/modalfit.py's own polymorph-prefix and density-confidence
logic directly (rather than re-deriving it) so this can never silently
drift from what export_layer()/export_stack() actually do at export time
-- the same reasoning export_stack() itself gives for reusing its own
label-resolution helpers instead of a second copy.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from materials_db.export.modalfit import (
    KNOWN_EXCLUSIONS, _density_confidence, _polymorph_prefix,
)
from materials_db.pipeline.process_condition import DENSITY_BULK_APPROXIMATION


def _connect(db):
    conn = sqlite3.connect(str(db)) if isinstance(db, (str, Path)) else db
    close_after = isinstance(db, (str, Path))
    return conn, close_after


def list_materials(db, query: Optional[str] = None) -> list:
    """One dict per (material, polymorph) -- the real selectable unit,
    since a material with 2+ polymorphs needs a dataset_label to
    disambiguate at export time (export_layer()'s own rule). Each dict:

      material_id, name, formula, polymorph (may be None),
      density_g_cm3, density_confidence ("verified"/"bulk_approximation"/
      "unresolved"), selectable (bool), exclusion_reason (str or None).

    `query` filters case-insensitively on name OR formula substring
    (None/"" returns everything). Named exclusions (KNOWN_EXCLUSIONS,
    keyed by formula -- the same list export_all_materials_modalfit.py
    asserts its skip set against) are INCLUDED in the result but marked
    selectable=False with the real reason, rather than silently hidden --
    a caller searching for "Gadolinium" should see why GdF3 doesn't come
    up as a choice, not wonder if the search is broken."""
    conn, close_after = _connect(db)
    try:
        rows = conn.execute(
            "SELECT m.material_id, m.name, m.formula, p.dataset_label, p.density_g_cm3 "
            "FROM materials m LEFT JOIN physical_properties p "
            "ON p.material_id = m.material_id AND p.density_g_cm3 IS NOT NULL"
        ).fetchall()
    finally:
        if close_after:
            conn.close()

    by_material = {}
    for material_id, name, formula, dataset_label, density in rows:
        by_material.setdefault((material_id, name, formula), []).append((dataset_label, density))

    out = []
    for (material_id, name, formula), density_rows in by_material.items():
        if query and query.lower() not in name.lower() and query.lower() not in formula.lower():
            continue

        exclusion_reason = KNOWN_EXCLUSIONS.get(formula)
        if exclusion_reason is not None:
            out.append(dict(material_id=material_id, name=name, formula=formula, polymorph=None,
                             density_g_cm3=None, density_confidence=None,
                             selectable=False, exclusion_reason=exclusion_reason))
            continue

        by_polymorph = {}
        for dataset_label, density in density_rows:
            if dataset_label is None:
                continue
            poly = _polymorph_prefix(dataset_label)
            if density is not None:
                by_polymorph[poly] = (dataset_label, density)

        for poly, (dataset_label, density) in sorted(by_polymorph.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
            out.append(dict(
                material_id=material_id, name=name, formula=formula, polymorph=poly,
                density_g_cm3=density, density_confidence=_density_confidence(dataset_label),
                selectable=True, exclusion_reason=None,
            ))

    out.sort(key=lambda r: (r["name"], r["polymorph"] or ""))
    return out


def describe_row(row: dict) -> str:
    """One-line CLI display for a list_materials() row, density confidence
    always visible -- the requirement this whole module exists to satisfy:
    a caller must see bulk_approximation (or a named exclusion) BEFORE
    picking a material, not discover it in the exported JSON afterward."""
    if not row["selectable"]:
        return f"{row['name']} ({row['formula']}) -- EXCLUDED: {row['exclusion_reason']}"
    poly = f" [{row['polymorph']}]" if row["polymorph"] else ""
    flag = " *** BULK_APPROXIMATION density ***" if row["density_confidence"] == DENSITY_BULK_APPROXIMATION else ""
    return (f"{row['name']} ({row['formula']}){poly} -- "
            f"density {row['density_g_cm3']:.4f} g/cm3, {row['density_confidence']}{flag}")
