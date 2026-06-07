-- materials-db schema
-- Wavelengths stored in nm; source data converted from µm on parse.
-- k = NULL means no extinction data for this material (not zero).
-- density_g_cm3: bulk density at ~20 °C, used for XRR/neutron modelling.

CREATE TABLE IF NOT EXISTS materials (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    formula        TEXT,
    material_class TEXT,                -- solvent | metal | oxide | polymer | lipid | …
    notes          TEXT,
    density_g_cm3  REAL
);

CREATE TABLE IF NOT EXISTS optical_nk (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id),
    wavelength_nm  REAL    NOT NULL,
    n              REAL    NOT NULL,    -- real part of refractive index
    k              REAL,               -- extinction coefficient; NULL = absent, not zero
    source_ref     TEXT,
    temperature_C  REAL
);

CREATE INDEX IF NOT EXISTS idx_nk_mat ON optical_nk(material_id);
CREATE INDEX IF NOT EXISTS idx_nk_wl  ON optical_nk(wavelength_nm);
