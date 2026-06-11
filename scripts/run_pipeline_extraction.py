"""
Full extraction pipeline:

  1. Accept a target directory of HTML/XML literature files.
  2. Run RefractiveIndexModel + DielectricConstantModel over each file.
  3. Fetch missing InChIKey + CAS numbers for the 23 DB materials via PubChem.
  4. Pass all raw records through the normalize_extracted.py validation layer.
  5. UPSERT valid, normalized records into data/materials_normalized.db.

Usage
-----
  python scripts/run_pipeline_extraction.py <lit_dir>  [--db <path>]  [--dry-run]

  lit_dir   : directory containing .html / .xml files to process
  --db      : path to SQLite database (default: data/materials_normalized.db)
  --dry-run : parse and normalize but skip all DB writes
"""

from __future__ import annotations

import argparse
import os
import sys
import sqlite3
import time
import json
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── dawg shim (Python 3.13 compatibility) ────────────────────────────────────
try:
    import dawg  # noqa: F401
except ImportError:
    import dawg_python as _dp
    sys.modules["dawg"] = _dp

# ── project imports ───────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))   # make `scripts/` importable as package

from scripts.build_extractors import (
    RefractiveIndexModel,
    DielectricConstantModel,
    extract_from_document,
    RawExtractionRecord,
)
from scripts.normalize_extracted import normalize_records, NormalizedRecord

# ── constants ─────────────────────────────────────────────────────────────────

DB_DEFAULT = str(_HERE.parent / "data" / "materials_normalized.db")

DEFAULT_TEMPERATURE_C = 25.0   # applied only when source text is silent

# Source record for PubChem-sourced rows (inserted once)
_PUBCHEM_SOURCE_LABEL = "PubChem REST API"


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — DOCUMENT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _iter_files(lit_dir: Path):
    for ext in ("*.html", "*.htm", "*.xml"):
        yield from lit_dir.glob(ext)


def extract_from_directory(lit_dir: Path) -> list[RawExtractionRecord]:
    from chemdataextractor import Document

    all_raw: list[RawExtractionRecord] = []
    files = list(_iter_files(lit_dir))
    if not files:
        log.warning("No HTML/XML files found in %s", lit_dir)
        return all_raw

    for fpath in files:
        log.info("Extracting from %s", fpath.name)
        try:
            with fpath.open("rb") as fh:
                doc = Document.from_file(fh, models=[RefractiveIndexModel, DielectricConstantModel])
            recs = extract_from_document(doc)
            for r in recs:
                r.source_label = fpath.name
            all_raw.extend(recs)
            log.info("  → %d raw record(s)", len(recs))
        except Exception as exc:
            log.warning("  failed to parse %s: %s", fpath.name, exc)

    log.info("Total raw records extracted: %d", len(all_raw))
    return all_raw


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PUBCHEM IDENTIFIER FETCH
# ══════════════════════════════════════════════════════════════════════════════

def _pubchem_lookup(name: str, delay: float = 0.3) -> dict:
    """
    Query PubChem REST API for a compound by name.
    Returns dict with keys: inchikey, cas_number, smiles, molecular_weight.
    All values are None when PubChem cannot resolve the name.
    No values are invented.
    """
    result = {"inchikey": None, "cas_number": None, "smiles": None, "molecular_weight": None}
    try:
        import pubchempy as pcp
        compounds = pcp.get_compounds(name, "name")
        if not compounds:
            return result
        c = compounds[0]
        result["inchikey"] = getattr(c, "inchikey", None)
        result["smiles"]   = getattr(c, "smiles", None) or getattr(c, "canonical_smiles", None)
        result["molecular_weight"] = getattr(c, "molecular_weight", None)

        # CAS via synonyms endpoint
        syns = pcp.get_synonyms(name, "name")
        if syns:
            cas_pat = __import__("re").compile(r"^\d{2,7}-\d{2}-\d$")
            for syn_group in syns:
                for s in syn_group.get("Synonym", []):
                    if cas_pat.match(s):
                        result["cas_number"] = s
                        break
                if result["cas_number"]:
                    break
        time.sleep(delay)   # be polite to PubChem API
    except Exception as exc:
        log.debug("PubChem lookup failed for %r: %s", name, exc)
    return result


