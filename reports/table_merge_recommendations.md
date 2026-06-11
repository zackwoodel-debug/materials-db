# Table Merge Recommendations

## 1. `legacy_calculated_sld` vs `legacy_calculated_slds`

- Rows: `legacy_calculated_sld`=68, `legacy_calculated_slds`=46
- Shared material_ids: 17
- Material_ids only in legacy_calculated_sld: 0
- Material_ids only in legacy_calculated_slds: 6
- Columns in A not B: {'sld_neutron_imag', 'sld_xray_real', 'sld_neutron_real', 'frequency_hz', 'sld_xray_imag', 'notes', 'calculation_method'}
- Columns in B not A: {'neutron_sld_imag', 'xray_sld_real', 'xray_sld_imag', 'neutron_sld_real'}

**Recommendation:** Both tables are legacy mirrors of `physical_properties` (xray_sld / neutron_sld columns). `legacy_calculated_sld` contains two extra columns: `calculation_method` and `notes`, and uses the `sld_` prefix naming; `legacy_calculated_slds` uses `xray_sld_` prefix. Neither table is authoritative in the normalised schema — canonical SLD data should be in `physical_properties`. Both legacy tables can be **dropped** once provenance is confirmed. If `calculation_method` / `notes` contain unique information they should be migrated to `sources.notes` first.

## 2. `legacy_dielectric` vs `legacy_dielectrics`

- Rows: `legacy_dielectric`=21, `legacy_dielectrics`=9
- Shared material_ids: 9
- Material_ids only in legacy_dielectric: 12
- Material_ids only in legacy_dielectrics: 0
- Columns only in legacy_dielectric: {'dielectric_real', 'wavelength_nm', 'dielectric_imag', 'notes', 'energy_ev'}
- Columns only in legacy_dielectrics: {'imag_permittivity', 'real_permittivity'}

**Recommendation:** `legacy_dielectric` is the richer table (21 rows vs 9; has `wavelength_nm`, `energy_ev`, `notes`, `measurement_regime` absent from `legacy_dielectrics`). The 9 rows in `legacy_dielectrics` are a subset by material_id with no exclusive columns. If canonical data is in `physical_properties` both legacy tables can be **dropped**. If not yet fully migrated, migrate `legacy_dielectrics` rows first (they are the minimal set), then `legacy_dielectric` extras, then drop both.

## 3. `optical_dispersion` vs `legacy_optical_nk`

- Rows: `optical_dispersion`=2819, `legacy_optical_nk`=2819
- Row counts are identical (2 819). The normalised table has generated columns `eps_real` / `eps_imag`, a `source_id` FK, `dataset_label`, and a UNIQUE constraint on `(raw_record_table, raw_record_id)`.
**Recommendation:** `optical_dispersion` is the authoritative successor. `legacy_optical_nk` can be **dropped** once referential integrity is verified.

## 4. `mechanical_properties` vs `legacy_viscoelasticity`

- Rows: `mechanical_properties`=11, `legacy_viscoelasticity`=11
- `legacy_viscoelasticity` has `viscosity_mpa_s` (mPa·s) which was mapped to `rheology.viscosity_pas` (Pa·s, ×1000 conversion). Column `storage_modulus_pa` → `storage_modulus` (units implied by schema).
**Recommendation:** `mechanical_properties` and `rheology` are the authoritative successors. `legacy_viscoelasticity` can be **dropped** after confirming the viscosity unit conversion (mPa·s → Pa·s ÷ 1000) was applied.

## 5. Summary

| Legacy Table | Canonical Successor | Unique Legacy Data | Action |
|---|---|---|---|
| `legacy_calculated_sld` | `physical_properties` | `calculation_method`, `notes` | Migrate notes → `sources`; drop |
| `legacy_calculated_slds` | `physical_properties` | none | Drop |
| `legacy_dielectric` | `physical_properties` | `measurement_regime`, `notes`, `energy_ev` | Migrate `measurement_regime` → `physical_properties`; drop |
| `legacy_dielectrics` | `physical_properties` | none | Drop |
| `legacy_optical_nk` | `optical_dispersion` | none | Drop |
| `legacy_viscoelasticity` | `mechanical_properties` + `rheology` | `viscosity_mpa_s` | Confirm unit conversion; drop |
| `legacy_materials` | `materials` | `material_class`, `density_g_cm3` | Migrate `material_class`; `density_g_cm3` → `physical_properties`; drop |
| `legacy_references_db` | `sources` | `citation_text`, `bibtex` | Migrate to `sources.notes`; drop |
| `legacy_chemical_descriptors` | `chemical_descriptors` | long-form rows | Already migrated to wide-form; drop |
| `legacy_pubchem_data` | `chemical_descriptors` | none | Drop |
| `legacy_lab_measurements_needed` | none yet | full content | Promote to a `measurement_plan` table in normalised schema |
