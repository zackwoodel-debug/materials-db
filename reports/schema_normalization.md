# Schema Normalization Report

## 1. Table Inventory

| Table | Rows | Notes |
|---|---:|---|
| `chemical_descriptors` | 23 |  |
| `consensus_properties` | 122 |  |
| `dataset_validation` | 43 |  |
| `descriptor_failures` | 23 |  |
| `legacy_calculated_sld` | 68 | legacy |
| `legacy_calculated_slds` | 46 | legacy |
| `legacy_chemical_descriptors` | 252 | legacy |
| `legacy_dielectric` | 21 | legacy |
| `legacy_dielectrics` | 9 | legacy |
| `legacy_lab_measurements_needed` | 6 | legacy |
| `legacy_materials` | 23 | legacy |
| `legacy_optical_nk` | 2,819 | legacy |
| `legacy_pubchem_data` | 17 | legacy |
| `legacy_references_db` | 34 | legacy |
| `legacy_viscoelasticity` | 11 | legacy |
| `material_synonyms` | 17 |  |
| `materials` | 23 |  |
| `mechanical_properties` | 11 |  |
| `optical_dispersion` | 2,819 |  |
| `physical_properties` | 167 |  |
| `property_statistics` | 107 |  |
| `rheology` | 7 |  |
| `sources` | 41 |  |
| `spectral_anomalies` | 16 |  |
| `spectral_validation` | 12 |  |

## 2. View Inventory

| View |
|---|
| `consensus_summary` |
| `material_summary` |
| `optical_summary` |
| `spr_data` |
| `xrr_data` |

## 3. Column Catalogue

### `chemical_descriptors`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `material_id` | INTEGER |  | `materials`.`material_id` |
| 1 | `exact_mass` | REAL |  |  |
| 2 | `tpsa` | REAL |  |  |
| 3 | `logp` | REAL |  |  |
| 4 | `heavy_atom_count` | INTEGER |  |  |
| 5 | `rotatable_bonds` | INTEGER |  |  |
| 6 | `hbond_donors` | INTEGER |  |  |
| 7 | `hbond_acceptors` | INTEGER |  |  |
| 8 | `aromatic_rings` | INTEGER |  |  |
| 9 | `descriptor_json` | TEXT |  |  |
| 10 | `morgan_fp` | TEXT |  |  |

### `consensus_properties`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 1 | `property_name` | TEXT | YES |  |
| 2 | `consensus_value` | REAL |  |  |
| 3 | `std_dev` | REAL |  |  |
| 4 | `num_sources` | INTEGER | YES |  |
| 5 | `confidence_score` | REAL |  |  |
| 6 | `classification` | TEXT |  |  |

### `dataset_validation`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `validation_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `property_name` | TEXT | YES |  |
| 3 | `dataset_a` | TEXT | YES |  |
| 4 | `dataset_b` | TEXT | YES |  |
| 5 | `pearson_r` | REAL |  |  |
| 6 | `rmse` | REAL |  |  |
| 7 | `mean_relative_error` | REAL |  |  |
| 8 | `classification` | TEXT |  |  |
| 9 | `notes` | TEXT |  |  |

### `descriptor_failures`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `failure_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES |  |
| 2 | `material_name` | TEXT | YES |  |
| 3 | `smiles_available` | INTEGER | YES |  |
| 4 | `attempted_rdkit` | INTEGER | YES |  |
| 5 | `attempted_pubchem` | INTEGER | YES |  |
| 6 | `attempted_legacy` | INTEGER | YES |  |
| 7 | `partial_fill` | INTEGER | YES |  |
| 8 | `missing_fields` | TEXT |  |  |
| 9 | `reason` | TEXT |  |  |
| 10 | `created_at` | TEXT | YES |  |

### `legacy_calculated_sld`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `reference_id` | INT |  |  |
| 3 | `energy_ev` | REAL |  |  |
| 4 | `wavelength_nm` | REAL |  |  |
| 5 | `frequency_hz` | REAL |  |  |
| 6 | `sld_xray_real` | REAL |  |  |
| 7 | `sld_xray_imag` | REAL |  |  |
| 8 | `sld_neutron_real` | REAL |  |  |
| 9 | `sld_neutron_imag` | REAL |  |  |
| 10 | `calculation_method` | TEXT |  |  |
| 11 | `notes` | TEXT |  |  |

