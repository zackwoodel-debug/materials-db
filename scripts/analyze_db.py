#!/usr/bin/env python3
"""
scripts/analyze_db.py
=====================
Read-only audit of a materials database against a professional scientific data model: what is present, missing, packed into
one column, or anomalous, and a machine-readable migration blueprint (Material / Specimen / Measurement / PropertyValue /
ProvenanceRecord). It never writes to the database and never "fixes" data: anomalies are flagged, not changed.

    python3 scripts/analyze_db.py release/materials-db-v0.19.0/materials-db-v0.19.0.sqlite
    python3 scripts/analyze_db.py release/materials-db-v0.19.0/materials-db-v0.19.0.sqlite --release-dir release/materials-db-v0.19.0
    python3 scripts/analyze_db.py postgresql://user@host/db          # any SQLAlchemy URL, if sqlalchemy is installed
    -> <out>/schema_gaps.csv + schema_gaps.md, data_completeness.csv, anomalies.csv, migration_recommendations.yaml

Steps (functions of the same names):
  introspect_schema()        tables, views, columns, types, keys; each column classified as identity / specimen / measurement /
                             property / provenance / internal, by its name and a sample of its values; units: stored as data,
                             encoded in the column name, documented only in a data dictionary, or absent
  analyze_completeness()     per material: stable id, canonical name, identifiers, >= 1 source; per spectrum (material x
                             dataset): explicit x-axis unit, temperature, technique, specimen detail, validity range, source
  detect_anomalies()         negative / non-finite k, non-physical n, duplicate wavelengths, one-point spectra, out-of-range
                             densities / temperatures, sources with no DOI / URL / title, dangling foreign keys, and (with
                             --release-dir) malformed or self-inconsistent glass codes. Flag only.
  generate_recommendations() entities, a mapping of every existing column to an entity field (keep / split / derive), columns
                             packing several concepts, and the fields the data model needs but the database lacks
"""
import argparse
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------------------------------------------ vocabulary

CATEGORIES = ["identity", "specimen", "measurement", "property", "provenance", "internal"]

# name rules, first match wins (checked against "table.column" and "column")
NAME_RULES = [
    ("internal", r"^(record_id|synonym_id|validation_id|raw_record_id)$|_fp$|morgan"),
    ("provenance", r"source|doi|url|author|journal|title|year|reference|citation|raw_record_table|notes?$|license|retriev"),
    ("identity", r"(^|_)(material_id|name|formula|smiles|inchikey|cas|pubchem|synonym|manufacturer|trade|glass_code|catalog|"
                 r"polymorph|material_class|materialclass|key)(_|$)"),
    ("specimen", r"substrate|thickness|film|bulk|orientation|specimen|sample|anneal|process|preparation|phase|axis|lot"),
    ("measurement", r"temperature|pressure|frequency|technique|method|instrument|angle|energy_ev|^wavelength_nm$|shear_rate|"
                    r"context|date|condition"),
    ("property", r"(^|_)(n|k|eps_real|eps_imag|density|sld|dielectric|modulus|viscosity|value|mass|tpsa|logp|bond|donor|"
                 r"acceptor|ring|descriptor|consensus|std_dev|pearson|rmse|error|confidence|classification|uncertainty|"
                 r"heavy|weight|num_sources|property_name|dataset_[ab])(_|$)"),
]
UNIT_SUFFIX = re.compile(r"_(nm|um|m|cm|mm|ev|c|k|hz|pa|pas|g_cm3|kg_m3|s_inv|gpa|deg|angstrom\d?|mol)$", re.I)
DIMENSIONLESS = {"n", "k", "eps_real", "eps_imag", "pearson_r", "logp", "confidence_score", "dielectric_constant",
                 "mean_relative_error", "rmse", "std_dev", "consensus_value"}
COUNT_COLUMN = re.compile(r"(^|_)(count|num|rings|donors|acceptors|bonds|sites)(_|$)", re.I)  # integer counts: dimensionless
# a sources.technique value that names HOW a value was obtained, as opposed to WHERE it came from ("refractiveindex.info", "literature")
TECHNIQUE = re.compile(r"ellipsometr|refractometr|prism|interferomet|reflectan|transmi|spectrophotomet|kramers|minimum deviation|"
                       r"crystallograph|diffraction|dft|density functional|calculat|pycnometr|archimedes|abbe", re.I)

