PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS materials (
    material_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    formula TEXT,
    smiles TEXT,
    inchikey TEXT UNIQUE,
    molecular_weight REAL,
    cas_number TEXT,
    pubchem_cid INTEGER
);

CREATE TABLE IF NOT EXISTS material_synonyms (
    synonym_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    synonym TEXT NOT NULL,
    UNIQUE(material_id, synonym)
);

CREATE TABLE IF NOT EXISTS sources (
    source_id INTEGER PRIMARY KEY,
    doi TEXT UNIQUE,
    title TEXT,
    authors TEXT,
    journal TEXT,
    year INTEGER,
    technique TEXT,
    url TEXT,
    uncertainty REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS chemical_descriptors (
    material_id INTEGER PRIMARY KEY REFERENCES materials(material_id) ON DELETE CASCADE,
    exact_mass REAL,
    tpsa REAL,
    logp REAL,
    heavy_atom_count INTEGER,
    rotatable_bonds INTEGER,
    hbond_donors INTEGER,
    hbond_acceptors INTEGER,
    aromatic_rings INTEGER,
    descriptor_json TEXT,
    morgan_fp TEXT
);

CREATE TABLE IF NOT EXISTS optical_dispersion (
    record_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    wavelength_nm REAL NOT NULL,
    n REAL,
    k REAL,
    eps_real REAL GENERATED ALWAYS AS (
        CASE WHEN n IS NOT NULL AND k IS NOT NULL THEN n * n - k * k END
    ) STORED,
    eps_imag REAL GENERATED ALWAYS AS (
        CASE WHEN n IS NOT NULL AND k IS NOT NULL THEN 2.0 * n * k END
    ) STORED,
    temperature_c REAL,
    dataset_label TEXT,
    raw_record_table TEXT,
    raw_record_id INTEGER,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    CHECK(n IS NOT NULL OR k IS NOT NULL),
    UNIQUE(raw_record_table, raw_record_id)
);

CREATE TABLE IF NOT EXISTS mechanical_properties (
    record_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    storage_modulus REAL,
    loss_modulus REAL,
    temperature_c REAL NOT NULL,
    frequency_hz REAL NOT NULL,
    dataset_label TEXT,
    raw_record_table TEXT,
    raw_record_id INTEGER,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    CHECK(storage_modulus IS NOT NULL OR loss_modulus IS NOT NULL),
    UNIQUE(raw_record_table, raw_record_id)
);

CREATE TABLE IF NOT EXISTS rheology (
    record_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    viscosity_pas REAL NOT NULL,
    shear_rate_s_inv REAL,
    temperature_c REAL,
    context_flag TEXT,
    dataset_label TEXT,
    raw_record_table TEXT,
    raw_record_id INTEGER,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    UNIQUE(raw_record_table, raw_record_id)
);

CREATE TABLE IF NOT EXISTS physical_properties (
    record_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    density_g_cm3 REAL,
    xray_sld REAL,
    neutron_sld REAL,
    dielectric_constant REAL,
    temperature_c REAL,
    frequency_hz REAL,
    wavelength_nm REAL,
    energy_ev REAL,
    dataset_label TEXT,
    raw_record_table TEXT,
    raw_record_id INTEGER,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    CHECK(
        density_g_cm3 IS NOT NULL
        OR xray_sld IS NOT NULL
        OR neutron_sld IS NOT NULL
        OR dielectric_constant IS NOT NULL
    ),
    UNIQUE(raw_record_table, raw_record_id)
);

CREATE TABLE IF NOT EXISTS consensus_properties (
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    property_name TEXT NOT NULL,
    consensus_value REAL,
    std_dev REAL,
    num_sources INTEGER NOT NULL DEFAULT 0,
    confidence_score REAL,
    classification TEXT,
    PRIMARY KEY(material_id, property_name)
);

CREATE TABLE IF NOT EXISTS dataset_validation (
    validation_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
    property_name TEXT NOT NULL,
    dataset_a TEXT NOT NULL,
    dataset_b TEXT NOT NULL,
    pearson_r REAL,
    rmse REAL,
    mean_relative_error REAL,
    classification TEXT,
    notes TEXT,
    UNIQUE(material_id, property_name, dataset_a, dataset_b)
);

CREATE INDEX IF NOT EXISTS idx_materials_name ON materials(name);
CREATE INDEX IF NOT EXISTS idx_synonyms_material ON material_synonyms(material_id);
CREATE INDEX IF NOT EXISTS idx_optical_material_wavelength ON optical_dispersion(material_id, wavelength_nm);
CREATE INDEX IF NOT EXISTS idx_mechanical_material_context ON mechanical_properties(material_id, temperature_c, frequency_hz);
CREATE INDEX IF NOT EXISTS idx_rheology_material_context ON rheology(material_id, temperature_c, shear_rate_s_inv);
CREATE INDEX IF NOT EXISTS idx_physical_material ON physical_properties(material_id);
CREATE INDEX IF NOT EXISTS idx_consensus_property ON consensus_properties(property_name);

DROP VIEW IF EXISTS spr_data;
CREATE VIEW spr_data AS
SELECT
    m.material_id,
    m.name AS material_name,
    o.wavelength_nm,
    o.n,
    o.k,
    o.eps_real,
    o.eps_imag,
    o.temperature_c,
    o.source_id
FROM materials m
JOIN optical_dispersion o ON o.material_id = m.material_id
WHERE o.wavelength_nm BETWEEN 600.0 AND 1000.0;

DROP VIEW IF EXISTS xrr_data;
CREATE VIEW xrr_data AS
SELECT
    m.material_id,
    m.name AS material_name,
    p.density_g_cm3,
    p.xray_sld,
    p.neutron_sld,
    p.energy_ev,
    p.wavelength_nm,
    p.source_id
FROM materials m
LEFT JOIN physical_properties p ON p.material_id = m.material_id
WHERE p.density_g_cm3 IS NOT NULL
   OR p.xray_sld IS NOT NULL
   OR p.neutron_sld IS NOT NULL;

DROP VIEW IF EXISTS optical_summary;
CREATE VIEW optical_summary AS
SELECT
    m.material_id,
    m.name AS material_name,
    COUNT(o.record_id) AS optical_records,
    MIN(o.wavelength_nm) AS min_wavelength_nm,
    MAX(o.wavelength_nm) AS max_wavelength_nm,
    AVG(o.n) AS mean_n,
    AVG(o.k) AS mean_k,
    COUNT(DISTINCT o.source_id) AS optical_sources
FROM materials m
LEFT JOIN optical_dispersion o ON o.material_id = m.material_id
GROUP BY m.material_id, m.name;

DROP VIEW IF EXISTS material_summary;
CREATE VIEW material_summary AS
SELECT
    m.material_id,
    m.name,
    m.formula,
    m.smiles,
    m.inchikey,
    m.molecular_weight,
    COUNT(DISTINCT o.record_id) AS optical_records,
    COUNT(DISTINCT me.record_id) AS mechanical_records,
    COUNT(DISTINCT r.record_id) AS rheology_records,
    COUNT(DISTINCT p.record_id) AS physical_records
FROM materials m
LEFT JOIN optical_dispersion o ON o.material_id = m.material_id
LEFT JOIN mechanical_properties me ON me.material_id = m.material_id
LEFT JOIN rheology r ON r.material_id = m.material_id
LEFT JOIN physical_properties p ON p.material_id = m.material_id
GROUP BY m.material_id, m.name, m.formula, m.smiles, m.inchikey, m.molecular_weight;

DROP VIEW IF EXISTS consensus_summary;
CREATE VIEW consensus_summary AS
SELECT
    m.material_id,
    m.name AS material_name,
    c.property_name,
    c.consensus_value,
    c.std_dev,
    c.num_sources,
    c.confidence_score,
    c.classification
FROM consensus_properties c
JOIN materials m ON m.material_id = c.material_id;
