-- 001: constraints + indexes. Additive and rerunnable; does not edit updated_sql_schema.sql.
-- Already present in the schema of record, so intentionally NOT repeated here:
--   * material_id NOT NULL REFERENCES materials ON DELETE CASCADE (all child tables)
--   * source_id NOT NULL on optical/mechanical/rheology/physical
--   * idx_optical_material_wavelength, idx_materials_name
--   * materials.inchikey UNIQUE (implicit index)
-- Not added: physical_properties(material_id, measurement_regime) -- no such column
-- (regime lives only in analysis_dataset.csv); would need migration 003 (needs Aiden's approval).
-- SQLite cannot ADD CHECK / NOT NULL to an existing table without a rebuild, so the
-- CHECKs are enforced with triggers. Pre-checked: zero existing rows violate any of them.

PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_materials_formula ON materials(formula);

CREATE TRIGGER IF NOT EXISTS trg_materials_formula_nn_ins
BEFORE INSERT ON materials WHEN NEW.formula IS NULL
BEGIN SELECT RAISE(ABORT, 'materials.formula must not be NULL'); END;

CREATE TRIGGER IF NOT EXISTS trg_materials_formula_nn_upd
BEFORE UPDATE OF formula ON materials WHEN NEW.formula IS NULL
BEGIN SELECT RAISE(ABORT, 'materials.formula must not be NULL'); END;

CREATE TRIGGER IF NOT EXISTS trg_optical_check_ins
BEFORE INSERT ON optical_dispersion
WHEN NEW.wavelength_nm <= 0 OR (NEW.n IS NOT NULL AND NEW.n < 0)
BEGIN SELECT RAISE(ABORT, 'optical_dispersion: wavelength_nm must be > 0 and n >= 0'); END;

CREATE TRIGGER IF NOT EXISTS trg_optical_check_upd
BEFORE UPDATE ON optical_dispersion
WHEN NEW.wavelength_nm <= 0 OR (NEW.n IS NOT NULL AND NEW.n < 0)
BEGIN SELECT RAISE(ABORT, 'optical_dispersion: wavelength_nm must be > 0 and n >= 0'); END;

CREATE TRIGGER IF NOT EXISTS trg_mechanical_check_ins
BEFORE INSERT ON mechanical_properties WHEN NEW.frequency_hz <= 0
BEGIN SELECT RAISE(ABORT, 'mechanical_properties: frequency_hz must be > 0'); END;

CREATE TRIGGER IF NOT EXISTS trg_mechanical_check_upd
BEFORE UPDATE ON mechanical_properties WHEN NEW.frequency_hz <= 0
BEGIN SELECT RAISE(ABORT, 'mechanical_properties: frequency_hz must be > 0'); END;

CREATE TRIGGER IF NOT EXISTS trg_physical_check_ins
BEFORE INSERT ON physical_properties
WHEN (NEW.frequency_hz IS NOT NULL AND NEW.frequency_hz <= 0)
  OR (NEW.wavelength_nm IS NOT NULL AND NEW.wavelength_nm <= 0)
BEGIN SELECT RAISE(ABORT, 'physical_properties: frequency_hz and wavelength_nm must be > 0 when set'); END;

CREATE TRIGGER IF NOT EXISTS trg_physical_check_upd
BEFORE UPDATE ON physical_properties
WHEN (NEW.frequency_hz IS NOT NULL AND NEW.frequency_hz <= 0)
  OR (NEW.wavelength_nm IS NOT NULL AND NEW.wavelength_nm <= 0)
BEGIN SELECT RAISE(ABORT, 'physical_properties: frequency_hz and wavelength_nm must be > 0 when set'); END;