### `legacy_calculated_slds`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `reference_id` | INT |  |  |
| 3 | `energy_ev` | REAL |  |  |
| 4 | `wavelength_nm` | REAL |  |  |
| 5 | `xray_sld_real` | REAL |  |  |
| 6 | `xray_sld_imag` | REAL |  |  |
| 7 | `neutron_sld_real` | REAL |  |  |
| 8 | `neutron_sld_imag` | REAL |  |  |

### `legacy_chemical_descriptors`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `descriptor_name` | TEXT |  |  |
| 3 | `value` | REAL |  |  |
| 4 | `source_library` | TEXT |  |  |

### `legacy_dielectric`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `reference_id` | INT |  |  |
| 3 | `wavelength_nm` | REAL |  |  |
| 4 | `frequency_hz` | REAL |  |  |
| 5 | `energy_ev` | REAL |  |  |
| 6 | `dielectric_real` | REAL |  |  |
| 7 | `dielectric_imag` | REAL |  |  |
| 8 | `temperature_C` | REAL |  |  |
| 9 | `notes` | TEXT |  |  |
| 10 | `measurement_regime` | TEXT |  |  |

### `legacy_dielectrics`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `reference_id` | INT |  |  |
| 3 | `frequency_hz` | REAL |  |  |
| 4 | `temperature_C` | REAL |  |  |
| 5 | `real_permittivity` | REAL |  |  |
| 6 | `imag_permittivity` | REAL |  |  |
| 7 | `measurement_regime` | TEXT |  |  |

### `legacy_lab_measurements_needed`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `measurement_type` | TEXT |  |  |
| 3 | `instrument` | TEXT |  |  |
| 4 | `parameter` | TEXT |  |  |
| 5 | `frequency_range` | TEXT |  |  |
| 6 | `wavelength_range` | TEXT |  |  |
| 7 | `priority` | INT |  |  |
| 8 | `reason` | TEXT |  |  |
| 9 | `protocol_notes` | TEXT |  |  |
| 10 | `status` | TEXT |  |  |

### `legacy_materials`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `name` | TEXT |  |  |
| 2 | `formula` | TEXT |  |  |
| 3 | `smiles` | TEXT |  |  |
| 4 | `molecular_weight` | REAL |  |  |
| 5 | `material_class` | TEXT |  |  |
| 6 | `notes` | TEXT |  |  |
| 7 | `density_g_cm3` | REAL |  |  |
| 8 | `pubchem_cid` | INT |  |  |

### `legacy_optical_nk`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `reference_id` | INT |  |  |
| 3 | `wavelength_nm` | REAL |  |  |
| 4 | `n` | REAL |  |  |
| 5 | `k` | REAL |  |  |
| 6 | `source_ref` | TEXT |  |  |
| 7 | `temperature_C` | REAL |  |  |

### `legacy_pubchem_data`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `material_name` | TEXT |  |  |
| 1 | `SMILES` | TEXT |  |  |
| 2 | `molecular_formula` | TEXT |  |  |
| 3 | `MW` | REAL |  |  |
| 4 | `XLogP` | REAL |  |  |
| 5 | `HBondDonors` | REAL |  |  |
| 6 | `HBondAcceptors` | REAL |  |  |
| 7 | `RotatableBonds` | REAL |  |  |
| 8 | `TPSA` | REAL |  |  |

### `legacy_references_db`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `doi` | TEXT |  |  |
| 2 | `citation_text` | TEXT |  |  |
| 3 | `url` | TEXT |  |  |
| 4 | `bibtex` | TEXT |  |  |

### `legacy_viscoelasticity`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `id` | INT |  |  |
| 1 | `material_id` | INT |  |  |
| 2 | `reference_id` | INT |  |  |
| 3 | `frequency_hz` | REAL |  |  |
| 4 | `temperature_C` | REAL |  |  |
| 5 | `storage_modulus_pa` | REAL |  |  |
| 6 | `loss_modulus_pa` | REAL |  |  |
| 7 | `viscosity_mpa_s` | REAL |  |  |

### `material_synonyms`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `synonym_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `synonym` | TEXT | YES |  |

