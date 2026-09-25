#!/usr/bin/env python3
"""
scripts/load_family_db.py
==========================
Family-parameterized loader: {family, catalog CSV, selections JSON, output DB}.
Extracted from scripts/load_oxides_db.py (which is now a thin wrapper).

Schema is frozen pending Aiden's approval: no new columns. Polymorph, optical
axis and SLD real-vs-imaginary distinctions live in the existing `dataset_label`
text column as "polymorph | source_or_quantity | axis".

Catalog CSV: required columns `name`, `formula` (formula may be NULL only with allow_null_formula, used by the polymer
family; then a `selection_key` column is required); optional `polymorph`, PubChem
columns and the density/SLD columns used by load_physical_properties. The
selections JSON is keyed by `selection_key` (a catalog column) if present, else
by `formula`; it must be unique per catalog row.

Selection states: a dict with a non-empty `axes` list -> optical data is loaded.
A missing key, `null`, or a dict without `axes` (e.g. only `candidates`) is an
unresolved/ambiguous match -> optical load is SKIPPED and reported, never
auto-picked. A dict with `"deferred": true` is a deliberate deferral: the whole material is skipped (zero rows) and listed
under report.deferred; it is not a warning and does not fail --strict.

Idempotent: a rerun against an existing DB adds zero logical rows. Conflicting
values are kept side by side (physical rows) or left untouched (materials /
optical) and reported; nothing is silently overwritten.

Block-boundary duplicates (opt-in, --collapse-block-duplicates): when an RI.info file gives n by a formula block AND by a tabulated
block, parse_file emits a row from each at a shared wavelength (n differs ~1e-5). With the flag, the TABULATED row (the source's own
n,k) is kept and the formula-sampled row dropped; every drop is recorded in report.collapsed with both n values. Anything that cannot
be identified this way is left alone and warned. Default off: oxide/nitride output is unchanged.

Modes: --fresh (delete + rebuild DB), --dry-run (runs on an in-memory copy, writes
nothing), --strict (any conflict/skip/warning aborts and rolls back), --report PATH
(JSON report). All writes happen in one transaction; any error rolls back.
"""

import argparse
import collections
import html
import json
import math
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
import materials_db.pipeline.fetch_optical_data as _fetch_optical_data  # noqa: E402
from materials_db.pipeline.fetch_optical_data import parse_file  # noqa: E402

_fetch_optical_data.WL_MIN_NM = 0.01
_fetch_optical_data.WL_MAX_NM = 2_000_000.0

SCHEMA_PATH = _ROOT / "updated_sql_schema.sql"
RI_DATA_ROOT = _ROOT / "refractiveindex_db" / "database" / "data"

XRAY_ENERGY_EV = 8048.0
XRAY_WAVELENGTH_NM = 0.15406
NEUTRON_WAVELENGTH_NM = 0.1798

PREEXISTING_SOURCE_KEY = "__preexisting_max_source_id__"
MATERIAL_FIELDS = ("formula", "smiles", "inchikey", "molecular_weight", "cas_number", "pubchem_cid")


class CatalogError(ValueError):
    """Malformed, empty or duplicated catalog/selections input."""


class StrictError(RuntimeError):
    """--strict: the run produced conflicts, skips or warnings."""


class Report:
    def __init__(self, family):
        self.family = family
        self.inserted = {"materials": 0, "physical_properties": 0, "optical_dispersion": 0, "sources": 0}
        self.unchanged = {"materials": 0, "physical_properties": 0, "optical_dispersion": 0}
        self.conflicts, self.skipped, self.warnings, self.notes, self.deferred = [], [], [], [], []
        self.collapsed = []

    def to_dict(self):
        return dict(family=self.family, inserted=self.inserted, unchanged=self.unchanged,
                    conflicts=self.conflicts, skipped=self.skipped, warnings=self.warnings, notes=self.notes,
                    deferred=self.deferred, collapsed=self.collapsed)


# ---------------------------------------------------------------------------
# input validation
# ---------------------------------------------------------------------------

def _clean(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v) else v