# the professional model: fields each entity should have (the recommendation targets)
MODEL = {
    "Material": ["material_id", "canonical_name", "formula", "material_class", "identifiers (InChIKey, PubChem CID, CAS)",
                 "manufacturer", "trade_name", "glass_code", "composition_basis (atomic / weight / nominal)"],
    "Specimen": ["specimen_id", "material_id", "form (bulk / film / single crystal / liquid / gas)", "phase_or_polymorph",
                 "thickness_nm", "substrate", "crystal_orientation / optical_axis", "preparation_method", "supplier_lot"],
    "Measurement": ["measurement_id", "specimen_id", "measurand (n,k / density / ...)", "technique", "temperature_K",
                    "pressure_Pa", "validity_domain (x_min, x_max, x_unit)", "method_kind (measured / model fit / calculated)",
                    "analysis_model", "measurement_date"],
    "PropertyValue": ["value", "unit", "uncertainty", "uncertainty_type (std / expanded / bound)", "x_value (wavelength)",
                      "x_unit", "representation (tabulated / dispersion formula)", "formula_type_and_coefficients"],
    "ProvenanceRecord": ["source_id", "doi", "citation (title, authors, journal, year)", "url", "source_file / page",
                         "retrieved_at", "upstream_version (commit)", "license", "curation_notes", "quality_level"],
}
CATEGORY_ENTITY = {"identity": "Material", "specimen": "Specimen", "measurement": "Measurement", "property": "PropertyValue",
                   "provenance": "ProvenanceRecord", "internal": None}
# model fields the database may already cover, detected by a column name pattern (else counted missing)
MODEL_COVERAGE = {
    "Material": {"material_id": r"^material_id$", "canonical_name": r"^name$", "formula": r"^formula$",
                 "material_class": r"material_?class", "identifiers": r"inchikey|pubchem|cas", "manufacturer": r"manufacturer",
                 "trade_name": r"trade", "glass_code": r"glass_code", "composition_basis": r"composition_basis"},
    "Specimen": {"specimen_id": r"specimen_id", "form": r"^form$|specimen_form", "phase_or_polymorph": r"polymorph|^phase$",
                 "thickness_nm": r"thickness", "substrate": r"substrate", "orientation/axis": r"orientation|^axis$",
                 "preparation_method": r"preparation|process", "supplier_lot": r"lot|supplier"},
    "Measurement": {"measurement_id": r"measurement_id", "technique": r"technique", "temperature": r"temperature",
                    "pressure": r"pressure", "validity_domain": r"valid", "method_kind": r"method_kind|is_model",
                    "analysis_model": r"analysis_model", "measurement_date": r"measure.*date|^date$"},
    "PropertyValue": {"value": r"^(n|k|density_g_cm3|consensus_value|viscosity_pas)$", "unit": r"^unit$|_unit$",
                      "uncertainty": r"uncertainty|std_dev", "x_value": r"^wavelength_nm$", "representation": r"representation",
                      "formula_coefficients": r"coefficient"},
    "ProvenanceRecord": {"source_id": r"^source_id$", "doi": r"^doi$", "citation": r"^title$|authors|journal",
                         "url": r"^url$", "source_file": r"raw_record_table", "retrieved_at": r"retriev",
                         "upstream_version": r"commit|version", "license": r"licen", "quality_level": r"quality"},
}
PACKED_HINTS = {  # what a free-text value can carry, beyond its column's category
    "conditions": r"\b\d+(\.\d+)?\s*(degc|°c|k\b|kpa|mbar|nm|um|µm)\b|room temperature",
    "specimen": r"\bfilm\b|substrate|thick|crystal|bulk|amorphous|annealed|coated|\bo-ray|\be-ray",
    "provenance": r"doi|https?://|et al|\b(19|20)\d{2}\b|\b[A-Z][a-z]+(19|20)\d{2}\b",
    "quality": r"disagree|suspect|excluded|typo|not reliable|warning|model",
}


# ------------------------------------------------------------------------------------------------ database access

class DB:
    """sqlite3 for a file path; SQLAlchemy (if installed) for a URL. Read-only for SQLite (mode=ro)."""

    def __init__(self, target):
        self.target = str(target)
        if "://" in self.target:
            import sqlalchemy as sa
            self.engine = sa.create_engine(self.target)
            self.kind = self.engine.dialect.name
        else:
            p = Path(self.target)
            if not p.exists():
                raise SystemExit(f"no database at {p}")
            self.con = sqlite3.connect(f"file:{p.resolve()}?mode=ro", uri=True)
            self.kind = "sqlite"

    def df(self, sql, params=None):
        if hasattr(self, "engine"):
            import sqlalchemy as sa
            with self.engine.connect() as c:
                return pd.read_sql(sa.text(sql), c, params=params)
        return pd.read_sql(sql, self.con, params=params)

    def schema(self):
        """[{table, kind, columns: [{name, type, pk, not_null}], foreign_keys: [(col, ref_table, ref_col)]}]"""
        if hasattr(self, "engine"):
            import sqlalchemy as sa
            ins = sa.inspect(self.engine)
            out = []
            for kind, names in (("table", ins.get_table_names()), ("view", ins.get_view_names())):
                for t in names:
                    pk = set((ins.get_pk_constraint(t) or {}).get("constrained_columns") or [])
                    cols = [dict(name=c["name"], type=str(c["type"]), pk=c["name"] in pk, not_null=not c.get("nullable", True))
                            for c in ins.get_columns(t)]
                    fks = [(fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0])
                           for fk in ins.get_foreign_keys(t)] if kind == "table" else []
                    out.append(dict(table=t, kind=kind, columns=cols, foreign_keys=fks))
            return out
        out = []
        for t, kind in self.con.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
                                        "AND name NOT LIKE 'sqlite_%' ORDER BY type, name"):
            cols = [dict(name=r[1], type=r[2], pk=bool(r[5]), not_null=bool(r[3]))
                    for r in self.con.execute(f'PRAGMA table_info("{t}")')]
            fks = [(r[3], r[2], r[4]) for r in self.con.execute(f'PRAGMA foreign_key_list("{t}")')]
            out.append(dict(table=t, kind=kind, columns=cols, foreign_keys=fks))
        return out