def fetch_missing_identifiers(con: sqlite3.Connection, dry_run: bool = False) -> int:
    """
    For each material in `materials` where inchikey or cas_number is NULL,
    query PubChem and UPSERT the identifiers.  Returns count of rows updated.
    """
    cur = con.execute(
        "SELECT material_id, name FROM materials "
        "WHERE inchikey IS NULL OR cas_number IS NULL"
    )
    rows = cur.fetchall()
    log.info("Materials missing identifiers: %d", len(rows))

    updated = 0
    for mat_id, mat_name in rows:
        log.info("  PubChem lookup: %s", mat_name)
        ids = _pubchem_lookup(mat_name)
        if all(v is None for v in ids.values()):
            log.debug("    → no result for %r", mat_name)
            continue

        changes = {k: v for k, v in ids.items() if v is not None}
        log.info("    → %s", changes)

        if not dry_run:
            for col, val in changes.items():
                if col in ("inchikey", "cas_number", "smiles", "molecular_weight"):
                    con.execute(
                        f"UPDATE materials SET {col} = ? WHERE material_id = ? AND {col} IS NULL",
                        (val, mat_id),
                    )
            con.commit()
            updated += 1

    return updated


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — SCHEMA PATCH: ensure physical_properties has measurement_regime / phase
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_PATCHES = [
    "ALTER TABLE physical_properties ADD COLUMN measurement_regime TEXT",
    "ALTER TABLE physical_properties ADD COLUMN phase TEXT",
]