def load_catalog(path, allow_null_formula=False) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise CatalogError(f"catalog not found: {path}")
    try:
        df = pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
        raise CatalogError(f"catalog unreadable ({path.name}): {e}") from e
    if df.empty:
        raise CatalogError(f"catalog has no rows: {path.name}")
    required = {"name"} if allow_null_formula else {"name", "formula"}
    missing = required - set(df.columns)
    if missing:
        raise CatalogError(f"catalog {path.name} missing required columns: {sorted(missing)}")
    if allow_null_formula:
        if "formula" not in df.columns:
            df["formula"] = None
        if "selection_key" not in df.columns:
            raise CatalogError(f"catalog {path.name}: a selection_key column is required when formulas may be NULL")
    for col in ("name",) if allow_null_formula else ("name", "formula"):
        blank = df[df[col].isna() | (df[col].astype(str).str.strip() == "")]
        if len(blank):
            raise CatalogError(f"catalog {path.name}: blank {col} in row(s) {list(blank.index + 2)}")
    if "selection_key" not in df.columns:
        df["selection_key"] = df["formula"]
    blank_key = df[df["selection_key"].isna() | (df["selection_key"].astype(str).str.strip() == "")]
    if len(blank_key):
        raise CatalogError(f"catalog {path.name}: blank selection_key in row(s) {list(blank_key.index + 2)}")
    for col in ("name", "selection_key"):
        dup = df[df[col].duplicated(keep=False)][col].unique().tolist()
        if dup:
            raise CatalogError(f"catalog {path.name}: duplicate {col}: {dup}")
    if "inchikey" in df.columns:
        dup = df["inchikey"].dropna()
        dup = dup[dup.duplicated(keep=False)].unique().tolist()
        if dup:
            raise CatalogError(f"catalog {path.name}: duplicate inchikey (one materials row per compound; "
                               f"put polymorphs in dataset_label): {dup}")
    return df


def load_selections(path) -> dict:
    path = Path(path)
    try:
        sel = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CatalogError(f"selections unreadable ({path.name}): {e}") from e
    if not isinstance(sel, dict):
        raise CatalogError(f"selections {path.name} must be a JSON object keyed by selection_key")
    return sel


# ---------------------------------------------------------------------------
# helpers moved from load_oxides_db.py
# ---------------------------------------------------------------------------

def parse_ri_references(data_path: str) -> dict:
    p = RI_DATA_ROOT / data_path
    raw = yaml.safe_load(open(p))
    refs = raw.get("REFERENCES") or ""
    if isinstance(refs, list):
        refs = " | ".join(str(r) for r in refs)
    refs = str(refs)

    doi = None
    m = re.search(r"doi\.org/([^\s\"<>]+)", refs)
    if m:
        doi = m.group(1).rstrip(".,")

    url = None
    m2 = re.search(r'href="([^"]+)"', refs)
    if m2:
        url = html.unescape(m2.group(1))

    plain = re.sub(r"<[^>]+>", "", refs)
    plain = html.unescape(plain)
    lines = [l.strip().lstrip("0123456789) ").strip() for l in plain.splitlines() if l.strip()]
    authors = lines[0] if lines else None
    title = lines[1] if len(lines) > 1 else None

    year = None
    ym = re.search(r"\((\d{4})\)", plain)
    if ym:
        year = int(ym.group(1))

    return dict(doi=doi, url=url, authors=authors, title=title, year=year, notes=plain[:1000])


def get_or_create_source(conn, cache: dict, key, **fields) -> int:
    if key in cache:
        return cache[key]
    if fields.get("doi"):
        row = conn.execute("SELECT source_id FROM sources WHERE doi = ?", (fields["doi"],)).fetchone()
        if row:
            cache[key] = row[0]
            return row[0]
    elif cache.get(PREEXISTING_SOURCE_KEY) is not None:
        # DOI-less source: on a rerun, reuse a source row from BEFORE this run (never one created earlier in
        # the same run, so a fresh load still creates one row per dataset exactly as before).
        row = conn.execute(
            "SELECT MIN(source_id) FROM sources WHERE doi IS NULL AND source_id <= ? AND title IS ? AND authors IS ? "
            "AND year IS ? AND technique IS ? AND url IS ? AND notes IS ?",
            (cache[PREEXISTING_SOURCE_KEY], fields.get("title"), fields.get("authors"), fields.get("year"),
             fields.get("technique"), fields.get("url"), fields.get("notes"))).fetchone()
        if row and row[0] is not None:
            cache[key] = row[0]
            return row[0]
    cur = conn.execute(
        "INSERT INTO sources (doi, title, authors, journal, year, technique, url, uncertainty, notes) "
        "VALUES (:doi, :title, :authors, :journal, :year, :technique, :url, :uncertainty, :notes)",
        dict(doi=fields.get("doi"), title=fields.get("title"), authors=fields.get("authors"),
             journal=fields.get("journal"), year=fields.get("year"), technique=fields.get("technique"),
             url=fields.get("url"), uncertainty=fields.get("uncertainty"), notes=fields.get("notes")),
    )
    cache[key] = cur.lastrowid
    return cur.lastrowid


