-- seed_manual.sql
-- Idempotent seed for materials that have no refractiveindex.info entry.
-- Safe to run on an empty or an already-populated database: INSERT OR IGNORE
-- skips rows that would violate a UNIQUE constraint.
--
-- Schema (from sqlite_master, verified against current materials.db):
-- ─────────────────────────────────────────────────────────────────────
-- CREATE TABLE materials (
--     id             INTEGER PRIMARY KEY AUTOINCREMENT,
--     name           TEXT    NOT NULL,
--     formula        TEXT,
--     material_class TEXT,
--     notes          TEXT,
--     density_g_cm3  REAL
-- );
--
-- CREATE TABLE optical_nk (
--     id             INTEGER PRIMARY KEY AUTOINCREMENT,
--     material_id    INTEGER NOT NULL REFERENCES materials(id),
--     wavelength_nm  REAL    NOT NULL,
--     n              REAL    NOT NULL,
--     k              REAL,               -- NULL = absent, never 0 for transparent materials
--     source_ref     TEXT,
--     temperature_C  REAL
-- );
-- ─────────────────────────────────────────────────────────────────────

-- Enforce uniqueness so INSERT OR IGNORE has something to check against.
-- These indexes are also good for query performance.
CREATE UNIQUE INDEX IF NOT EXISTS uidx_materials_name
    ON materials(name);

CREATE UNIQUE INDEX IF NOT EXISTS uidx_nk_mat_wl
    ON optical_nk(material_id, wavelength_nm);

-- ── PEG ──────────────────────────────────────────────────────────────────────
-- Polyethylene glycol. Bulk density 1.13 g/cm³.
-- n @ 589 nm from Brandrup et al. Polymer Handbook, 4th ed. (1999).
-- Not available in refractiveindex.info.

INSERT OR IGNORE INTO materials (name, formula, material_class, notes, density_g_cm3)
VALUES (
    'PEG',
    '(C2H4O)n',
    'polymer',
    'Polyethylene glycol; not in refractiveindex.info. Bulk n from Polymer Handbook (Brandrup et al. 4th ed.).',
    1.13
);

INSERT OR IGNORE INTO optical_nk (material_id, wavelength_nm, n, k, source_ref, temperature_C)
SELECT id, 589.0, 1.4570, NULL,
       'Brandrup et al. Polymer Handbook 4th ed. (1999)',
       20.0
FROM   materials
WHERE  name = 'PEG';

-- ── DPPC ─────────────────────────────────────────────────────────────────────
-- Dipalmitoylphosphatidylcholine; lipid bilayer model.
-- Density 1.02 g/cm³ (dry bilayer estimate).
-- n @ 633 nm from Chou et al. Biophys J 2010.
-- Not available in refractiveindex.info.

INSERT OR IGNORE INTO materials (name, formula, material_class, notes, density_g_cm3)
VALUES (
    'DPPC',
    'C40H80NO8P',
    'lipid',
    'Dipalmitoylphosphatidylcholine; lipid bilayer model. Not in refractiveindex.info.',
    1.02
);

INSERT OR IGNORE INTO optical_nk (material_id, wavelength_nm, n, k, source_ref, temperature_C)
SELECT id, 633.0, 1.48, NULL,
       'Chou et al. Biophys J 2010 doi:10.1016/j.bpj.2010.07.026',
       25.0
FROM   materials
WHERE  name = 'DPPC';

-- ── Silicon ───────────────────────────────────────────────────────────────────
-- Single-crystal Si substrate; standard XRR reference. No optical_nk entry
-- (visible-range optical constants live in refractiveindex.info if needed;
--  density used only for XRR SLD computation via xrr_engine.py).

INSERT OR IGNORE INTO materials (name, formula, material_class, notes, density_g_cm3)
VALUES (
    'Silicon',
    'Si',
    'semiconductor',
    'Single-crystal silicon substrate. Density: Deslattes et al. 1980.',
    2.329
);
