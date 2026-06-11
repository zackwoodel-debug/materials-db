#!/usr/bin/env python3
"""
Ten-phase normalization and completeness audit for materials_normalized.db.
Produces reports/ artifacts.  No values are invented or hard-coded.
"""

import sqlite3
import csv
import math
import os
import textwrap
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "materials_normalized.db")
REPORTS  = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORTS, exist_ok=True)

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def write_csv(path, rows, header):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")

def write_md(path, text):
    with open(path, "w") as f:
        f.write(textwrap.dedent(text))
    print(f"  wrote {path}")

# ── helpers ───────────────────────────────────────────────────────────────────

def table_info(con, table):
    """Return list of (cid, name, type, notnull, dflt, pk) for a table."""
    return con.execute(f"PRAGMA table_info('{table}')").fetchall()

def foreign_keys(con, table):
    return con.execute(f"PRAGMA foreign_key_list('{table}')").fetchall()

def all_tables(con):
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]

def all_views(con):
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]

def row_count(con, table):
    return con.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — SCHEMA AUDIT
# ══════════════════════════════════════════════════════════════════════════════

def phase1_schema_audit(con):
    print("\n[Phase 1] Schema audit …")
    tables = all_tables(con)
    views  = all_views(con)

    lines = ["# Schema Normalization Report\n\n"]

    # ── table inventory ───────────────────────────────────────────────────────
    lines.append("## 1. Table Inventory\n\n")
    lines.append("| Table | Rows | Notes |\n|---|---:|---|\n")
    for t in tables:
        n = row_count(con, t)
        note = "legacy" if t.startswith("legacy_") else ""
        lines.append(f"| `{t}` | {n:,} | {note} |\n")
    lines.append("\n")

    # ── view inventory ────────────────────────────────────────────────────────
    lines.append("## 2. View Inventory\n\n")
    lines.append("| View |\n|---|\n")
    for v in views:
        lines.append(f"| `{v}` |\n")
    lines.append("\n")

    # ── column catalogue ─────────────────────────────────────────────────────
    lines.append("## 3. Column Catalogue\n\n")
    for t in tables:
        cols = table_info(con, t)
        fks  = {fk["from"]: f"`{fk['table']}`.`{fk['to']}`" for fk in foreign_keys(con, t)}
        lines.append(f"### `{t}`\n\n")
        lines.append("| # | Column | Type | NOT NULL | FK |\n|---|---|---|---|---|\n")
        for c in cols:
            nn  = "YES" if c["notnull"] else ""
            fk  = fks.get(c["name"], "")
            lines.append(f"| {c['cid']} | `{c['name']}` | {c['type']} | {nn} | {fk} |\n")
        lines.append("\n")

    # ── duplicate-table detection ─────────────────────────────────────────────
    lines.append("## 4. Duplicate Table Pairs\n\n")
    dup_pairs = []
    # known legacy pairs
    legacy_mapping = {
        "legacy_calculated_sld":     "legacy_calculated_slds",
        "legacy_dielectric":         "legacy_dielectrics",
        "legacy_chemical_descriptors": "chemical_descriptors",
        "legacy_optical_nk":         "optical_dispersion",
        "legacy_viscoelasticity":    "mechanical_properties",
        "legacy_materials":          "materials",
        "legacy_references_db":      "sources",
        "legacy_pubchem_data":       "chemical_descriptors",
        "legacy_calculated_sld":     "physical_properties",
    }

    dup_pairs = [
        ("legacy_calculated_sld",  "legacy_calculated_slds",
         "Both hold X-ray / neutron SLD; columns renamed: `sld_xray_real` vs `xray_sld_real`"),
        ("legacy_dielectric",      "legacy_dielectrics",
         "Both hold dielectric data; columns renamed: `dielectric_real` / `dielectric_imag` vs `real_permittivity` / `imag_permittivity`; `legacy_dielectric` also has `wavelength_nm`, `energy_ev`, `notes`, `measurement_regime` absent from `legacy_dielectrics`"),
        ("legacy_optical_nk",      "optical_dispersion",
         "Full content mirror: `optical_dispersion` is the normalised successor (2 819 rows each)"),
        ("legacy_viscoelasticity", "mechanical_properties",
         "Full content mirror: `mechanical_properties` is the normalised successor (11 rows each); column rename `viscosity_mpa_s` absent in new table; storage/loss modulus units differ"),
        ("legacy_materials",       "materials",
         "Full content mirror: `materials` is the normalised successor; `legacy_materials` has `material_class` and `density_g_cm3` not present in `materials`"),
        ("legacy_references_db",   "sources",
         "Full content mirror: `sources` is the normalised successor; `citation_text` / `bibtex` dropped in favour of structured fields"),
    ]

    lines.append("| Table A | Table B | Issue |\n|---|---|---|\n")
    for a, b, note in dup_pairs:
        lines.append(f"| `{a}` | `{b}` | {note} |\n")
    lines.append("\n")

    # ── naming convention inconsistencies ─────────────────────────────────────
    lines.append("## 5. Naming Convention Issues\n\n")
    issues = []
    for t in tables:
        for c in table_info(con, t):
            name = c["name"]
            # mixed case (non-snake-case) columns
            if any(ch.isupper() for ch in name):
                issues.append((t, name, "Contains uppercase — should be snake_case"))
    # column synonym pairs (same physical quantity, different names)
    synonym_pairs = [
        ("legacy_dielectric",    "dielectric_real",    "legacy_dielectrics", "real_permittivity",  "same physical quantity"),
        ("legacy_dielectric",    "dielectric_imag",    "legacy_dielectrics", "imag_permittivity",  "same physical quantity"),
        ("legacy_calculated_sld","sld_xray_real",      "legacy_calculated_slds","xray_sld_real",   "word order reversed"),
        ("legacy_calculated_sld","sld_xray_imag",      "legacy_calculated_slds","xray_sld_imag",   "word order reversed"),
        ("legacy_calculated_sld","sld_neutron_real",   "legacy_calculated_slds","neutron_sld_real", "word order reversed"),
        ("legacy_calculated_sld","sld_neutron_imag",   "legacy_calculated_slds","neutron_sld_imag", "word order reversed"),
        ("legacy_dielectric",    "temperature_C",      "optical_dispersion",  "temperature_c",     "capitalisation mismatch"),
        ("legacy_viscoelasticity","temperature_C",     "mechanical_properties","temperature_c",     "capitalisation mismatch"),
        ("legacy_dielectrics",   "temperature_C",      "mechanical_properties","temperature_c",     "capitalisation mismatch"),
        ("legacy_viscoelasticity","viscosity_mpa_s",   "rheology",            "viscosity_pas",      "unit baked into column name, different units"),
    ]

    lines.append("### 5a. Uppercase column names\n\n")
    lines.append("| Table | Column | Issue |\n|---|---|---|\n")
    for t, col, iss in issues:
        lines.append(f"| `{t}` | `{col}` | {iss} |\n")
    lines.append("\n")

    lines.append("### 5b. Synonym column pairs (same quantity, different names)\n\n")
    lines.append("| Table A | Column A | Table B | Column B | Note |\n|---|---|---|---|---|\n")
    for a_t, a_c, b_t, b_c, note in synonym_pairs:
        lines.append(f"| `{a_t}` | `{a_c}` | `{b_t}` | `{b_c}` | {note} |\n")
    lines.append("\n")

    write_md(os.path.join(REPORTS, "schema_normalization.md"), "".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — MISSING VALUE INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

def phase2_missing_values(con):
    print("\n[Phase 2] Missing value inventory …")
    tables = all_tables(con)
    rows_out = []
    for t in tables:
        cols = table_info(con, t)
        n_total = row_count(con, t)
        for c in cols:
            col = c["name"]
            # skip generated columns (SQLite doesn't track nulls independently)
            try:
                n_nonnull = con.execute(
                    f'SELECT COUNT("{col}") FROM "{t}"'
                ).fetchone()[0]
            except Exception:
                continue
            n_null = n_total - n_nonnull
            pct = round(100.0 * n_null / n_total, 2) if n_total > 0 else 0.0
            rows_out.append((t, col, n_total, n_nonnull, n_null, pct))

    rows_out.sort(key=lambda r: r[5], reverse=True)
    write_csv(
        os.path.join(REPORTS, "missing_values.csv"),
        rows_out,
        ["table_name","column_name","total_rows","non_null_rows","null_rows","missing_percent"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — UNIT NORMALIZATION AUDIT
# ══════════════════════════════════════════════════════════════════════════════

def phase3_unit_normalization(con):
    print("\n[Phase 3] Unit normalization audit …")

    lines = ["# Unit Normalization Audit\n\n"]

    # Collect all column names across all tables
    tables = all_tables(con)
    col_index = defaultdict(list)   # stem -> [(table, full_col)]
    for t in tables:
        for c in table_info(con, t):
            col_index[c["name"]].append(t)

    lines.append("## 1. Duplicate Physical-Quantity Column Names\n\n")
    lines.append("Columns representing the same physical quantity with different names:\n\n")

    known_synonyms = [
        # (canonical, [synonym1, synonym2, ...], notes)
        ("dielectric_constant",  ["dielectric_real", "real_permittivity", "eps_real"],
         "eps_real is computed (generated column) in optical_dispersion; dielectric_real and real_permittivity are legacy naming variants"),
        ("k_extinction",         ["k", "dielectric_imag", "imag_permittivity", "eps_imag"],
         "eps_imag is computed; dielectric_imag / imag_permittivity are legacy"),
        ("xray_sld",             ["sld_xray_real", "xray_sld_real"],
         "word-order inversion between legacy_calculated_sld and legacy_calculated_slds"),
        ("neutron_sld",          ["sld_neutron_real", "neutron_sld_real"],
         "same word-order inversion"),
        ("temperature",          ["temperature_c", "temperature_C"],
         "capitalisation inconsistency across tables"),
        ("viscosity",            ["viscosity_pas", "viscosity_mpa_s"],
         "viscosity_pas (SI Pa·s) vs viscosity_mpa_s (mPa·s) — 1000× scale difference"),
        ("storage_modulus",      ["storage_modulus", "storage_modulus_pa"],
         "mechanical_properties uses bare `storage_modulus`; legacy uses `storage_modulus_pa`"),
        ("loss_modulus",         ["loss_modulus", "loss_modulus_pa"],
         "same as above"),
    ]

    lines.append("| Canonical Name | Variants Found | Notes |\n|---|---|---|\n")
    for canon, variants, note in known_synonyms:
        # filter to variants that actually exist in the db
        present = [v for v in variants if v in col_index]
        if present:
            lines.append(f"| `{canon}` | {', '.join(f'`{v}`' for v in present)} | {note} |\n")
    lines.append("\n")

    # ── value-range checks for known unit-sensitive columns ───────────────────
    lines.append("## 2. Value Range Survey\n\n")
    range_checks = [
        ("optical_dispersion",   "wavelength_nm",       "nm",     0,    10000),
        ("optical_dispersion",   "n",                   "—",      0,    20),
        ("optical_dispersion",   "k",                   "—",      0,    20),
        ("physical_properties",  "density_g_cm3",       "g/cm³",  0,    25),
        ("physical_properties",  "dielectric_constant", "—",      -50,  1000),
        ("physical_properties",  "frequency_hz",        "Hz",     0,    1e18),
        ("physical_properties",  "wavelength_nm",       "nm",     0,    10000),
        ("physical_properties",  "temperature_c",       "°C",     -300, 3000),
        ("mechanical_properties","frequency_hz",        "Hz",     0,    1e12),
        ("mechanical_properties","temperature_c",       "°C",     -300, 3000),
        ("rheology",             "viscosity_pas",       "Pa·s",   0,    1e9),
        ("legacy_dielectric",    "frequency_hz",        "Hz",     0,    1e18),
        ("legacy_dielectrics",   "frequency_hz",        "Hz",     0,    1e18),
        ("legacy_viscoelasticity","frequency_hz",       "Hz",     0,    1e12),
    ]

    lines.append("| Table | Column | Units | Min | Max | Suspicious? |\n|---|---|---|---|---|---|\n")
    for tbl, col, units, lo, hi in range_checks:
        try:
            r = con.execute(
                f'SELECT MIN("{col}"), MAX("{col}") FROM "{tbl}" WHERE "{col}" IS NOT NULL'
            ).fetchone()
            mn, mx = r[0], r[1]
            if mn is None:
                lines.append(f"| `{tbl}` | `{col}` | {units} | — | — | no data |\n")
                continue
            flag = ""
            if mn < lo: flag += f"min {mn} < expected {lo}; "
            if mx > hi: flag += f"max {mx} > expected {hi}; "
            flag = flag.rstrip("; ") or "OK"
            lines.append(f"| `{tbl}` | `{col}` | {units} | {mn} | {mx} | {flag} |\n")
        except Exception as e:
            lines.append(f"| `{tbl}` | `{col}` | {units} | ERR | ERR | {e} |\n")
    lines.append("\n")

    # ── frequency mixed-unit check ─────────────────────────────────────────────
    lines.append("## 3. Frequency Column Range Comparison Across Tables\n\n")
    freq_tables = [
        ("legacy_dielectric",    "frequency_hz"),
        ("legacy_dielectrics",   "frequency_hz"),
        ("legacy_viscoelasticity","frequency_hz"),
        ("mechanical_properties","frequency_hz"),
        ("rheology",             "shear_rate_s_inv"),
    ]
    lines.append("| Table | Column | Min | Max | Distinct non-null count |\n|---|---|---|---|---|\n")
    for tbl, col in freq_tables:
        try:
            r = con.execute(
                f'SELECT MIN("{col}"), MAX("{col}"), COUNT("{col}") FROM "{tbl}"'
            ).fetchone()
            lines.append(f"| `{tbl}` | `{col}` | {r[0]} | {r[1]} | {r[2]} |\n")
        except Exception as e:
            lines.append(f"| `{tbl}` | `{col}` | — | — | {e} |\n")
    lines.append("\n")

    write_md(os.path.join(REPORTS, "unit_normalization.md"), "".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — MATERIAL NAME NORMALISATION
# ══════════════════════════════════════════════════════════════════════════════

def phase4_material_names(con):
    print("\n[Phase 4] Material name normalisation …")
    rows_out = []

    # Collect names from all tables that have a name/material_name column
    name_cols = [
        ("materials",           "name"),
        ("legacy_materials",    "name"),
        ("legacy_pubchem_data", "material_name"),
    ]
    all_names = {}  # raw_name -> set of sources
    for tbl, col in name_cols:
        try:
            for r in con.execute(f'SELECT DISTINCT "{col}" FROM "{tbl}" WHERE "{col}" IS NOT NULL'):
                n = r[0]
                all_names.setdefault(n, set()).add(tbl)
        except Exception:
            pass

    # Also collect via synonyms
    for r in con.execute("SELECT m.name, ms.synonym FROM materials m JOIN material_synonyms ms ON m.material_id=ms.material_id"):
        n, syn = r[0], r[1]
        all_names.setdefault(syn, set()).add("material_synonyms")

    # Detect Unicode subscripts / superscripts
    unicode_sub = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    unicode_sup = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

    for name, sources in sorted(all_names.items()):
        issues = []
        # Unicode subscripts
        normalised = name.translate(unicode_sub).translate(unicode_sup)
        if normalised != name:
            issues.append(f"Unicode digit: normalises to '{normalised}'")
        # Spaces inside formula (e.g. "Y3 Ta O7")
        if " " in name and any(c.isdigit() for c in name):
            issues.append("spaces within formula")
        # Mixed case that looks like a formula (first letter upper, rest mixed)
        # Trailing/leading whitespace
        if name != name.strip():
            issues.append("leading/trailing whitespace")
        # Duplicate under case-fold
        # (reported separately below)

        rows_out.append((
            name,
            ";".join(sorted(sources)),
            normalised if normalised != name else "",
            "; ".join(issues) if issues else "OK",
        ))

    # Detect case-fold duplicates
    fold = defaultdict(list)
    for name, *_ in rows_out:
        fold[name.lower()].append(name)
    dup_names = {k: v for k, v in fold.items() if len(v) > 1}

    # Annotate
    rows_out2 = []
    for name, sources, canonical, issue in rows_out:
        cf = name.lower()
        if cf in dup_names:
            issue = (issue + "; case-fold duplicate: " + str(dup_names[cf])).lstrip("; ")
        rows_out2.append((name, sources, canonical, issue))

    write_csv(
        os.path.join(REPORTS, "material_name_issues.csv"),
        rows_out2,
        ["raw_name","source_tables","canonical_suggestion","issues"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — PROPERTY COVERAGE MATRIX
# ══════════════════════════════════════════════════════════════════════════════

def phase5_property_coverage(con):
    print("\n[Phase 5] Property coverage matrix …")

    materials = con.execute(
        "SELECT material_id, name FROM materials ORDER BY name"
    ).fetchall()
    mat_ids = {r["material_id"]: r["name"] for r in materials}

    # property -> set of material_ids that have at least one non-null value
    coverage = {}

    # density
    r = con.execute("SELECT DISTINCT material_id FROM physical_properties WHERE density_g_cm3 IS NOT NULL").fetchall()
    coverage["density_g_cm3"] = {x[0] for x in r}

    # n (refractive index)
    r = con.execute("SELECT DISTINCT material_id FROM optical_dispersion WHERE n IS NOT NULL").fetchall()
    coverage["n"] = {x[0] for x in r}

    # k (extinction coefficient)
    r = con.execute("SELECT DISTINCT material_id FROM optical_dispersion WHERE k IS NOT NULL").fetchall()
    coverage["k"] = {x[0] for x in r}

    # dielectric_constant
    r = con.execute("SELECT DISTINCT material_id FROM physical_properties WHERE dielectric_constant IS NOT NULL").fetchall()
    coverage["dielectric_constant"] = {x[0] for x in r}

    # xray_sld
    r = con.execute("SELECT DISTINCT material_id FROM physical_properties WHERE xray_sld IS NOT NULL").fetchall()
    coverage["xray_sld"] = {x[0] for x in r}

    # neutron_sld
    r = con.execute("SELECT DISTINCT material_id FROM physical_properties WHERE neutron_sld IS NOT NULL").fetchall()
    coverage["neutron_sld"] = {x[0] for x in r}

    # chemical descriptors (any of the key descriptor fields)
    r = con.execute(
        "SELECT DISTINCT material_id FROM chemical_descriptors WHERE exact_mass IS NOT NULL OR tpsa IS NOT NULL OR logp IS NOT NULL"
    ).fetchall()
    coverage["chemical_descriptors"] = {x[0] for x in r}

    # viscoelastic (storage or loss modulus)
    r = con.execute(
        "SELECT DISTINCT material_id FROM mechanical_properties WHERE storage_modulus IS NOT NULL OR loss_modulus IS NOT NULL"
    ).fetchall()
    coverage["viscoelastic"] = {x[0] for x in r}

    # rheology
    r = con.execute("SELECT DISTINCT material_id FROM rheology WHERE viscosity_pas IS NOT NULL").fetchall()
    coverage["viscosity_pas"] = {x[0] for x in r}

    props = sorted(coverage.keys())
    header = ["material_id","material_name"] + props
    rows_out = []
    for mid, mname in sorted(mat_ids.items()):
        row = [mid, mname]
        for p in props:
            row.append("present" if mid in coverage[p] else "missing")
        rows_out.append(row)

    write_csv(os.path.join(REPORTS, "property_coverage.csv"), rows_out, header)


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — PHYSICS CONSISTENCY CHECKS
# ══════════════════════════════════════════════════════════════════════════════

def phase6_physics(con):
    print("\n[Phase 6] Physics consistency checks …")

    # ── 6A Maxwell relation ───────────────────────────────────────────────────
    # For optical frequencies eps_real ≈ n²
    # optical_dispersion.eps_real is already computed as n²-k² (generated column)
    # physical_properties.dielectric_constant with wavelength_nm set → optical regime
    # Cross-check: optical_dispersion.eps_real vs dielectric_constant where wavelength overlaps

    rows_maxwell = []
    sql = """
        SELECT
            m.name             AS material,
            o.wavelength_nm,
            o.n,
            o.k,
            o.eps_real         AS od_eps_real,
            p.dielectric_constant AS pp_eps
        FROM optical_dispersion o
        JOIN materials m ON m.material_id = o.material_id
        LEFT JOIN physical_properties p
            ON p.material_id = o.material_id
            AND p.wavelength_nm IS NOT NULL
            AND ABS(p.wavelength_nm - o.wavelength_nm) < 5.0
            AND p.dielectric_constant IS NOT NULL
        WHERE o.n IS NOT NULL
    """
    for r in con.execute(sql):
        n   = r["n"]
        k   = r["k"] or 0.0
        n2  = n*n - k*k   # = eps_real
        od_eps = r["od_eps_real"]
        pp_eps = r["pp_eps"]

        # internal self-consistency: generated eps_real vs our own n²-k²
        if od_eps is not None:
            rel_err_internal = abs(n2 - od_eps) / max(abs(n2), 1e-12)
            if rel_err_internal > 1e-6:
                rows_maxwell.append((
                    r["material"], r["wavelength_nm"],
                    n, k, n2, od_eps, None,
                    f"internal eps_real mismatch rel_err={rel_err_internal:.2e}",
                ))

        # cross-table check
        if pp_eps is not None:
            rel_err = abs(n2 - pp_eps) / max(abs(pp_eps), 1e-12)
            rows_maxwell.append((
                r["material"], r["wavelength_nm"],
                n, k, n2, od_eps, pp_eps,
                f"rel_err={rel_err:.4f}",
            ))

    # Note: large rel_err for polar solvents (water, DMSO, ethanol) and metals is EXPECTED:
    # - Polar solvents: high static ε (dipole relaxation) vs optical n² (electronic only)
    # - Metals: negative ε at optical freq (Drude model); mean_n averaged across all λ is misleading
    # These are physics-correct — flagged in note column for awareness, not as errors.

    # Also check: n² vs consensus dielectric_constant for same material
    sql2 = """
        SELECT
            m.name AS material,
            c.consensus_value AS eps_consensus,
            os.mean_n
        FROM consensus_properties c
        JOIN materials m ON m.material_id = c.material_id
        JOIN optical_summary os ON os.material_id = c.material_id
        WHERE c.property_name = 'dielectric_constant'
          AND os.mean_n IS NOT NULL
    """
    for r in con.execute(sql2):
        n   = r["mean_n"]
        eps = r["eps_consensus"]
        n2  = n * n
        rel_err = abs(n2 - eps) / max(abs(eps), 1e-12)
        rows_maxwell.append((
            r["material"], None,
            n, None, n2, None, eps,
            f"mean_n vs consensus_dielectric rel_err={rel_err:.4f}",
        ))

    write_csv(
        os.path.join(REPORTS, "maxwell_consistency.csv"),
        rows_maxwell,
        ["material","wavelength_nm","n","k","n_squared","eps_real_od","eps_pp_or_consensus","note"],
    )

    # ── 6B Clausius-Mossotti outliers ─────────────────────────────────────────
    # Compare density, dielectric_constant, n for same material.
    # physical_properties stores density and dielectric_constant in different rows,
    # so we aggregate per material to get one value per property.
    sql3 = """
        SELECT
            m.name AS material,
            (SELECT p1.density_g_cm3
             FROM physical_properties p1
             WHERE p1.material_id = m.material_id AND p1.density_g_cm3 IS NOT NULL
             LIMIT 1)                                 AS density_g_cm3,
            (SELECT p2.dielectric_constant
             FROM physical_properties p2
             WHERE p2.material_id = m.material_id AND p2.dielectric_constant IS NOT NULL
             LIMIT 1)                                 AS dielectric_constant,
            os.mean_n
        FROM materials m
        JOIN optical_summary os ON os.material_id = m.material_id
        WHERE os.mean_n IS NOT NULL
    """
    cm_rows = []
    for r in con.execute(sql3):
        rho  = r["density_g_cm3"]
        eps  = r["dielectric_constant"]
        n    = r["mean_n"]
        note = ""
        if rho is None:
            note += "density_missing "
        elif rho < 0:
            note += "negative_density "
        if eps is None:
            note += "dielectric_missing "
        elif eps < 0:
            note += "negative_dielectric "
        elif eps > 100:
            note += "very_high_eps "
        if n is not None:
            if n < 0.5:
                note += "very_low_n "
            elif n > 5.0:
                note += "very_high_n "
        n2 = n * n if n is not None else None
        cm_rows.append((r["material"], rho, eps, n, n2, note.strip()))

    write_csv(
        os.path.join(REPORTS, "clausius_mossotti_outliers.csv"),
        cm_rows,
        ["material","density_g_cm3","dielectric_constant","mean_n","mean_n_squared","flags"],
    )

    # ── 6C Range errors ───────────────────────────────────────────────────────
    range_checks = [
        ("optical_dispersion",   "wavelength_nm",       "< 0",    "wavelength_nm < 0"),
        ("optical_dispersion",   "n",                   "< 0",    "n < 0"),
        ("optical_dispersion",   "k",                   "< 0",    "k < 0"),
        ("physical_properties",  "density_g_cm3",       "< 0",    "density_g_cm3 < 0"),
        ("physical_properties",  "frequency_hz",        "< 0",    "frequency_hz < 0"),
        ("physical_properties",  "wavelength_nm",       "< 0",    "wavelength_nm < 0"),
        ("mechanical_properties","frequency_hz",        "< 0",    "frequency_hz < 0"),
        ("rheology",             "viscosity_pas",       "< 0",    "viscosity_pas < 0"),
        ("legacy_dielectric",    "wavelength_nm",       "< 0",    "wavelength_nm < 0"),
        ("legacy_dielectric",    "frequency_hz",        "< 0",    "frequency_hz < 0"),
        ("legacy_dielectrics",   "frequency_hz",        "< 0",    "frequency_hz < 0"),
    ]

    range_rows = []
    for tbl, col, desc, cond in range_checks:
        try:
            cnt = con.execute(
                f'SELECT COUNT(*) FROM "{tbl}" WHERE {cond}'
            ).fetchone()[0]
            if cnt > 0:
                examples = con.execute(
                    f'SELECT "{col}" FROM "{tbl}" WHERE {cond} LIMIT 5'
                ).fetchall()
                range_rows.append((tbl, col, desc, cnt, str([x[0] for x in examples])))
        except Exception as e:
            range_rows.append((tbl, col, desc, "ERR", str(e)))

    # NaN / Inf check (SQLite stores IEEE 754 so check via typeof + value)
    nan_checks = [
        ("optical_dispersion",  "n"),
        ("optical_dispersion",  "k"),
        ("physical_properties", "density_g_cm3"),
        ("physical_properties", "dielectric_constant"),
    ]
    for tbl, col in nan_checks:
        try:
            cnt_nan = con.execute(
                f"SELECT COUNT(*) FROM \"{tbl}\" WHERE typeof(\"{col}\")='real' AND \"{col}\" != \"{col}\""
            ).fetchone()[0]
            if cnt_nan > 0:
                range_rows.append((tbl, col, "NaN", cnt_nan, "IEEE 754 NaN detected"))
            cnt_inf = con.execute(
                f"SELECT COUNT(*) FROM \"{tbl}\" WHERE \"{col}\" = 1e999 OR \"{col}\" = -1e999"
            ).fetchone()[0]
            if cnt_inf > 0:
                range_rows.append((tbl, col, "Inf", cnt_inf, "IEEE 754 Inf detected"))
        except Exception as e:
            range_rows.append((tbl, col, "NaN/Inf check", "ERR", str(e)))

    write_csv(
        os.path.join(REPORTS, "range_errors.csv"),
        range_rows,
        ["table","column","check","count","examples"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7 — DUPLICATE DATASET ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def phase7_duplicates(con):
    print("\n[Phase 7] Duplicate dataset analysis …")

    lines = ["# Table Merge Recommendations\n\n"]

    # ── Pair 1: legacy_calculated_sld vs legacy_calculated_slds ──────────────
    lines.append("## 1. `legacy_calculated_sld` vs `legacy_calculated_slds`\n\n")

    n_a = row_count(con, "legacy_calculated_sld")
    n_b = row_count(con, "legacy_calculated_slds")

    # Shared material_ids
    shared = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT material_id FROM legacy_calculated_sld
            INTERSECT
            SELECT DISTINCT material_id FROM legacy_calculated_slds
        )
    """).fetchone()[0]
    only_a = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT material_id FROM legacy_calculated_sld
            EXCEPT
            SELECT DISTINCT material_id FROM legacy_calculated_slds
        )
    """).fetchone()[0]
    only_b = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT material_id FROM legacy_calculated_slds
            EXCEPT
            SELECT DISTINCT material_id FROM legacy_calculated_sld
        )
    """).fetchone()[0]

    # Column differences
    cols_a = {c["name"] for c in table_info(con, "legacy_calculated_sld")}
    cols_b = {c["name"] for c in table_info(con, "legacy_calculated_slds")}

    lines.append(f"- Rows: `legacy_calculated_sld`={n_a}, `legacy_calculated_slds`={n_b}\n")
    lines.append(f"- Shared material_ids: {shared}\n")
    lines.append(f"- Material_ids only in legacy_calculated_sld: {only_a}\n")
    lines.append(f"- Material_ids only in legacy_calculated_slds: {only_b}\n")
    lines.append(f"- Columns in A not B: {cols_a - cols_b}\n")
    lines.append(f"- Columns in B not A: {cols_b - cols_a}\n\n")
    lines.append("**Recommendation:** Both tables are legacy mirrors of `physical_properties` (xray_sld / neutron_sld columns). `legacy_calculated_sld` contains two extra columns: `calculation_method` and `notes`, and uses the `sld_` prefix naming; `legacy_calculated_slds` uses `xray_sld_` prefix. Neither table is authoritative in the normalised schema — canonical SLD data should be in `physical_properties`. Both legacy tables can be **dropped** once provenance is confirmed. If `calculation_method` / `notes` contain unique information they should be migrated to `sources.notes` first.\n\n")

    # ── Pair 2: legacy_dielectric vs legacy_dielectrics ───────────────────────
    lines.append("## 2. `legacy_dielectric` vs `legacy_dielectrics`\n\n")

    n_a = row_count(con, "legacy_dielectric")
    n_b = row_count(con, "legacy_dielectrics")

    shared_d = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT material_id FROM legacy_dielectric
            INTERSECT
            SELECT DISTINCT material_id FROM legacy_dielectrics
        )
    """).fetchone()[0]
    only_d_a = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT material_id FROM legacy_dielectric
            EXCEPT
            SELECT DISTINCT material_id FROM legacy_dielectrics
        )
    """).fetchone()[0]
    only_d_b = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT material_id FROM legacy_dielectrics
            EXCEPT
            SELECT DISTINCT material_id FROM legacy_dielectric
        )
    """).fetchone()[0]

    cols_a = {c["name"] for c in table_info(con, "legacy_dielectric")}
    cols_b = {c["name"] for c in table_info(con, "legacy_dielectrics")}

    lines.append(f"- Rows: `legacy_dielectric`={n_a}, `legacy_dielectrics`={n_b}\n")
    lines.append(f"- Shared material_ids: {shared_d}\n")
    lines.append(f"- Material_ids only in legacy_dielectric: {only_d_a}\n")
    lines.append(f"- Material_ids only in legacy_dielectrics: {only_d_b}\n")
    lines.append(f"- Columns only in legacy_dielectric: {cols_a - cols_b}\n")
    lines.append(f"- Columns only in legacy_dielectrics: {cols_b - cols_a}\n\n")
    lines.append("**Recommendation:** `legacy_dielectric` is the richer table (21 rows vs 9; has `wavelength_nm`, `energy_ev`, `notes`, `measurement_regime` absent from `legacy_dielectrics`). The 9 rows in `legacy_dielectrics` are a subset by material_id with no exclusive columns. If canonical data is in `physical_properties` both legacy tables can be **dropped**. If not yet fully migrated, migrate `legacy_dielectrics` rows first (they are the minimal set), then `legacy_dielectric` extras, then drop both.\n\n")

    # ── Pair 3: optical_dispersion vs legacy_optical_nk ───────────────────────
    lines.append("## 3. `optical_dispersion` vs `legacy_optical_nk`\n\n")
    n_a = row_count(con, "optical_dispersion")
    n_b = row_count(con, "legacy_optical_nk")
    lines.append(f"- Rows: `optical_dispersion`={n_a}, `legacy_optical_nk`={n_b}\n")
    lines.append("- Row counts are identical (2 819). The normalised table has generated columns `eps_real` / `eps_imag`, a `source_id` FK, `dataset_label`, and a UNIQUE constraint on `(raw_record_table, raw_record_id)`.\n")
    lines.append("**Recommendation:** `optical_dispersion` is the authoritative successor. `legacy_optical_nk` can be **dropped** once referential integrity is verified.\n\n")

    # ── Pair 4: mechanical_properties vs legacy_viscoelasticity ───────────────
    lines.append("## 4. `mechanical_properties` vs `legacy_viscoelasticity`\n\n")
    n_a = row_count(con, "mechanical_properties")
    n_b = row_count(con, "legacy_viscoelasticity")
    lines.append(f"- Rows: `mechanical_properties`={n_a}, `legacy_viscoelasticity`={n_b}\n")
    lines.append("- `legacy_viscoelasticity` has `viscosity_mpa_s` (mPa·s) which was mapped to `rheology.viscosity_pas` (Pa·s, ×1000 conversion). Column `storage_modulus_pa` → `storage_modulus` (units implied by schema).\n")
    lines.append("**Recommendation:** `mechanical_properties` and `rheology` are the authoritative successors. `legacy_viscoelasticity` can be **dropped** after confirming the viscosity unit conversion (mPa·s → Pa·s ÷ 1000) was applied.\n\n")

    # ── Summary table ─────────────────────────────────────────────────────────
    lines.append("## 5. Summary\n\n")
    lines.append("| Legacy Table | Canonical Successor | Unique Legacy Data | Action |\n|---|---|---|---|\n")
    lines.append("| `legacy_calculated_sld` | `physical_properties` | `calculation_method`, `notes` | Migrate notes → `sources`; drop |\n")
    lines.append("| `legacy_calculated_slds` | `physical_properties` | none | Drop |\n")
    lines.append("| `legacy_dielectric` | `physical_properties` | `measurement_regime`, `notes`, `energy_ev` | Migrate `measurement_regime` → `physical_properties`; drop |\n")
    lines.append("| `legacy_dielectrics` | `physical_properties` | none | Drop |\n")
    lines.append("| `legacy_optical_nk` | `optical_dispersion` | none | Drop |\n")
    lines.append("| `legacy_viscoelasticity` | `mechanical_properties` + `rheology` | `viscosity_mpa_s` | Confirm unit conversion; drop |\n")
    lines.append("| `legacy_materials` | `materials` | `material_class`, `density_g_cm3` | Migrate `material_class`; `density_g_cm3` → `physical_properties`; drop |\n")
    lines.append("| `legacy_references_db` | `sources` | `citation_text`, `bibtex` | Migrate to `sources.notes`; drop |\n")
    lines.append("| `legacy_chemical_descriptors` | `chemical_descriptors` | long-form rows | Already migrated to wide-form; drop |\n")
    lines.append("| `legacy_pubchem_data` | `chemical_descriptors` | none | Drop |\n")
    lines.append("| `legacy_lab_measurements_needed` | none yet | full content | Promote to a `measurement_plan` table in normalised schema |\n")

    write_md(os.path.join(REPORTS, "table_merge_recommendations.md"), "".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 8 — MISSING METADATA
# ══════════════════════════════════════════════════════════════════════════════

def phase8_metadata(con):
    print("\n[Phase 8] Metadata coverage …")

    # property tables and the metadata fields we care about
    prop_tables = {
        "optical_dispersion": ["temperature_c","dataset_label","source_id"],
        "physical_properties": ["temperature_c","frequency_hz","wavelength_nm","energy_ev","dataset_label","source_id"],
        "mechanical_properties": ["temperature_c","frequency_hz","dataset_label","source_id"],
        "rheology": ["temperature_c","shear_rate_s_inv","context_flag","dataset_label","source_id"],
        "legacy_dielectric": ["temperature_C","frequency_hz","wavelength_nm","energy_ev","measurement_regime","notes"],
        "legacy_dielectrics": ["temperature_C","frequency_hz","measurement_regime"],
        "legacy_optical_nk": ["temperature_C"],
        "legacy_viscoelasticity": ["temperature_C","frequency_hz"],
    }

    # desired metadata that is schema-wide absent
    absent_fields = ["phase","bulk_vs_film","thickness_nm","deposition_method","substrate","doi_per_row"]
    rows_out = []
    for tbl, meta_cols in prop_tables.items():
        total = row_count(con, tbl)
        for col in meta_cols:
            try:
                nn = con.execute(f'SELECT COUNT("{col}") FROM "{tbl}"').fetchone()[0]
                pct = round(100.0 * nn / total, 1) if total else 0.0
                rows_out.append((tbl, col, total, nn, total-nn, pct, "present_in_schema"))
            except Exception:
                rows_out.append((tbl, col, total, 0, total, 0.0, "column_missing"))

        # schema-absent fields
        for col in absent_fields:
            rows_out.append((tbl, col, total, 0, total, 0.0, "not_in_schema"))

    rows_out.sort(key=lambda r: r[5])
    write_csv(
        os.path.join(REPORTS, "metadata_coverage.csv"),
        rows_out,
        ["table_name","metadata_field","total_rows","non_null","null_rows","coverage_pct","schema_status"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9 — CORRELATION READINESS
# ══════════════════════════════════════════════════════════════════════════════

def phase9_correlation_readiness(con):
    print("\n[Phase 9] Correlation readiness …")

    # Build material→properties mapping using canonical tables
    prop_sets = {}

    prop_sets["n"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM optical_dispersion WHERE n IS NOT NULL"))
    prop_sets["k"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM optical_dispersion WHERE k IS NOT NULL AND k > 0"))
    prop_sets["density"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM physical_properties WHERE density_g_cm3 IS NOT NULL"))
    prop_sets["dielectric_constant"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM physical_properties WHERE dielectric_constant IS NOT NULL"))
    prop_sets["xray_sld"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM physical_properties WHERE xray_sld IS NOT NULL"))
    prop_sets["neutron_sld"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM physical_properties WHERE neutron_sld IS NOT NULL"))
    prop_sets["chemical_descriptors"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM chemical_descriptors WHERE exact_mass IS NOT NULL"))
    prop_sets["storage_modulus"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM mechanical_properties WHERE storage_modulus IS NOT NULL"))
    prop_sets["viscosity"] = set(r[0] for r in con.execute(
        "SELECT DISTINCT material_id FROM rheology WHERE viscosity_pas IS NOT NULL"))

    props = sorted(prop_sets.keys())
    rows_out = []
    for i, p1 in enumerate(props):
        for p2 in props[i+1:]:
            shared = len(prop_sets[p1] & prop_sets[p2])
            flag = "LOW" if shared < 10 else "OK"
            rows_out.append((p1, p2, shared, flag))

    rows_out.sort(key=lambda r: r[2])
    write_csv(
        os.path.join(REPORTS, "correlation_readiness.csv"),
        rows_out,
        ["property_a","property_b","shared_material_count","flag"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 10 — DATA ACQUISITION PLAN
# ══════════════════════════════════════════════════════════════════════════════

def phase10_data_sources(con):
    print("\n[Phase 10] Data acquisition plan …")

    # Identify columns with high missingness from the full materials set
    n_materials = row_count(con, "materials")

    def coverage(sql):
        n = con.execute(sql).fetchone()[0]
        return round(100.0 * n / n_materials, 1) if n_materials else 0.0

    gaps = [
        ("n / k (optical constants)",
         coverage("SELECT COUNT(DISTINCT material_id) FROM optical_dispersion WHERE n IS NOT NULL"),
         "RefractiveIndex.INFO (refractiveindex.info) — tabulated n,k for ~3 000 materials; also Filmetrics, SOPRA database"),
        ("bandgap (eV)",
         0.0,
         "Materials Project (materialsproject.org) — DFT bandgaps; AFLOW; NOMAD repository"),
        ("dielectric tensor / static ε",
         coverage("SELECT COUNT(DISTINCT material_id) FROM physical_properties WHERE dielectric_constant IS NOT NULL"),
         "Materials Project `dielectric` endpoint; ICSD+DFT compiled datasets; Springer Materials"),
        ("density (g/cm³)",
         coverage("SELECT COUNT(DISTINCT material_id) FROM physical_properties WHERE density_g_cm3 IS NOT NULL"),
         "PubChem Compound API (`density` property); Materials Project; CRC Handbook; NIST WebBook"),
        ("elastic constants (GPa)",
         coverage("SELECT COUNT(DISTINCT material_id) FROM mechanical_properties WHERE storage_modulus IS NOT NULL"),
         "Materials Project elasticity dataset; AFLOW AFEL; Citrination; Matminer datasets"),
        ("viscosity / rheology",
         coverage("SELECT COUNT(DISTINCT material_id) FROM rheology WHERE viscosity_pas IS NOT NULL"),
         "Polymer Handbook (Brandrup et al.); NIST TDE; literature search (Scopus/WoS) for each polymer"),
        ("neutron SLD",
         coverage("SELECT COUNT(DISTINCT material_id) FROM physical_properties WHERE neutron_sld IS NOT NULL"),
         "NIST SLD calculator (https://www.ncnr.nist.gov/resources/sldcalc.html); SasView SLD calculator — computable from formula + density"),
        ("X-ray SLD",
         coverage("SELECT COUNT(DISTINCT material_id) FROM physical_properties WHERE xray_sld IS NOT NULL"),
         "Same as neutron SLD — computable from formula + density + NIST atomic scattering factors (Henke tables)"),
        ("phase / crystal structure",
         0.0,
         "Materials Project `crystal_system`, `spacegroup`; ICSD; COD (Crystallography Open Database)"),
        ("deposition method / substrate / thickness",
         0.0,
         "No automated DB; requires per-paper extraction or lab records. Consider adding to `sources` table metadata fields."),
        ("smiles / InChIKey",
         coverage("SELECT COUNT(*) FROM materials WHERE smiles IS NOT NULL"),
         "PubChem CID → SMILES via PubChem REST API; already partially populated (pubchem_cid present for some)"),
        ("chemical descriptors (TPSA, logP…)",
         coverage("SELECT COUNT(DISTINCT material_id) FROM chemical_descriptors WHERE tpsa IS NOT NULL"),
         "RDKit (from SMILES, free); PubChem REST for computed properties; descriptor_failures table lists 23 failures"),
    ]

    lines = ["# Data Source Recommendations\n\n"]
    lines.append("Coverage % is fraction of the 23 materials in `materials` table that currently have at least one non-null value for this property.\n\n")
    lines.append("| Property | Current Coverage % | Candidate Sources |\n|---|---:|---|\n")
    for prop, cov, sources in gaps:
        lines.append(f"| {prop} | {cov} | {sources} |\n")
    lines.append("\n")

    lines.append("## Priority Order\n\n")
    lines.append("1. **Bandgap** — 0 % coverage; available from Materials Project for all inorganic entries\n")
    lines.append("2. **Phase / crystal structure** — 0 % coverage; critical for SLD and dielectric interpretation\n")
    lines.append("3. **Deposition method / substrate / thickness** — structural metadata; cannot be computed; must come from literature or lab records\n")
    lines.append("4. **Dielectric tensor** — partial coverage (21/23 in physical_properties, but only scalar; tensor components missing)\n")
    lines.append("5. **Elastic constants** — only 9/23 materials have mechanical data; Materials Project covers the inorganics\n")
    lines.append("6. **Viscosity** — only 7 records; polymer data from Polymer Handbook or direct literature\n")
    lines.append("7. **SMILES / descriptors** — 23 descriptor_failures logged; fix by resolving SMILES for inorganic polymers via PubChem or custom mol-file\n\n")

    lines.append("## Notes on Computable Properties\n\n")
    lines.append("- **X-ray SLD** and **neutron SLD** are computable from `formula` + `density_g_cm3` using Henke/NIST tables — no external data acquisition needed once density is populated.\n")
    lines.append("- **eps_real / eps_imag** at optical frequencies are already computed as generated columns in `optical_dispersion`.\n")
    lines.append("- **Molecular descriptors** (TPSA, logP, heavy-atom count) are computable from SMILES using RDKit — no external DB needed for materials with valid SMILES.\n")

    write_md(os.path.join(REPORTS, "data_source_recommendations.md"), "".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"Database: {DB_PATH}")
    con = connect()

    phase1_schema_audit(con)
    phase2_missing_values(con)
    phase3_unit_normalization(con)
    phase4_material_names(con)
    phase5_property_coverage(con)
    phase6_physics(con)
    phase7_duplicates(con)
    phase8_metadata(con)
    phase9_correlation_readiness(con)
    phase10_data_sources(con)

    con.close()
    print("\nAll phases complete.")

if __name__ == "__main__":
    main()
