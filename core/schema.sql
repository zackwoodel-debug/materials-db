-- core/schema.sql
-- Full DDL: tables, performance indexes, and the spr_data view.
-- Idempotent — safe to re-run on an existing database.
-- Wavelengths stored in nm; k = NULL means no extinction data (never 0).

CREATE TABLE IF NOT EXISTS references_db (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doi           TEXT    UNIQUE,
    citation_text TEXT    NOT NULL,
    url           TEXT,
    bibtex        TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    formula          TEXT,
    smiles           TEXT,
    molecular_weight REAL,
    material_class   TEXT,
    notes            TEXT,
    density_g_cm3    REAL
);

CREATE TABLE IF NOT EXISTS chemical_descriptors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id     INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    descriptor_name TEXT    NOT NULL,
    value           REAL    NOT NULL,
    source_library  TEXT,
    UNIQUE(material_id, descriptor_name)
);

CREATE TABLE IF NOT EXISTS optical_nk (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id   INTEGER REFERENCES references_db(id),
    wavelength_nm  REAL    NOT NULL,
    n              REAL    NOT NULL,
    k              REAL,
    source_ref     TEXT,
    temperature_C  REAL
);

CREATE TABLE IF NOT EXISTS viscoelasticity (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id        INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id       INTEGER REFERENCES references_db(id),
    frequency_hz       REAL    NOT NULL,
    temperature_C      REAL,
    storage_modulus_pa REAL,
    loss_modulus_pa    REAL,
    viscosity_mpa_s    REAL,
    UNIQUE(material_id, frequency_hz, temperature_C)
);

CREATE TABLE IF NOT EXISTS dielectrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id),
    frequency_hz      REAL    NOT NULL,
    temperature_C     REAL,
    real_permittivity REAL    NOT NULL,
    imag_permittivity REAL,
    UNIQUE(material_id, frequency_hz, temperature_C)
);

CREATE TABLE IF NOT EXISTS calculated_slds (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id),
    energy_ev         REAL    NOT NULL,
    wavelength_nm     REAL    NOT NULL,
    xray_sld_real     REAL    NOT NULL,
    xray_sld_imag     REAL,
    neutron_sld_real  REAL    NOT NULL,
    neutron_sld_imag  REAL,
    UNIQUE(material_id, energy_ev)
);

CREATE INDEX IF NOT EXISTS idx_nk_mat ON optical_nk(material_id);
CREATE INDEX IF NOT EXISTS idx_nk_wl  ON optical_nk(wavelength_nm);

-- spr_data VIEW
-- Linear interpolation of n,k at SPR instrument wavelengths (633, 785, 980 nm).
-- Returns NULL when no optical_nk point exists within 10 nm of the target wavelength.

DROP VIEW IF EXISTS spr_data;

CREATE VIEW spr_data AS
WITH

targets(wl) AS (
    VALUES (633.0), (785.0), (980.0)
),

brackets AS (
    SELECT
        m.id                                                                AS material_id,
        m.name                                                              AS material_name,
        t.wl                                                                AS target_wl,
        MAX(CASE WHEN o.wavelength_nm <= t.wl THEN o.wavelength_nm END)    AS lo_wl,
        MIN(CASE WHEN o.wavelength_nm >  t.wl THEN o.wavelength_nm END)    AS hi_wl
    FROM   materials  m
    CROSS  JOIN targets t
    LEFT   JOIN optical_nk o ON o.material_id = m.id
    GROUP  BY m.id, t.wl
),

interp AS (
    SELECT
        b.material_id,
        b.material_name,
        b.target_wl,
        b.lo_wl,
        b.hi_wl,
        lo.n                                                                AS lo_n,
        lo.k                                                                AS lo_k,
        hi.n                                                                AS hi_n,
        hi.k                                                                AS hi_k,
        MIN(
            COALESCE(ABS(b.target_wl - b.lo_wl), 1e9),
            COALESCE(ABS(b.target_wl - b.hi_wl), 1e9)
        )                                                                   AS nearest_dist,
        CASE
            WHEN b.lo_wl IS NULL OR b.hi_wl IS NULL THEN NULL
            ELSE (b.target_wl - b.lo_wl) / (b.hi_wl - b.lo_wl)
        END                                                                 AS t_frac
    FROM   brackets b
    LEFT   JOIN optical_nk lo ON lo.material_id = b.material_id
                               AND lo.wavelength_nm = b.lo_wl
    LEFT   JOIN optical_nk hi ON hi.material_id = b.material_id
                               AND hi.wavelength_nm = b.hi_wl
)

SELECT
    material_id,
    material_name,
    target_wl                           AS wavelength_nm,
    CASE
        WHEN nearest_dist > 10.0        THEN NULL
        WHEN lo_wl IS NULL              THEN hi_n
        WHEN hi_wl IS NULL              THEN lo_n
        ELSE                                 lo_n + (hi_n - lo_n) * t_frac
    END                                 AS n,
    CASE
        WHEN nearest_dist > 10.0        THEN NULL
        WHEN lo_wl IS NULL              THEN hi_k
        WHEN hi_wl IS NULL              THEN lo_k
        WHEN lo_k IS NULL AND hi_k IS NULL  THEN NULL
        WHEN lo_k IS NULL               THEN hi_k
        WHEN hi_k IS NULL               THEN lo_k
        ELSE                                 lo_k + (hi_k - lo_k) * t_frac
    END                                 AS k

FROM interp;