def apply_schema_patches(con: sqlite3.Connection) -> None:
    for sql in _SCHEMA_PATCHES:
        try:
            con.execute(sql)
            con.commit()
            log.info("Schema patch applied: %s", sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                pass   # already present
            else:
                raise


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — UPSERT NORMALIZED RECORDS
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_material_id(con: sqlite3.Connection, name: str) -> Optional[int]:
    """
    Resolve material name → material_id using exact match, then synonym match.
    Returns None if the material is not in the DB (no new materials inserted).
    """
    row = con.execute(
        "SELECT material_id FROM materials WHERE name = ? COLLATE NOCASE",
        (name,),
    ).fetchone()
    if row:
        return row[0]
    # Try synonyms table
    row = con.execute(
        "SELECT material_id FROM material_synonyms WHERE synonym = ? COLLATE NOCASE",
        (name,),
    ).fetchone()
    return row[0] if row else None


def _ensure_source(con: sqlite3.Connection, label: str) -> int:
    """Get or create a sources row for a given label. Returns source_id."""
    row = con.execute(
        "SELECT source_id FROM sources WHERE title = ?", (label,)
    ).fetchone()
    if row:
        return row[0]
    cur = con.execute(
        "INSERT INTO sources (title) VALUES (?)", (label,)
    )
    con.commit()
    return cur.lastrowid


def _upsert_optical(
    con: sqlite3.Connection,
    mat_id: int,
    rec: NormalizedRecord,
    source_id: int,
) -> bool:
    """
    Insert n into optical_dispersion.
    Skip if a row with the same material_id + wavelength_nm + source_id exists.
    temperature_c defaults to 25.0 when text was silent (per task spec).
    """
    wl = rec.wavelength_nm
    if wl is None:
        log.debug("  optical skip (no wavelength): %s n=%s", rec.material_name, rec.value)
        return False

    t_c = rec.temperature_c if rec.temperature_c is not None else DEFAULT_TEMPERATURE_C

    existing = con.execute(
        "SELECT record_id FROM optical_dispersion "
        "WHERE material_id=? AND wavelength_nm=? AND source_id=?",
        (mat_id, wl, source_id),
    ).fetchone()
    if existing:
        log.debug("  optical skip (duplicate): %s wl=%s", rec.material_name, wl)
        return False

    con.execute(
        """
        INSERT INTO optical_dispersion
          (material_id, wavelength_nm, n, temperature_c, dataset_label,
           raw_record_table, raw_record_id, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (mat_id, wl, rec.value, t_c,
         rec.source_label or _PUBCHEM_SOURCE_LABEL,
         "run_pipeline_extraction", None, source_id),
    )
    return True


def _upsert_physical(
    con: sqlite3.Connection,
    mat_id: int,
    rec: NormalizedRecord,
    source_id: int,
) -> bool:
    """
    Insert dielectric_constant into physical_properties.
    Skip exact duplicates (same material_id + dielectric_constant + regime + phase).
    """
    t_c = rec.temperature_c if rec.temperature_c is not None else DEFAULT_TEMPERATURE_C

    existing = con.execute(
        """
        SELECT record_id FROM physical_properties
        WHERE material_id=?
          AND dielectric_constant=?
          AND COALESCE(measurement_regime,'') = COALESCE(?,'')
          AND COALESCE(phase,'') = COALESCE(?,'')
          AND source_id=?
        """,
        (mat_id, rec.value, rec.measurement_regime, rec.phase, source_id),
    ).fetchone()
    if existing:
        log.debug("  physical skip (duplicate): %s eps=%s", rec.material_name, rec.value)
        return False

    con.execute(
        """
        INSERT INTO physical_properties
          (material_id, dielectric_constant, temperature_c, frequency_hz,
           wavelength_nm, measurement_regime, phase,
           dataset_label, raw_record_table, raw_record_id, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mat_id, rec.value, t_c, rec.frequency_hz, rec.wavelength_nm,
            rec.measurement_regime, rec.phase,
            rec.source_label or _PUBCHEM_SOURCE_LABEL,
            "run_pipeline_extraction", None, source_id,
        ),
    )
    return True


def upsert_normalized_records(
    con: sqlite3.Connection,
    records: list[NormalizedRecord],
    dry_run: bool = False,
) -> dict:
    stats = {"inserted": 0, "skipped_dup": 0, "skipped_invalid": 0,
             "skipped_unknown_material": 0, "rejected_physics": 0}

    for rec in records:
        if not rec.is_valid:
            stats["rejected_physics"] += 1
            log.debug("  rejected: %s %s=%s reason=%s",
                      rec.material_name, rec.property_type, rec.value, rec.rejection_reason)
            continue

        mat_id = _resolve_material_id(con, rec.material_name)
        if mat_id is None:
            stats["skipped_unknown_material"] += 1
            log.debug("  unknown material: %r", rec.material_name)
            continue

        src_label = rec.source_label or _PUBCHEM_SOURCE_LABEL
        if dry_run:
            log.info("[DRY-RUN] would insert %s=%s for %s (src=%s)",
                     rec.property_type, rec.value, rec.material_name, src_label)
            stats["inserted"] += 1
            continue

        source_id = _ensure_source(con, src_label)

        if rec.property_type == "n":
            inserted = _upsert_optical(con, mat_id, rec, source_id)
        elif rec.property_type == "dielectric_constant":
            inserted = _upsert_physical(con, mat_id, rec, source_id)
        else:
            stats["skipped_invalid"] += 1
            continue

        if inserted:
            stats["inserted"] += 1
        else:
            stats["skipped_dup"] += 1

    if not dry_run:
        con.commit()

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("lit_dir", nargs="?", default=None,
                   help="Directory of HTML/XML literature files (optional; "
                        "skip to run only PubChem identifier fetch)")
    p.add_argument("--db", default=DB_DEFAULT, help="Path to SQLite DB")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse and normalize but do not write to DB")
    p.add_argument("--skip-pubchem", action="store_true",
                   help="Skip PubChem identifier resolution")
    p.add_argument("--skip-extraction", action="store_true",
                   help="Skip CDE literature extraction (identifier fetch only)")
    return p.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        log.error("Database not found: %s", db_path)
        sys.exit(1)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    # ── schema patch: add measurement_regime / phase columns if absent ────────
    if not args.dry_run:
        apply_schema_patches(con)

    # ── STEP A: PubChem identifier fetch ──────────────────────────────────────
    if not args.skip_pubchem:
        log.info("=== PubChem identifier fetch ===")
        n_updated = fetch_missing_identifiers(con, dry_run=args.dry_run)
        log.info("Materials updated with identifiers: %d", n_updated)

    # ── STEP B: Literature extraction + normalization + UPSERT ───────────────
    if not args.skip_extraction:
        if args.lit_dir is None:
            log.info("No lit_dir given; skipping CDE extraction.")
        else:
            lit_dir = Path(args.lit_dir)
            if not lit_dir.is_dir():
                log.error("lit_dir is not a directory: %s", lit_dir)
                sys.exit(1)

            log.info("=== CDE extraction from %s ===", lit_dir)
            raw_records = extract_from_directory(lit_dir)

            log.info("=== Normalization ===")
            norm_records = normalize_records(raw_records)

            n_valid   = sum(1 for r in norm_records if r.is_valid)
            n_invalid = len(norm_records) - n_valid
            log.info("  valid: %d  rejected: %d", n_valid, n_invalid)
            for r in norm_records:
                if not r.is_valid:
                    log.debug("  REJECTED %s %s=%s — %s",
                              r.material_name, r.property_type, r.value, r.rejection_reason)
                elif r.flags:
                    log.info("  FLAG %s %s=%s — %s",
                             r.material_name, r.property_type, r.value, r.flags)

            log.info("=== DB UPSERT ===")
            stats = upsert_normalized_records(con, norm_records, dry_run=args.dry_run)
            log.info("  inserted:              %d", stats["inserted"])
            log.info("  skipped (duplicate):   %d", stats["skipped_dup"])
            log.info("  skipped (unknown mat): %d", stats["skipped_unknown_material"])
            log.info("  rejected (physics):    %d", stats["rejected_physics"])

    con.close()
    log.info("Pipeline complete.")


if __name__ == "__main__":
    main()