def get_or_create_named_source(conn, cache, key, title, **fields) -> int:
    """Idempotent source creation for sources with no DOI: match on (title, technique)."""
    if key in cache:
        return cache[key]
    row = conn.execute("SELECT source_id FROM sources WHERE doi IS NULL AND title = ? AND technique IS ?",
                       (title, fields.get("technique"))).fetchone()
    if row:
        cache[key] = row[0]
        return row[0]
    return get_or_create_source(conn, cache, key, title=title, **fields)


def label_join(polymorph, *parts) -> str:
    segs = [polymorph] if polymorph else []
    segs += [p for p in parts if p]
    return " | ".join(segs)


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    except (TypeError, ValueError):
        return a == b


def _insert_physical(conn, report, material_id, label, source_id, **cols):
    """Insert one physical_properties row unless an identical one exists.
    Same (material, label, source) with a different value is kept alongside and reported."""
    keys = sorted(cols)
    rows = conn.execute(
        f"SELECT {', '.join(keys)} FROM physical_properties WHERE material_id=? AND dataset_label=? AND source_id=?",
        (material_id, label, source_id)).fetchall()
    for r in rows:
        if all(_same(r[i], cols[k]) for i, k in enumerate(keys)):
            report.unchanged["physical_properties"] += 1
            return
    if rows:
        report.conflicts.append(dict(kind="physical_value", material_id=material_id, dataset_label=label,
                                     existing=[dict(zip(keys, r)) for r in rows], new=cols,
                                     action="kept both"))
    conn.execute(
        f"INSERT INTO physical_properties (material_id, {', '.join(keys)}, dataset_label, source_id) "
        f"VALUES (?, {', '.join('?' * len(keys))}, ?, ?)",
        (material_id, *[cols[k] for k in keys], label, source_id))
    report.inserted["physical_properties"] += 1


def collapse_block_duplicates(data_path, wl_nm, n_val, report):
    """Indices to keep after resolving formula-vs-tabulated duplicates at a shared wavelength (see module docstring)."""
    groups = collections.defaultdict(list)
    for i, w in enumerate(wl_nm):
        groups[round(float(w), 6)].append(i)
    dup = {w: ix for w, ix in groups.items() if len(ix) > 1}
    if not dup:
        return list(range(len(wl_nm)))
    table = {}
    for b in yaml.safe_load(open(RI_DATA_ROOT / data_path)).get("DATA", []):
        if b.get("type") in ("tabulated nk", "tabulated n"):
            for line in b["data"].strip().splitlines():
                c = line.split()
                if c:
                    table[round(float(c[0]) * 1000.0, 6)] = float(c[1])
    drop = set()
    for w, ix in sorted(dup.items()):
        tab_n = table.get(w)
        cand = [i for i in ix if tab_n is not None and abs(float(n_val[i]) - tab_n) < 1e-9]
        if len(cand) != 1:  # cannot tell which row is the tabulated one: leave both, say so
            report.warnings.append(dict(kind="unresolved_duplicate_wavelength", data_path=data_path, wavelength_nm=w,
                                        n_values=[float(n_val[i]) for i in ix], action="left as is"))
            continue
        keep = cand[0]
        for i in ix:
            if i != keep:
                drop.add(i)
                report.collapsed.append(dict(data_path=data_path, wavelength_nm=w, kept="tabulated", kept_n=float(n_val[keep]),
                                             dropped="formula-sampled", dropped_n=float(n_val[i]),
                                             delta_n=float(n_val[keep]) - float(n_val[i]), dropped_raw_record_id=i))
    return [i for i in range(len(wl_nm)) if i not in drop]


