# Schema Audit

Database: `/Users/zackwoodel/Desktop/dataset/data/materials.db`

## Objects

| Name | Type | Rows |
| --- | --- | ---: |
| `calculated_sld` | table | 68 |
| `calculated_slds` | table | 46 |
| `chemical_descriptors` | table | 252 |
| `dielectric` | table | 21 |
| `dielectrics` | table | 9 |
| `lab_measurements_needed` | table | 6 |
| `materials` | table | 23 |
| `optical_nk` | table | 2819 |
| `pubchem_data` | table | 17 |
| `references_db` | table | 34 |
| `sqlite_sequence` | table | 10 |
| `viscoelasticity` | table | 11 |

## Tables

### `calculated_sld`

Rows: 68

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `reference_id` | `INTEGER` | 0 | `None` | 0 |
| `energy_ev` | `REAL` | 0 | `None` | 0 |
| `wavelength_nm` | `REAL` | 0 | `None` | 0 |
| `frequency_hz` | `REAL` | 0 | `None` | 0 |
| `sld_xray_real` | `REAL` | 0 | `None` | 0 |
| `sld_xray_imag` | `REAL` | 0 | `None` | 0 |
| `sld_neutron_real` | `REAL` | 0 | `None` | 0 |
| `sld_neutron_imag` | `REAL` | 0 | `None` | 0 |
| `calculation_method` | `TEXT` | 0 | `None` | 0 |
| `notes` | `TEXT` | 0 | `None` | 0 |

Declared foreign keys:
- `reference_id` -> `references_db.id` (on delete: `NO ACTION`)
- `material_id` -> `materials.id` (on delete: `NO ACTION`)

### `calculated_slds`

Rows: 46

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `reference_id` | `INTEGER` | 0 | `None` | 0 |
| `energy_ev` | `REAL` | 1 | `None` | 0 |
| `wavelength_nm` | `REAL` | 1 | `None` | 0 |
| `xray_sld_real` | `REAL` | 1 | `None` | 0 |
| `xray_sld_imag` | `REAL` | 0 | `None` | 0 |
| `neutron_sld_real` | `REAL` | 1 | `None` | 0 |
| `neutron_sld_imag` | `REAL` | 0 | `None` | 0 |

Declared foreign keys:
- `reference_id` -> `references_db.id` (on delete: `NO ACTION`)
- `material_id` -> `materials.id` (on delete: `CASCADE`)

### `chemical_descriptors`

Rows: 252

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `descriptor_name` | `TEXT` | 1 | `None` | 0 |
| `value` | `REAL` | 1 | `None` | 0 |
| `source_library` | `TEXT` | 0 | `None` | 0 |

Declared foreign keys:
- `material_id` -> `materials.id` (on delete: `CASCADE`)

### `dielectric`

Rows: 21

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `reference_id` | `INTEGER` | 0 | `None` | 0 |
| `wavelength_nm` | `REAL` | 0 | `None` | 0 |
| `frequency_hz` | `REAL` | 0 | `None` | 0 |
| `energy_ev` | `REAL` | 0 | `None` | 0 |
| `dielectric_real` | `REAL` | 0 | `None` | 0 |
| `dielectric_imag` | `REAL` | 0 | `None` | 0 |
| `temperature_C` | `REAL` | 0 | `None` | 0 |
| `notes` | `TEXT` | 0 | `None` | 0 |
| `measurement_regime` | `TEXT` | 0 | `None` | 0 |

Declared foreign keys:
- `reference_id` -> `references_db.id` (on delete: `NO ACTION`)
- `material_id` -> `materials.id` (on delete: `NO ACTION`)

### `dielectrics`

Rows: 9

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `reference_id` | `INTEGER` | 0 | `None` | 0 |
| `frequency_hz` | `REAL` | 1 | `None` | 0 |
| `temperature_C` | `REAL` | 0 | `None` | 0 |
| `real_permittivity` | `REAL` | 1 | `None` | 0 |
| `imag_permittivity` | `REAL` | 0 | `None` | 0 |
| `measurement_regime` | `TEXT` | 0 | `None` | 0 |

Declared foreign keys:
- `reference_id` -> `references_db.id` (on delete: `NO ACTION`)
- `material_id` -> `materials.id` (on delete: `CASCADE`)

### `lab_measurements_needed`

Rows: 6

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `measurement_type` | `TEXT` | 1 | `None` | 0 |
| `instrument` | `TEXT` | 1 | `None` | 0 |
| `parameter` | `TEXT` | 1 | `None` | 0 |
| `frequency_range` | `TEXT` | 0 | `None` | 0 |
| `wavelength_range` | `TEXT` | 0 | `None` | 0 |
| `priority` | `INTEGER` | 1 | `None` | 0 |
| `reason` | `TEXT` | 1 | `None` | 0 |
| `protocol_notes` | `TEXT` | 0 | `None` | 0 |
| `status` | `TEXT` | 1 | `'needed'` | 0 |

Declared foreign keys:
- `material_id` -> `materials.id` (on delete: `NO ACTION`)

### `materials`

Rows: 23

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `name` | `TEXT` | 1 | `None` | 0 |
| `formula` | `TEXT` | 0 | `None` | 0 |
| `smiles` | `TEXT` | 0 | `None` | 0 |
| `molecular_weight` | `REAL` | 0 | `None` | 0 |
| `material_class` | `TEXT` | 0 | `None` | 0 |
| `notes` | `TEXT` | 0 | `None` | 0 |
| `density_g_cm3` | `REAL` | 0 | `None` | 0 |
| `pubchem_cid` | `INTEGER` | 0 | `None` | 0 |