def load_dictionary(release_dir):
    p = Path(release_dir) / "data_dictionary.json" if release_dir else None
    if not p or not p.exists():
        return {}
    d = json.loads(p.read_text())
    return {(t, c["name"]): c for t, v in d["tables"].items() for c in v["columns"]}


# ------------------------------------------------------------------------------------------------ 1. schema

def _classify(table, col, sample):
    for cat, pat in NAME_RULES:
        if re.search(pat, col, re.I) or re.search(pat, f"{table}.{col}", re.I):
            return cat, "name"
    if sample:  # fall back to the values: numbers -> property, text with a year / DOI -> provenance, else identity
        text = " ".join(map(str, sample))[:2000]
        if all(isinstance(v, (int, float)) for v in sample):
            return "property", "values"
        if re.search(PACKED_HINTS["provenance"], text, re.I):
            return "provenance", "values"
    return "identity", "default"


def _packing(values):
    """Which concepts a text column's values carry (share of sampled values showing each)."""
    vals = [str(v) for v in values if isinstance(v, str) and v.strip()]
    if not vals:
        return {}
    hits = {k: sum(bool(re.search(p, v, re.I)) for v in vals) / len(vals) for k, p in PACKED_HINTS.items()}
    sep = sum(bool(re.search(r"\s\|\s|;\s", v)) for v in vals) / len(vals)
    return {**{k: round(v, 3) for k, v in hits.items() if v > 0}, **({"separators": round(sep, 3)} if sep else {})}


def introspect_schema(db, dictionary=None, sample_rows=400):
    dictionary = dictionary or {}
    rows = []
    for t in db.schema():
        for c in t["columns"]:
            try:
                sample = db.df(f'SELECT "{c["name"]}" AS v FROM "{t["table"]}" WHERE "{c["name"]}" IS NOT NULL LIMIT {sample_rows}').v.tolist()
            except Exception:
                sample = []
            cat, basis = _classify(t["table"], c["name"], sample)
            numeric = bool(sample) and all(isinstance(v, (int, float)) for v in sample)
            documented = (dictionary.get((t["table"], c["name"])) or {}).get("unit")
            if not numeric or cat not in ("property", "measurement"):
                unit = "n/a"
            elif c["name"] in DIMENSIONLESS or COUNT_COLUMN.search(c["name"]):
                unit = "dimensionless (implied)"
            elif UNIT_SUFFIX.search(c["name"]):
                unit = "in column name"
            elif documented:
                unit = "documented only (data dictionary)"
            else:
                unit = "absent"
            fk = next((f"{rt}.{rc}" for col, rt, rc in t["foreign_keys"] if col == c["name"]), None)
            rows.append(dict(table=t["table"], object=t["kind"], column=c["name"], type=c["type"], primary_key=c["pk"],
                             foreign_key=fk, category=cat, classified_by=basis, numeric=numeric, unit_storage=unit,
                             dictionary_unit=documented, packs=json.dumps(_packing(sample)) if not numeric else ""))
    return pd.DataFrame(rows)


def schema_gaps(cols):
    """For each entity: the model fields present (and in which columns) and missing."""
    tables = cols[cols.object == "table"]
    out = []
    for entity, fields in MODEL_COVERAGE.items():
        for field, pat in fields.items():
            hit = tables[tables.column.map(lambda c: bool(re.search(pat, c, re.I)))]
            out.append(dict(entity=entity, field=field, status="present" if len(hit) else "MISSING",
                            columns=", ".join(sorted(set(hit.table + "." + hit.column)))[:300]))
    return pd.DataFrame(out)


# ------------------------------------------------------------------------------------------------ 2. completeness

def _pct(n, d):
    return round(100.0 * n / d, 2) if d else None


def _has(cols, table, column):
    return ((cols.table == table) & (cols.column == column)).any()