def load_optical_axis(conn, material_id, source_id, axis_entry, effective_polymorph, report=None,
                      collapse_block_duplicates_flag=False):
    report = report or Report("adhoc")
    data_path = axis_entry["data_path"]
    dataset_label = axis_entry["dataset_label"]
    wl_nm, n_val, k_val, refs, temp_c = parse_file(RI_DATA_ROOT / data_path)
    if temp_c is None and axis_entry.get("temperature_c") is not None:
        temp_c = float(axis_entry["temperature_c"])  # stated in the page text ("293 K (20 degC)"); only families whose matcher records it
    keep = collapse_block_duplicates(data_path, wl_nm, n_val, report) if collapse_block_duplicates_flag else list(range(len(wl_nm)))
    total = len(keep)

    have, lo, hi = conn.execute(
        "SELECT COUNT(*), MIN(material_id), MAX(material_id) FROM optical_dispersion WHERE raw_record_table = ?",
        (data_path,)).fetchone()
    if have:
        if lo == hi == material_id and have == total:
            report.unchanged["optical_dispersion"] += have
        else:
            report.conflicts.append(dict(kind="optical_dataset", data_path=data_path, material_id=material_id,
                                         existing_rows=have, expected_rows=total, existing_material_ids=[lo, hi],
                                         action="left untouched"))
        return 0
    # Dedupe key (material, source, dataset_label): the same dataset arriving from a DIFFERENT data file must never be
    # inserted a second time. Enforced here, not in the schema (schema is frozen).
    dup = conn.execute(
        "SELECT COUNT(*), GROUP_CONCAT(DISTINCT raw_record_table) FROM optical_dispersion "
        "WHERE material_id = ? AND source_id = ? AND dataset_label IS ?", (material_id, source_id, dataset_label)).fetchone()
    if dup[0]:
        report.conflicts.append(dict(kind="optical_duplicate_key", material_id=material_id, source_id=source_id,
                                     dataset_label=dataset_label, existing_rows=dup[0], existing_data_files=dup[1],
                                     new_data_file=data_path, action="not inserted; existing rows kept"))
        return 0

    for i in keep:  # i is parse_file's row index, kept as raw_record_id for traceability
        n = float(n_val[i])
        k = None
        if k_val is not None and not np.isnan(k_val[i]):
            k = float(k_val[i])
        conn.execute(
            "INSERT INTO optical_dispersion "
            "(material_id, wavelength_nm, n, k, temperature_c, dataset_label, raw_record_table, raw_record_id, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (material_id, float(wl_nm[i]), n, k, temp_c, dataset_label, data_path, i, source_id),
        )
    report.inserted["optical_dispersion"] += total
    return total


def load_physical_properties(conn, material_id, row, mp_source_id, literature_source_id, periodictable_source_id,
                             effective_polymorph, source_cache=None, get_source_fn=None, report=None,
                             catalog_name="oxides_50.csv"):
    report = report or Report("adhoc")
    density = row.get("density_g_cm3")
    density_source = row.get("density_source")
    # a liquid's density is only meaningful at its temperature: families that state it get it on the density and SLD rows
    at_t = {"temperature_c": float(row["density_temperature_c"])} if pd.notna(row.get("density_temperature_c")) else {}

    if pd.notna(density):
        citation_doi = row.get("density_citation_doi")
        citation_title = row.get("density_citation_title")
        if (pd.notna(citation_doi) or pd.notna(citation_title)) and source_cache is not None and get_source_fn is not None:
            technique = ("DFT (Materials Project)" if density_source == "MP_DFT" else
                         "experimental crystallography" if density_source == "experimental lattice params" else "literature")
            extra = row.get("density_citation_notes")
            src = get_source_fn(
                conn, source_cache, citation_doi if pd.notna(citation_doi) else citation_title,
                doi=citation_doi if pd.notna(citation_doi) else None,
                title=citation_title,
                authors=row.get("density_citation_authors"),
                journal=row.get("density_citation_journal"),
                year=int(row["density_citation_year"]) if pd.notna(row.get("density_citation_year")) else None,
                technique=technique,
                notes=f"Cited for {row['formula']} density ({density} g/cm3, density_source={density_source}). "
                      f"See flags column in data/{catalog_name} for the specific calculation/value."
                      + (f" {extra}" if pd.notna(extra) else ""),
            )
        else:
            src = mp_source_id if density_source == "MP_DFT" else literature_source_id
        _insert_physical(conn, report, material_id, label_join(effective_polymorph, f"density_{density_source}"),
                         src, density_g_cm3=float(density), **at_t)

    for col in ("xray_sld_real", "xray_sld_imag"):
        if pd.notna(row.get(col)):
            _insert_physical(conn, report, material_id,
                             label_join(effective_polymorph, col, "periodictable_CuKalpha"),
                             periodictable_source_id, xray_sld=float(row[col]),
                             energy_ev=XRAY_ENERGY_EV, wavelength_nm=XRAY_WAVELENGTH_NM, **at_t)
    for col in ("neutron_sld_real", "neutron_sld_imag"):
        if pd.notna(row.get(col)):
            _insert_physical(conn, report, material_id,
                             label_join(effective_polymorph, col, "periodictable_thermal"),
                             periodictable_source_id, neutron_sld=float(row[col]),
                             wavelength_nm=NEUTRON_WAVELENGTH_NM, **at_t)