Declared foreign keys:
- None declared.

### `optical_nk`

Rows: 2819

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `reference_id` | `INTEGER` | 0 | `None` | 0 |
| `wavelength_nm` | `REAL` | 1 | `None` | 0 |
| `n` | `REAL` | 1 | `None` | 0 |
| `k` | `REAL` | 0 | `None` | 0 |
| `source_ref` | `TEXT` | 0 | `None` | 0 |
| `temperature_C` | `REAL` | 0 | `None` | 0 |

Declared foreign keys:
- `reference_id` -> `references_db.id` (on delete: `NO ACTION`)
- `material_id` -> `materials.id` (on delete: `CASCADE`)

### `pubchem_data`

Rows: 17

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `material_name` | `TEXT` | 0 | `None` | 1 |
| `SMILES` | `TEXT` | 0 | `None` | 0 |
| `molecular_formula` | `TEXT` | 0 | `None` | 0 |
| `MW` | `REAL` | 0 | `None` | 0 |
| `XLogP` | `REAL` | 0 | `None` | 0 |
| `HBondDonors` | `REAL` | 0 | `None` | 0 |
| `HBondAcceptors` | `REAL` | 0 | `None` | 0 |
| `RotatableBonds` | `REAL` | 0 | `None` | 0 |
| `TPSA` | `REAL` | 0 | `None` | 0 |

Declared foreign keys:
- None declared.

### `references_db`

Rows: 34

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `doi` | `TEXT` | 0 | `None` | 0 |
| `citation_text` | `TEXT` | 1 | `None` | 0 |
| `url` | `TEXT` | 0 | `None` | 0 |
| `bibtex` | `TEXT` | 0 | `None` | 0 |

Declared foreign keys:
- None declared.

### `sqlite_sequence`

Rows: 10

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `name` | `` | 0 | `None` | 0 |
| `seq` | `` | 0 | `None` | 0 |

Declared foreign keys:
- None declared.

### `viscoelasticity`

Rows: 11

| Column | Type | Not Null | Default | Primary Key |
| --- | --- | ---: | --- | ---: |
| `id` | `INTEGER` | 0 | `None` | 1 |
| `material_id` | `INTEGER` | 1 | `None` | 0 |
| `reference_id` | `INTEGER` | 0 | `None` | 0 |
| `frequency_hz` | `REAL` | 1 | `None` | 0 |
| `temperature_C` | `REAL` | 0 | `None` | 0 |
| `storage_modulus_pa` | `REAL` | 0 | `None` | 0 |
| `loss_modulus_pa` | `REAL` | 0 | `None` | 0 |
| `viscosity_mpa_s` | `REAL` | 0 | `None` | 0 |

Declared foreign keys:
- `reference_id` -> `references_db.id` (on delete: `NO ACTION`)
- `material_id` -> `materials.id` (on delete: `CASCADE`)

## Views

No views found.

## Duplicate Material Names

No duplicate material names found after lower-case trim normalization.

## Orphan Records

No orphan records found for declared foreign keys.

## Missing Foreign Keys

No obvious missing material/reference foreign keys detected.

## Dataset Overlap

| Dataset A | Dataset B | Shared Materials | A Materials | B Materials |
| --- | --- | ---: | ---: | ---: |
| `calculated_sld` | `calculated_slds` | 17 | 17 | 23 |
| `calculated_sld` | `chemical_descriptors` | 16 | 17 | 22 |
| `calculated_sld` | `dielectric` | 15 | 17 | 21 |
| `calculated_sld` | `dielectrics` | 3 | 17 | 9 |
| `calculated_sld` | `lab_measurements_needed` | 4 | 17 | 4 |
| `calculated_sld` | `optical_nk` | 17 | 17 | 23 |
| `calculated_sld` | `viscoelasticity` | 9 | 17 | 9 |
| `calculated_slds` | `chemical_descriptors` | 22 | 23 | 22 |
| `calculated_slds` | `dielectric` | 21 | 23 | 21 |
| `calculated_slds` | `dielectrics` | 9 | 23 | 9 |
| `calculated_slds` | `lab_measurements_needed` | 4 | 23 | 4 |
| `calculated_slds` | `optical_nk` | 23 | 23 | 23 |
| `calculated_slds` | `viscoelasticity` | 9 | 23 | 9 |
| `chemical_descriptors` | `dielectric` | 20 | 22 | 21 |
| `chemical_descriptors` | `dielectrics` | 9 | 22 | 9 |
| `chemical_descriptors` | `lab_measurements_needed` | 4 | 22 | 4 |
| `chemical_descriptors` | `optical_nk` | 22 | 22 | 23 |
| `chemical_descriptors` | `viscoelasticity` | 9 | 22 | 9 |
| `dielectric` | `dielectrics` | 9 | 21 | 9 |
| `dielectric` | `lab_measurements_needed` | 4 | 21 | 4 |
| `dielectric` | `optical_nk` | 21 | 21 | 23 |
| `dielectric` | `viscoelasticity` | 7 | 21 | 9 |
| `dielectrics` | `lab_measurements_needed` | 2 | 9 | 4 |
| `dielectrics` | `optical_nk` | 9 | 9 | 23 |
| `dielectrics` | `viscoelasticity` | 3 | 9 | 9 |
| `lab_measurements_needed` | `optical_nk` | 4 | 4 | 23 |
| `lab_measurements_needed` | `viscoelasticity` | 4 | 4 | 9 |
| `optical_nk` | `viscoelasticity` | 9 | 23 | 9 |