def analyze_completeness(db, cols, release_dir=None):
    stats = []
    add = lambda scope, metric, n, d, note="": stats.append(dict(scope=scope, metric=metric, count=n, total=d, percent=_pct(n, d), note=note))  # noqa: E731

    # materials
    if _has(cols, "materials", "material_id"):
        m = db.df("SELECT * FROM materials")
        N = len(m)
        add("material", "has primary-key id", int(m.material_id.notna().sum()), N)
        reg = Path(release_dir) / "material_registry.csv" if release_dir else None
        if reg and reg.exists():
            keys = pd.read_csv(reg)
            add("material", "has stable text key (registry)", int(m.material_id.isin(keys.material_id).sum()), N,
                "material_registry.csv; ids permanent across releases")
        else:
            add("material", "has stable text key (registry)", 0, N, "no registry found (pass --release-dir)")
        add("material", "canonical name present and unique", int(m.name.notna().sum() if m.name.is_unique else 0), N)
        add("material", "has formula", int(m.formula.notna().sum()), N)
        ident = [c for c in ("inchikey", "pubchem_cid", "cas_number") if c in m]
        add("material", "has an external identifier (InChIKey / PubChem / CAS)", int(m[ident].notna().any(axis=1).sum()) if ident else 0, N)
        src = db.df("SELECT material_id FROM optical_dispersion WHERE source_id IS NOT NULL UNION "
                    "SELECT material_id FROM physical_properties WHERE source_id IS NOT NULL")
        add("material", "has >= 1 source reference", int(m.material_id.isin(src.material_id).sum()), N)
        if _has(cols, "material_synonyms", "synonym"):
            add("material", "has synonyms", int(m.material_id.isin(db.df("SELECT DISTINCT material_id FROM material_synonyms").material_id).sum()), N)

    # spectra = (material, dataset_label) in optical_dispersion
    if _has(cols, "optical_dispersion", "dataset_label"):
        s = db.df("""SELECT o.material_id, o.dataset_label, COUNT(*) AS points, MIN(o.wavelength_nm) AS wl_min,
                            MAX(o.wavelength_nm) AS wl_max, SUM(o.temperature_c IS NOT NULL) AS with_t,
                            SUM(o.k IS NOT NULL) AS with_k, MIN(o.source_id) AS source_id, MIN(o.raw_record_table) AS src_file
                     FROM optical_dispersion o GROUP BY o.material_id, o.dataset_label""")
        srcs = db.df("SELECT source_id, doi, title, url, technique FROM sources").set_index("source_id") if _has(cols, "sources", "source_id") else pd.DataFrame()
        S = len(s)
        x_unit_in_name = bool(UNIT_SUFFIX.search("wavelength_nm"))
        add("spectrum", "x-axis unit explicit", S if x_unit_in_name else 0, S,
            "unit only in the column name (wavelength_nm); no unit column, but one unit for every row: consistent")
        add("spectrum", "stored as SI-convertible x (nm), no energy/wavenumber mix", S, S, "single x column")
        add("spectrum", "temperature stated on every point", int((s.with_t == s.points).sum()), S)
        add("spectrum", "temperature stated on some points", int((s.with_t > 0).sum()), S)
        add("spectrum", "has k as well as n", int((s.with_k > 0).sum()), S)
        tech = s.source_id.map(srcs.technique) if len(srcs) else pd.Series([None] * S)
        real = tech.fillna("").map(lambda t: bool(TECHNIQUE.search(t)))
        add("spectrum", "sources.technique filled (any value)", int(tech.notna().sum()), S,
            "mostly a source CHANNEL ('refractiveindex.info', 'literature'), not a technique")
        add("spectrum", "measurement technique actually named", int(real.sum()), S,
            "ellipsometry / refractometry / ... per spectrum: the upstream pages state it in free text, if at all")
        add("spectrum", "method kind (measured vs model fit) stored", 0, S,
            "not a column; derivable from the source file (scripts/dataset_kind.py)")
        spec = s.dataset_label.fillna("").str.contains(r"\|", regex=True) | s.dataset_label.fillna("").str.contains(
            r"film|substrate|crystal|thick|amorphous|glass|liquid|solid|gas", case=False, regex=True)
        add("spectrum", "specimen detail present (in dataset_label text)", int(spec.sum()), S,
            "specimen facts (phase, film, substrate, axis) live only inside dataset_label; no specimen entity/id")
        add("spectrum", "specimen id", 0, S, "no Specimen entity")
        add("spectrum", "validity range stored explicitly", 0, S, "derivable as min/max of the points only")
        add("spectrum", "has source_id", int(s.source_id.notna().sum()), S)
        if len(srcs):
            doi_or_url = s.source_id.map(lambda i: bool(i in srcs.index and (pd.notna(srcs.at[i, "doi"]) or pd.notna(srcs.at[i, "url"]))))
            add("spectrum", "source has DOI or URL", int(doi_or_url.sum()), S)
        add("spectrum", "source file (upstream page) recorded", int(s.src_file.notna().sum()), S)
        add("spectrum", "uncertainty stored per value", 0, S, "no uncertainty column in optical_dispersion")

    # physical property records
    if _has(cols, "physical_properties", "record_id"):
        p = db.df("SELECT * FROM physical_properties")
        P = len(p)
        add("property record", "has source_id", int(p.source_id.notna().sum()), P)
        add("property record", "temperature stated", int(p.temperature_c.notna().sum()), P)
        add("property record", "uncertainty stored", 0, P, "no uncertainty column")
        units_explicit = sum(1 for c in ("density_g_cm3", "xray_sld", "neutron_sld", "dielectric_constant")
                             if c in p and (UNIT_SUFFIX.search(c) or c in DIMENSIONLESS))
        add("property record", "value columns with unit in their name (of 4)", units_explicit, 4, "xray_sld / neutron_sld: dictionary only")

    # sources
    if _has(cols, "sources", "source_id"):
        so = db.df("SELECT * FROM sources")
        T = len(so)
        add("source", "has DOI", int(so.doi.notna().sum()), T)
        add("source", "has URL", int(so.url.notna().sum()), T)
        add("source", "has DOI or URL", int((so.doi.notna() | so.url.notna()).sum()), T)
        add("source", "has title", int(so.title.notna().sum()), T)
        add("source", "has year", int(so.year.notna().sum()), T)
        add("source", "technique field filled (any value)", int(so.technique.notna().sum()), T)
        add("source", "technique field names a technique", int(so.technique.fillna("").map(lambda t: bool(TECHNIQUE.search(t))).sum()), T,
            "vs a channel such as 'refractiveindex.info' or 'literature'")
        add("source", "has numeric uncertainty", int(so.uncertainty.notna().sum()), T)

    # columns overall
    num = cols[(cols.object == "table") & cols.numeric & cols.category.isin(["property", "measurement"])]
    add("column", "numeric value columns with a unit stored as data", 0, len(num), "no unit columns anywhere")
    add("column", "numeric value columns with unit in name or implied dimensionless",
        int(num.unit_storage.isin(["in column name", "dimensionless (implied)"]).sum()), len(num))
    add("column", "numeric value columns with unit only in the data dictionary",
        int((num.unit_storage == "documented only (data dictionary)").sum()), len(num))
    add("column", "numeric value columns with no unit anywhere", int((num.unit_storage == "absent").sum()), len(num))
    return pd.DataFrame(stats)