# ---------------------------------------------------------------------------
# material upsert
# ---------------------------------------------------------------------------

def upsert_material(conn, report, row):
    """Return (material_id, is_new), or (None, False) if the row collides and must be skipped."""
    vals = dict(
        formula=_clean(row.get("formula")),
        smiles=_clean(row.get("smiles")),
        inchikey=_clean(row.get("inchikey")),
        molecular_weight=float(row["molecular_weight"]) if _clean(row.get("molecular_weight")) is not None else None,
        cas_number=_clean(row.get("cas_number")),
        pubchem_cid=int(row["pubchem_cid"]) if _clean(row.get("pubchem_cid")) is not None else None,
    )
    ex = conn.execute("SELECT material_id, " + ", ".join(MATERIAL_FIELDS) + " FROM materials WHERE name = ?",
                      (row["name"],)).fetchone()
    if ex:
        for i, f in enumerate(MATERIAL_FIELDS):
            if vals[f] is not None and ex[i + 1] is not None and not _same(ex[i + 1], vals[f]):
                report.conflicts.append(dict(kind="material_field", name=row["name"], field=f,
                                             existing=ex[i + 1], new=vals[f], action="left untouched"))
        report.unchanged["materials"] += 1
        return ex[0], False
    if vals["inchikey"]:
        other = conn.execute("SELECT name FROM materials WHERE inchikey = ?", (vals["inchikey"],)).fetchone()
        if other:
            report.conflicts.append(dict(kind="duplicate_inchikey", name=row["name"], inchikey=vals["inchikey"],
                                         existing_name=other[0], action="material skipped, existing row kept"))
            report.skipped.append(dict(name=row["name"], reason="duplicate inchikey of " + other[0]))
            return None, False
    cur = conn.execute(
        "INSERT INTO materials (name, formula, smiles, inchikey, molecular_weight, cas_number, pubchem_cid) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row["name"], vals["formula"], vals["smiles"], vals["inchikey"], vals["molecular_weight"],
         vals["cas_number"], vals["pubchem_cid"]))
    report.inserted["materials"] += 1
    return cur.lastrowid, True


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def _open_db(db_path, schema_path, fresh, dry_run):
    db_path = Path(db_path)
    if dry_run:
        mem = sqlite3.connect(":memory:")
        if db_path.exists() and not fresh:
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            src.backup(mem)
            src.close()
        else:
            mem.executescript(Path(schema_path).read_text())
        return mem
    if fresh and db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(Path(schema_path).read_text())
    return conn