### `materials`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `material_id` | INTEGER |  |  |
| 1 | `name` | TEXT | YES |  |
| 2 | `formula` | TEXT |  |  |
| 3 | `smiles` | TEXT |  |  |
| 4 | `inchikey` | TEXT |  |  |
| 5 | `molecular_weight` | REAL |  |  |
| 6 | `cas_number` | TEXT |  |  |
| 7 | `pubchem_cid` | INTEGER |  |  |

### `mechanical_properties`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `record_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `storage_modulus` | REAL |  |  |
| 3 | `loss_modulus` | REAL |  |  |
| 4 | `temperature_c` | REAL | YES |  |
| 5 | `frequency_hz` | REAL | YES |  |
| 6 | `dataset_label` | TEXT |  |  |
| 7 | `raw_record_table` | TEXT |  |  |
| 8 | `raw_record_id` | INTEGER |  |  |
| 9 | `source_id` | INTEGER | YES | `sources`.`source_id` |

### `optical_dispersion`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `record_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `wavelength_nm` | REAL | YES |  |
| 3 | `n` | REAL |  |  |
| 4 | `k` | REAL |  |  |
| 5 | `temperature_c` | REAL |  |  |
| 6 | `dataset_label` | TEXT |  |  |
| 7 | `raw_record_table` | TEXT |  |  |
| 8 | `raw_record_id` | INTEGER |  |  |
| 9 | `source_id` | INTEGER | YES | `sources`.`source_id` |

### `physical_properties`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `record_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `density_g_cm3` | REAL |  |  |
| 3 | `xray_sld` | REAL |  |  |
| 4 | `neutron_sld` | REAL |  |  |
| 5 | `dielectric_constant` | REAL |  |  |
| 6 | `temperature_c` | REAL |  |  |
| 7 | `frequency_hz` | REAL |  |  |
| 8 | `wavelength_nm` | REAL |  |  |
| 9 | `energy_ev` | REAL |  |  |
| 10 | `dataset_label` | TEXT |  |  |
| 11 | `raw_record_table` | TEXT |  |  |
| 12 | `raw_record_id` | INTEGER |  |  |
| 13 | `source_id` | INTEGER | YES | `sources`.`source_id` |

### `property_statistics`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `stat_id` | INTEGER |  |  |
| 1 | `table_name` | TEXT | YES |  |
| 2 | `table_type` | TEXT | YES |  |
| 3 | `column_name` | TEXT | YES |  |
| 4 | `units` | TEXT |  |  |
| 5 | `total_rows` | INTEGER |  |  |
| 6 | `count` | INTEGER |  |  |
| 7 | `missing_count` | INTEGER |  |  |
| 8 | `missing_pct` | REAL |  |  |
| 9 | `material_count` | INTEGER |  |  |
| 10 | `min_val` | REAL |  |  |
| 11 | `max_val` | REAL |  |  |
| 12 | `mean_val` | REAL |  |  |
| 13 | `median_val` | REAL |  |  |
| 14 | `std_val` | REAL |  |  |
| 15 | `iqr_val` | REAL |  |  |
| 16 | `mad_val` | REAL |  |  |

### `rheology`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `record_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `viscosity_pas` | REAL | YES |  |
| 3 | `shear_rate_s_inv` | REAL |  |  |
| 4 | `temperature_c` | REAL |  |  |
| 5 | `context_flag` | TEXT |  |  |
| 6 | `dataset_label` | TEXT |  |  |
| 7 | `raw_record_table` | TEXT |  |  |
| 8 | `raw_record_id` | INTEGER |  |  |
| 9 | `source_id` | INTEGER | YES | `sources`.`source_id` |

### `sources`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `source_id` | INTEGER |  |  |
| 1 | `doi` | TEXT |  |  |
| 2 | `title` | TEXT |  |  |
| 3 | `authors` | TEXT |  |  |
| 4 | `journal` | TEXT |  |  |
| 5 | `year` | INTEGER |  |  |
| 6 | `technique` | TEXT |  |  |
| 7 | `url` | TEXT |  |  |
| 8 | `uncertainty` | REAL |  |  |
| 9 | `notes` | TEXT |  |  |

### `spectral_anomalies`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `anomaly_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `dataset_label` | TEXT | YES |  |
| 3 | `property` | TEXT | YES |  |
| 4 | `anomaly_type` | TEXT | YES |  |
| 5 | `severity` | TEXT | YES |  |
| 6 | `details` | TEXT |  |  |

### `spectral_validation`