# ------------------------------------------------------------------------------------------------ 3. anomalies

def detect_anomalies(db, cols, release_dir=None, examples=5):
    found = []

    def flag(kind, n, where, sample=None, note=""):
        if n:
            found.append(dict(anomaly=kind, count=int(n), where=where, examples=json.dumps(sample or [], default=str)[:600], note=note))

    if _has(cols, "optical_dispersion", "k"):
        q = lambda sql: db.df(sql)  # noqa: E731
        neg = q("SELECT m.name, o.dataset_label, COUNT(*) AS n, MIN(o.k) AS min_k FROM optical_dispersion o JOIN materials m "
                "USING(material_id) WHERE o.k < 0 GROUP BY 1, 2 ORDER BY 4")
        flag("negative k", neg.n.sum(), "optical_dispersion.k", neg.head(examples).values.tolist(),
             "unphysical for a passive medium; may be the source's own noise (flag only)")
        bad_n = q("SELECT m.name, o.dataset_label, COUNT(*) AS n FROM optical_dispersion o JOIN materials m USING(material_id) "
                  "WHERE o.n IS NULL OR o.n <= 0 GROUP BY 1, 2")
        flag("n null or <= 0", bad_n.n.sum(), "optical_dispersion.n", bad_n.head(examples).values.tolist())
        big = q("SELECT m.name, o.dataset_label, COUNT(*) AS n, MAX(o.n) AS max_n FROM optical_dispersion o JOIN materials m "
                "USING(material_id) WHERE o.n > 10 GROUP BY 1, 2 ORDER BY 4 DESC")
        flag("n > 10 (plausible for metals in the IR, check otherwise)", big.n.sum(), "optical_dispersion.n", big.head(examples).values.tolist())
        wl = q("SELECT COUNT(*) AS n FROM optical_dispersion WHERE wavelength_nm IS NULL OR wavelength_nm <= 0")
        flag("wavelength null or <= 0", wl.n[0], "optical_dispersion.wavelength_nm")
        dup = q("SELECT m.name, o.dataset_label, o.wavelength_nm, COUNT(*) AS n FROM optical_dispersion o JOIN materials m "
                "USING(material_id) GROUP BY o.material_id, o.dataset_label, o.wavelength_nm HAVING COUNT(*) > 1")
        flag("duplicate wavelength within one spectrum", len(dup), "optical_dispersion", dup.head(examples).values.tolist(),
             "check whether the source itself repeats the wavelength (the materials-db build only admits repeats present in the source)")
        tiny = q("SELECT m.name, o.dataset_label, COUNT(*) AS n FROM optical_dispersion o JOIN materials m USING(material_id) "
                 "GROUP BY o.material_id, o.dataset_label HAVING COUNT(*) < 3")
        flag("spectrum with < 3 points", len(tiny), "optical_dispersion", tiny.head(examples).values.tolist())
        temp = q("SELECT COUNT(*) AS n FROM optical_dispersion WHERE temperature_c < -273.15 OR temperature_c > 3000")
        flag("temperature outside -273.15..3000 degC", temp.n[0], "optical_dispersion.temperature_c")
        nok = q("SELECT COUNT(*) AS n FROM optical_dispersion WHERE (source_id IS NULL) OR (dataset_label IS NULL OR dataset_label = '')")
        flag("optical row without source or label", nok.n[0], "optical_dispersion")

    if _has(cols, "physical_properties", "density_g_cm3"):
        d = db.df("SELECT m.name, p.density_g_cm3, p.dataset_label FROM physical_properties p JOIN materials m USING(material_id) "
                  "WHERE p.density_g_cm3 IS NOT NULL AND (p.density_g_cm3 <= 0 OR p.density_g_cm3 > 23)")
        flag("density <= 0 or > 23 g/cm3", len(d), "physical_properties.density_g_cm3", d.head(examples).values.tolist())

    if _has(cols, "sources", "source_id"):
        s = db.df("SELECT source_id, title FROM sources WHERE doi IS NULL AND url IS NULL")
        flag("source with neither DOI nor URL", len(s), "sources", s.head(examples).values.tolist(),
             "citable only by title text")
        s = db.df("SELECT source_id FROM sources WHERE title IS NULL OR title = ''")
        flag("source without title", len(s), "sources")

    # dangling foreign keys (declared or implied by name)
    tables = set(cols[cols.object == "table"].table)
    for t in sorted(tables):
        for c in ("material_id", "source_id"):
            ref = "materials" if c == "material_id" else "sources"
            if t != ref and _has(cols, t, c) and ref in tables:
                n = db.df(f'SELECT COUNT(*) AS n FROM "{t}" x WHERE x.{c} IS NOT NULL AND x.{c} NOT IN (SELECT {c} FROM {ref})').n[0]
                flag(f"dangling {c}", n, f"{t}.{c}")

    # glass codes (family table in the release package)
    gc = Path(release_dir) / "family_tables" / "glass_catalogs.csv" if release_dir else None
    if gc and gc.exists():
        g = pd.read_csv(gc, dtype={"glass_code": str, "glass_code_from_nd": str})
        bad = g[g.glass_code.notna() & ~g.glass_code.fillna("").str.fullmatch(r"\d{6}")]
        flag("glass code not 6 digits", len(bad), "glass_catalogs.glass_code", bad[["name", "glass_code"]].head(examples).values.tolist())
        own = g.apply(lambda r: f"{round((r.nd - 1) * 1000) % 1000:03d}{round(r.vd * 10):03d}"
                      if pd.notna(r.nd) and pd.notna(r.vd) else None, axis=1)
        mism = g[g.glass_code.notna() & own.notna() & g.apply(
            lambda r: bool(r.glass_code) and own[r.name] is not None and (abs(int(r.glass_code[:3]) - int(own[r.name][:3])) > 1
                                                                           or abs(int(r.glass_code[3:]) - int(own[r.name][3:])) > 1), axis=1)]
        flag("glass code inconsistent with its own nd / Vd", len(mism), "glass_catalogs", mism[["name", "glass_code"]].head(examples).values.tolist(),
             "precision-moulding grades carry the base glass's code (post-moulding nd/Vd)")
        nod = g[g.glass_code.isna()]
        flag("catalog glass without glass code", len(nod), "glass_catalogs", nod.name.head(examples).tolist())
    return pd.DataFrame(found, columns=["anomaly", "count", "where", "examples", "note"])