def run_family(family, catalog_path, selections_path, db_path, *, fresh=False, dry_run=False, strict=False,
               report_path=None, load_physical_fn=None, literature_note=None, literature_title=None,
               literature_technique=None, schema_path=SCHEMA_PATH, allow_null_formula=False, reference_sources=True,
               collapse_block_duplicates=False) -> Report:
    catalog_path = Path(catalog_path)
    load_physical_fn = load_physical_fn or load_physical_properties
    df = load_catalog(catalog_path, allow_null_formula=allow_null_formula)
    selections = load_selections(selections_path)
    report = Report(family)
    deferred_keys = {k for k, v in selections.items() if isinstance(v, dict) and v.get("deferred") is True}
    if not reference_sources:
        dens_cols = [c for c in ("density_g_cm3", "xray_sld_real", "xray_sld_imag", "neutron_sld_real", "neutron_sld_imag") if c in df.columns]
        if any(df[c].notna().any() for c in dens_cols):
            raise CatalogError("catalog carries density/SLD values but reference_sources=False (no source rows to cite)")

    for key in sorted(set(selections) - set(df["selection_key"]) - deferred_keys):
        report.warnings.append(dict(kind="unknown_selection_key", key=key))
    for key in sorted(deferred_keys - set(df["selection_key"])):  # deferred and not in the catalog: nothing to load, but recorded
        report.deferred.append(dict(key=key, name=None, reason=selections[key].get("reason"), in_catalog=False))

    conn = _open_db(db_path, schema_path, fresh, dry_run)
    conn.execute("PRAGMA foreign_keys = ON")
    sources_before, max_source_id = conn.execute("SELECT COUNT(*), MAX(source_id) FROM sources").fetchone()
    source_cache = {PREEXISTING_SOURCE_KEY: max_source_id or 0}

    mp_source_id = periodictable_source_id = literature_source_id = None
    try:
        if reference_sources:
            mp_source_id = get_or_create_named_source(
                conn, source_cache, "mp", "Materials Project",
                authors="Materials Project Consortium", year=2013, technique="DFT (Materials Project)",
                url="https://materialsproject.org", doi="10.1063/1.4812323",
                notes="mp-api queries against the Materials Project summary endpoint; see mp_id/mp_space_group/"
                      f"mp_energy_above_hull_ev provenance recorded per-material in data/{catalog_path.name} and "
                      "data/raw_cache/mp/*.json")
            get_or_create_named_source(  # pubchem: registered so the source row exists; no numeric rows cite it
                conn, source_cache, "pubchem", "PubChem",
                authors="National Center for Biotechnology Information", year=2024,
                technique="PubChem PUG REST/PUG-View", url="https://pubchem.ncbi.nlm.nih.gov",
                notes="cid/smiles/inchikey/molecular_weight/CAS from PubChem PUG REST + PUG-View CAS heading; "
                      "raw responses cached under data/raw_cache/pubchem/")
            periodictable_source_id = get_or_create_named_source(
                conn, source_cache, "periodictable",
                "periodictable: x-ray and neutron scattering length density calculation",
                authors="periodictable Python package", technique="calculated",
                url="https://periodictable.readthedocs.io",
                notes=f"xray_sld at {XRAY_ENERGY_EV} eV (Cu K-alpha, {XRAY_WAVELENGTH_NM} nm); "
                      f"neutron_sld at {NEUTRON_WAVELENGTH_NM} nm (thermal, 2200 m/s reference), natural isotopic abundance")
            literature_source_id = get_or_create_named_source(
                conn, source_cache, "literature_density",
                literature_title or f"Literature density estimate ({family} materials with no trustworthy MP structure)",
                technique=literature_technique or "literature",
                notes=literature_note or f"Literature densities for {family} materials with no MP structure -- see the "
                                         f"flags column in data/{catalog_path.name} per material; verify against a "
                                         "primary source before relying on it.")

        for _, row in df.iterrows():
            key = row["selection_key"]
            sel = selections.get(key)
            if key in deferred_keys:  # deliberate deferral: zero rows for this material, not a warning
                report.deferred.append(dict(key=key, name=row["name"], reason=sel.get("reason"), in_catalog=True))
                continue
            csv_polymorph = row["polymorph"] if "polymorph" in df.columns and pd.notna(row.get("polymorph")) else None
            optical_polymorph = sel.get("effective_polymorph") if isinstance(sel, dict) else None
            if isinstance(sel, dict) and sel.get("axes") and optical_polymorph != csv_polymorph:
                report.notes.append(f"polymorph differs between optical ({optical_polymorph!r}) and physical "
                                    f"properties ({csv_polymorph!r}) for {key} -- their dataset_label prefixes "
                                    "will not match")

            material_id, _new = upsert_material(conn, report, row)
            if material_id is None:
                continue

            load_physical_fn(conn, material_id, row, mp_source_id, literature_source_id, periodictable_source_id,
                             csv_polymorph, source_cache=source_cache, get_source_fn=get_or_create_source,
                             report=report, catalog_name=catalog_path.name)

            if not (isinstance(sel, dict) and sel.get("axes")):
                reason = ("no selection entry" if key not in selections else
                          "selection is null/ambiguous" if sel is None else "selection has no axes")
                if isinstance(sel, dict) and sel.get("candidates"):
                    reason += f" ({len(sel['candidates'])} candidates, none chosen)"
                report.skipped.append(dict(name=row["name"], key=key, reason=reason + "; optical load skipped"))
                continue
            for axis_entry in sel["axes"]:
                ref = parse_ri_references(axis_entry["data_path"])
                src_id = get_or_create_source(
                    conn, source_cache, axis_entry["data_path"],
                    doi=ref["doi"], title=ref["title"], authors=ref["authors"], year=ref["year"],
                    technique="refractiveindex.info", url=ref["url"] or "https://refractiveindex.info",
                    notes=ref["notes"])
                load_optical_axis(conn, material_id, src_id, axis_entry, csv_polymorph, report,
                                  collapse_block_duplicates_flag=collapse_block_duplicates)

        report.inserted["sources"] = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] - sources_before
        if strict and (report.conflicts or report.skipped or report.warnings):
            raise StrictError(f"--strict: {len(report.conflicts)} conflict(s), {len(report.skipped)} skip(s), "
                              f"{len(report.warnings)} warning(s)")
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        if report_path:
            Path(report_path).write_text(json.dumps(report.to_dict(), indent=2, default=str))
        raise

    print(f"[{family}] {'DRY RUN (rolled back)' if dry_run else 'Committed'}. inserted={report.inserted} "
          f"unchanged={report.unchanged} conflicts={len(report.conflicts)} skipped={len(report.skipped)} "
          f"warnings={len(report.warnings)} deferred={len(report.deferred)} collapsed={len(report.collapsed)}")
    for n in report.notes:
        print(f"[{family}] NOTE: {n}")
    if not dry_run:
        print("PRAGMA integrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("PRAGMA foreign_key_check:", "OK (no violations)" if not fk else fk)
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            print(f"  {name}: {conn.execute(f'SELECT COUNT(*) FROM [{name}]').fetchone()[0]}")
    conn.close()
    if report_path:
        Path(report_path).write_text(json.dumps(report.to_dict(), indent=2, default=str))
    return report


def build_parser(default_family=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    if default_family is None:
        p.add_argument("--family", required=True)
        p.add_argument("--catalog", required=True)
        p.add_argument("--selections", required=True)
        p.add_argument("--db", required=True)
        p.add_argument("--fresh", action="store_true", help="delete and rebuild the output DB")
    p.add_argument("--dry-run", action="store_true", help="run on an in-memory copy; write nothing")
    p.add_argument("--strict", action="store_true", help="abort + roll back on any conflict/skip/warning")
    p.add_argument("--report", help="write a JSON report to this path")
    if default_family is None:
        p.add_argument("--allow-null-formula", action="store_true", help="NULL formula is valid (grade-specific materials)")
        p.add_argument("--collapse-block-duplicates", action="store_true", help="keep the tabulated row where a formula and a tabulated block share a wavelength")
        p.add_argument("--no-reference-sources", action="store_true", help="do not create the MP/PubChem/periodictable/literature source rows")
        p.add_argument("--literature-title", help="title of the source row that non-MP densities are attributed to")
        p.add_argument("--literature-technique", help="technique field of that source row (default: literature)")
        p.add_argument("--literature-note", help="notes field of that source row")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    run_family(a.family, a.catalog, a.selections, a.db, fresh=a.fresh, dry_run=a.dry_run, strict=a.strict,
               report_path=a.report, literature_title=a.literature_title,
               literature_technique=a.literature_technique, literature_note=a.literature_note,
               allow_null_formula=a.allow_null_formula, reference_sources=not a.no_reference_sources,
               collapse_block_duplicates=a.collapse_block_duplicates)


if __name__ == "__main__":
    main()