| # | Column | Type | NOT NULL | FK |
|---|---|---|---|---|
| 0 | `sv_id` | INTEGER |  |  |
| 1 | `material_id` | INTEGER | YES | `materials`.`material_id` |
| 2 | `property` | TEXT | YES |  |
| 3 | `dataset_a` | TEXT | YES |  |
| 4 | `dataset_b` | TEXT | YES |  |
| 5 | `overlap_wl_min` | REAL |  |  |
| 6 | `overlap_wl_max` | REAL |  |  |
| 7 | `n_overlap_points` | INTEGER |  |  |
| 8 | `pearson_r` | REAL |  |  |
| 9 | `rmse` | REAL |  |  |
| 10 | `mae` | REAL |  |  |
| 11 | `max_deviation` | REAL |  |  |
| 12 | `classification` | TEXT |  |  |
| 13 | `notes` | TEXT |  |  |

## 4. Duplicate Table Pairs

| Table A | Table B | Issue |
|---|---|---|
| `legacy_calculated_sld` | `legacy_calculated_slds` | Both hold X-ray / neutron SLD; columns renamed: `sld_xray_real` vs `xray_sld_real` |
| `legacy_dielectric` | `legacy_dielectrics` | Both hold dielectric data; columns renamed: `dielectric_real` / `dielectric_imag` vs `real_permittivity` / `imag_permittivity`; `legacy_dielectric` also has `wavelength_nm`, `energy_ev`, `notes`, `measurement_regime` absent from `legacy_dielectrics` |
| `legacy_optical_nk` | `optical_dispersion` | Full content mirror: `optical_dispersion` is the normalised successor (2 819 rows each) |
| `legacy_viscoelasticity` | `mechanical_properties` | Full content mirror: `mechanical_properties` is the normalised successor (11 rows each); column rename `viscosity_mpa_s` absent in new table; storage/loss modulus units differ |
| `legacy_materials` | `materials` | Full content mirror: `materials` is the normalised successor; `legacy_materials` has `material_class` and `density_g_cm3` not present in `materials` |
| `legacy_references_db` | `sources` | Full content mirror: `sources` is the normalised successor; `citation_text` / `bibtex` dropped in favour of structured fields |

## 5. Naming Convention Issues

### 5a. Uppercase column names

| Table | Column | Issue |
|---|---|---|
| `legacy_dielectric` | `temperature_C` | Contains uppercase — should be snake_case |
| `legacy_dielectrics` | `temperature_C` | Contains uppercase — should be snake_case |
| `legacy_optical_nk` | `temperature_C` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `SMILES` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `MW` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `XLogP` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `HBondDonors` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `HBondAcceptors` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `RotatableBonds` | Contains uppercase — should be snake_case |
| `legacy_pubchem_data` | `TPSA` | Contains uppercase — should be snake_case |
| `legacy_viscoelasticity` | `temperature_C` | Contains uppercase — should be snake_case |

### 5b. Synonym column pairs (same quantity, different names)

| Table A | Column A | Table B | Column B | Note |
|---|---|---|---|---|
| `legacy_dielectric` | `dielectric_real` | `legacy_dielectrics` | `real_permittivity` | same physical quantity |
| `legacy_dielectric` | `dielectric_imag` | `legacy_dielectrics` | `imag_permittivity` | same physical quantity |
| `legacy_calculated_sld` | `sld_xray_real` | `legacy_calculated_slds` | `xray_sld_real` | word order reversed |
| `legacy_calculated_sld` | `sld_xray_imag` | `legacy_calculated_slds` | `xray_sld_imag` | word order reversed |
| `legacy_calculated_sld` | `sld_neutron_real` | `legacy_calculated_slds` | `neutron_sld_real` | word order reversed |
| `legacy_calculated_sld` | `sld_neutron_imag` | `legacy_calculated_slds` | `neutron_sld_imag` | word order reversed |
| `legacy_dielectric` | `temperature_C` | `optical_dispersion` | `temperature_c` | capitalisation mismatch |
| `legacy_viscoelasticity` | `temperature_C` | `mechanical_properties` | `temperature_c` | capitalisation mismatch |
| `legacy_dielectrics` | `temperature_C` | `mechanical_properties` | `temperature_c` | capitalisation mismatch |
| `legacy_viscoelasticity` | `viscosity_mpa_s` | `rheology` | `viscosity_pas` | unit baked into column name, different units |