# ------------------------------------------------------------------------------------------------ 4. recommendations

SPLITS = {  # packed columns known in this schema: how to split them
    "optical_dispersion.dataset_label": dict(
        grammar="[variant/phase |] source tag [| axis]",
        into=["Specimen.phase_or_form (the variant part: 'film on glass', 'liquid', 'cubic, single crystal')",
              "Specimen.optical_axis or Measurement.polarization ('o-ray' / 'e-ray' / 'alpha-axis')",
              "ProvenanceRecord.source_tag (e.g. 'Papatryfonos2021', 'Wu1993-25.1C': the temperature suffix is a Measurement fact)"]),
    "physical_properties.dataset_label": dict(
        grammar="[polymorph |] quantity_method | source (e.g. 'xray_sld_real | periodictable_CuKalpha')",
        into=["PropertyValue.measurand ('density', 'xray_sld_real')", "Measurement.method_kind ('MP_DFT', 'literature', ...)",
              "Measurement.probe (CuKalpha / thermal neutrons)", "Specimen.phase_or_polymorph"]),
    "sources.notes": dict(into=["ProvenanceRecord.curation_notes", "Measurement conditions (when it states them)"]),
    "sources.title": dict(into=["ProvenanceRecord.citation.title (for papers)", "ProvenanceRecord.kind ('catalog', 'calculation')"],
                          note="also used for non-paper sources (catalogs, software)"),
    "chemical_descriptors.descriptor_json": dict(into=["Material descriptors (compositional / structural / molecular / chemistry)",
                                                       "ProvenanceRecord for the descriptor source (Materials Project version, RDKit)"]),
    "materials.name": dict(into=["Material.canonical_name", "Material.qualifier (the bracketed part: '(cured)', '(12 mol% Y2O3)')",
                                 "Specimen facts where the bracket is a sample state"]),
    "family_tables.*.flags": dict(into=["ProvenanceRecord.curation_notes", "QualityFlag rows (disagreement, excluded page, typo found)",
                                        "Measurement conditions quoted from the source"]),
}
TARGETS = {  # concrete target fields for columns whose destination is not just "the entity of its category"
    "materials.material_id": ("Material", "material_id", None), "materials.name": ("Material", "canonical_name", "split qualifier"),
    "materials.formula": ("Material", "formula", None), "materials.molecular_weight": ("Material", "molar_mass", "unit g/mol"),
    "material_synonyms.synonym": ("Material", "synonyms[]", None),
    "optical_dispersion.wavelength_nm": ("PropertyValue", "x_value", "x_unit = 'nm' (a spectrum's abscissa, not a condition)"),
    "optical_dispersion.n": ("PropertyValue", "value (measurand = n)", "unit = 1"),
    "optical_dispersion.k": ("PropertyValue", "value (measurand = k)", "unit = 1"),
    "optical_dispersion.eps_real": ("PropertyValue", "derived (n^2 - k^2)", "generated column: do not migrate as data"),
    "optical_dispersion.eps_imag": ("PropertyValue", "derived (2nk)", "generated column: do not migrate as data"),
    "optical_dispersion.temperature_c": ("Measurement", "temperature_K", "convert: + 273.15"),
    "optical_dispersion.dataset_label": ("Measurement", "label", "split: see `split`"),
    "optical_dispersion.raw_record_table": ("ProvenanceRecord", "source_file", None),
    "optical_dispersion.raw_record_id": ("ProvenanceRecord", "source_row", None),
    "optical_dispersion.source_id": ("ProvenanceRecord", "source_id", None),
    "physical_properties.density_g_cm3": ("PropertyValue", "value (measurand = density)", "unit = g/cm^3"),
    "physical_properties.xray_sld": ("PropertyValue", "value (measurand = xray_sld)", "unit = 1e-6 / Angstrom^2 (dictionary only today)"),
    "physical_properties.neutron_sld": ("PropertyValue", "value (measurand = neutron_sld)", "unit = 1e-6 / Angstrom^2 (dictionary only today)"),
    "physical_properties.dielectric_constant": ("PropertyValue", "value (measurand = dielectric constant)", "unit = 1"),
    "physical_properties.temperature_c": ("Measurement", "temperature_K", "convert: + 273.15"),
    "physical_properties.wavelength_nm": ("Measurement", "probe_wavelength", "unit nm (x-ray / neutron probe)"),
    "physical_properties.energy_ev": ("Measurement", "probe_energy", "unit eV"),
    "physical_properties.frequency_hz": ("Measurement", "frequency", "unit Hz"),
    "sources.doi": ("ProvenanceRecord", "doi", None), "sources.url": ("ProvenanceRecord", "url", None),
    "sources.title": ("ProvenanceRecord", "citation.title", "split: see `split`"),
    "sources.technique": ("Measurement", "technique", "only where it names a technique; else ProvenanceRecord.channel"),
    "sources.uncertainty": ("PropertyValue", "uncertainty", "per source today; move to per measurement"),
}
MISSING_FIELDS = [  # needed by the model and absent from the schema
    ("Specimen", "specimen_id", "one row per physical sample; today specimen facts are text inside dataset_label"),
    ("Specimen", "form", "bulk / thin film / single crystal / liquid / gas"),
    ("Specimen", "thickness_nm", "film spectra (e.g. ITO 17-110 nm, perovskite films) depend on it"),
    ("Specimen", "substrate", "stated by many pages (CONDITIONS.substrate) but not stored"),
    ("Measurement", "measurement_id", "links a spectrum to its specimen, technique and conditions"),
    ("Measurement", "technique", "sources.technique exists but per source, often empty"),
    ("Measurement", "temperature_K", "temperature_c exists on rows; many spectra have none"),
    ("Measurement", "pressure_Pa", "gases carry pressure only in the variant label"),
    ("Measurement", "validity_domain", "explicit x_min, x_max, x_unit; today derived from the points"),
    ("Measurement", "method_kind", "measured / model fit / calculated; today derived by scripts/dataset_kind.py"),
    ("PropertyValue", "unit", "units live in column names or the data dictionary, never as data"),
    ("PropertyValue", "uncertainty", "no per-value or per-dataset uncertainty column"),
    ("PropertyValue", "representation + formula coefficients", "formula pages are stored only as sampled points"),
    ("ProvenanceRecord", "retrieved_at + upstream_version", "the upstream commit is in the release MANIFEST, not per record"),
    ("ProvenanceRecord", "license", "per-source license (CC0 refractiveindex.info, CC BY Materials Project) is in DATA_LICENSE.md only"),
    ("ProvenanceRecord", "quality_level", "flags and dataset_validation classify quality, not a per-record field"),
]


def generate_recommendations(cols, gaps, completeness, anomalies):
    mapping = []
    for r in cols[cols.object == "table"].itertuples():
        key = f"{r.table}.{r.column}"
        action = "split" if key in SPLITS else ("derive" if r.category == "internal" else "keep")
        entity = CATEGORY_ENTITY.get(r.category)
        target, conversion = None, None
        if key in TARGETS:
            entity, target, conversion = TARGETS[key]
        packs = json.loads(r.packs) if r.packs else {}
        if action == "keep" and packs and len([k for k in packs if k != "separators"]) >= 2 and r.category == "provenance":
            action = "review (free text mixing concepts)"
        mapping.append(dict(column=key, category=r.category, entity=entity, target_field=target, action=action,
                            conversion_or_note=conversion, unit_storage=r.unit_storage if r.unit_storage != "n/a" else None,
                            packs=packs or None))
    missing = gaps[gaps.status == "MISSING"].groupby("entity").field.apply(list).to_dict()
    pct = {f"{r.scope}: {r.metric}": r.percent for r in completeness.itertuples()}
    return dict(
        purpose="Blueprint for separating material identity, specimen, measurement, values and provenance. Generated from the "
                "data by scripts/analyze_db.py; a proposal, not an applied migration.",
        entities={e: dict(fields=f, missing_in_current_schema=missing.get(e, [])) for e, f in MODEL.items()},
        relationships=["Material 1-n Specimen", "Specimen 1-n Measurement", "Measurement 1-n PropertyValue (a spectrum is one "
                       "Measurement with many values)", "Measurement n-1 ProvenanceRecord", "PropertyValue 0-n QualityFlag"],
        column_mapping=mapping,
        split=SPLITS,
        add_fields=[dict(entity=e, field=f, why=w) for e, f, w in MISSING_FIELDS],
        evidence=dict(completeness_percent=pct,
                      anomalies={r.anomaly: int(r.count) for r in anomalies.itertuples()}),
        migration_order=["1 ProvenanceRecord from sources (+ license, kind, upstream version)",
                         "2 Specimen from dataset_label variant/axis + family-table/page CONDITIONS (substrate, thickness)",
                         "3 Measurement per (material, dataset_label): technique, temperature, validity domain, method_kind",
                         "4 PropertyValue: move n, k, density ... with explicit unit and (where known) uncertainty",
                         "5 QualityFlag from flags, dataset_validation and the negative-k allow-list"],
    )


# ------------------------------------------------------------------------------------------------ output

def _md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("db", help="SQLite file, or a SQLAlchemy URL (needs sqlalchemy)")
    ap.add_argument("--release-dir", help="release package folder (data_dictionary.json, material_registry.csv, family_tables/)")
    ap.add_argument("--out", default="db_audit", help="output folder (default ./db_audit)")
    a = ap.parse_args(argv)
    release_dir = a.release_dir or (str(Path(a.db).parent) if "://" not in a.db and (Path(a.db).parent / "data_dictionary.json").exists() else None)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    db = DB(a.db)
    dictionary = load_dictionary(release_dir)

    cols = introspect_schema(db, dictionary)
    gaps = schema_gaps(cols)
    completeness = analyze_completeness(db, cols, release_dir)
    anomalies = detect_anomalies(db, cols, release_dir)
    recs = generate_recommendations(cols, gaps, completeness, anomalies)

    table_cols = cols[cols.object == "table"]
    schema_rows = (table_cols.assign(entity=table_cols.category.map(CATEGORY_ENTITY))
                   [["category", "entity", "table", "column", "type", "unit_storage", "packs"]].sort_values(["category", "table", "column"]))
    schema_out = pd.concat([schema_rows.assign(kind="existing column"),
                            gaps.rename(columns={"field": "column", "columns": "packs"}).assign(kind="model field", category="",
                                                                                              table="", type="", unit_storage="")
                            .rename(columns={"status": "presence"})], ignore_index=True)
    schema_out.to_csv(out / "schema_gaps.csv", index=False)
    completeness.to_csv(out / "data_completeness.csv", index=False)
    anomalies.to_csv(out / "anomalies.csv", index=False)
    import yaml
    (out / "migration_recommendations.yaml").write_text(yaml.safe_dump(recs, sort_keys=False, allow_unicode=True, width=120))
    md = [f"# Schema gaps: {Path(a.db).name}", "", "## Model fields present / missing", "", _md_table(gaps), "",
          "## Existing columns by category", "", _md_table(schema_rows.fillna("")), "",
          "## Completeness", "", _md_table(completeness), "", "## Anomalies (flagged, not fixed)", "",
          _md_table(anomalies.drop(columns=["examples"]))]
    (out / "schema_gaps.md").write_text("\n".join(md) + "\n")

    # human summary
    print(f"\n== {Path(a.db).name}: {len(cols[cols.object == 'table'].table.unique())} tables, "
          f"{len(cols[cols.object == 'view'].table.unique())} views, {len(table_cols)} columns")
    print("columns by category:", dict(Counter(table_cols.category)))
    print("\nmodel fields MISSING:")
    for e, f in gaps[gaps.status == "MISSING"].groupby("entity").field.apply(list).items():
        print(f"  {e:17s} {', '.join(f)}")
    print("\ncompleteness (percent):")
    for r in completeness.itertuples():
        print(f"  {r.scope:16s} {r.metric:62s} {r.percent if r.percent is not None else '-':>7}  ({r.count}/{r.total})")
    print("\nanomalies (flagged only):")
    for r in anomalies.itertuples():
        print(f"  {r.count:8d}  {r.anomaly}  [{r.where}]")
    print("\npacked columns to split:", ", ".join(SPLITS))
    print(f"\nwrote {out}/schema_gaps.csv, schema_gaps.md, data_completeness.csv, anomalies.csv, migration_recommendations.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
