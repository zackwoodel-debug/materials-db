# Dataset release v0.20.2: expected diff (declared before any edit)

Two maintainer-approved corrections (2026-09-30). The v0.20.2 build is compared with v0.20.1 as sorted logical records, table by
table; any difference not declared below is a failure.

## Declared changes

**A. `spr_data` view exposes the dataset (decision 2).** The view gains `dataset_label` and `raw_record_table` as its last two
columns, so rows of different phases / variants / axes at one wavelength can be told apart (e.g. "Water" includes amorphous and
crystalline ice at 10–150 K). Changed: the view definition in `updated_sql_schema.sql` and in the tracked base DB
(`data/materials_oxide_test.db`); the release's `spr_data` DDL. Its existing columns and rows are unchanged (same row count,
same values in the same columns).

**B. Material 38 identity (decision 4).** Material 38 (stable key `oxides_50:SiO2@amorphous`, **id unchanged**):

| Field | v0.20.1 | v0.20.2 | Evidence |
|---|---|---|---|
| `materials.name` | Silicon dioxide / quartz | Silicon dioxide (fused silica) | its only dataset, Malitson 1965: COMMENTS "Fused silica, 20 °C" |
| `materials.cas_number` | 14464-46-1 | 60676-86-0 | NIST Chemistry WebBook (SRD 69): 14464-46-1 = "cristobalite"; 60676-86-0 = "Silica, vitreous" (checked 2026-09-30) |
| `material_synonyms` (id 38) | Silica, Silicon dioxide, quartz | "quartz" removed; "fused silica" added; others as the curation rules give | "quartz" was derived from the old "A / B" name and is wrong for fused silica |

Changed files: `scripts/oxide_material_list.py` (name), `data/step1_selections.json` (name), `data/oxides_50.csv` (name,
cas_number, flags), `scripts/build_oxides_csv.py` (a documented CAS override so a rerun keeps it), `scripts/release_curation.py`
("fused silica" as a reviewed bracket synonym), the tracked base DB (the one `materials` row), one test fixture. Derived: the ML
sets' `meta_name` for material 38.

**Release metadata:** version 0.20.2; CHANGELOG entry; manifest (build time, git commit, lock hash, counts); README and data
dictionary text naming the version; the registry reports the name change (`name_changes`).

## Must be unchanged

Every optical value, missing-value mask, wavelength, temperature, dataset label and source of every dataset; every density,
SLD, dielectric and descriptor value; every material id and stable key; material 38's formula, PubChem CID, SMILES, InChIKey,
polymorph, density and density state; every other material's name, CAS and synonyms; sources and citations; exclusions;
dataset validation and consensus tables; primary-dataset selections and model-fit flags; the `xrr_data` view; all other table
and view definitions. Counts stay 2,129 materials / 2,605 datasets / 1,753,649 optical rows.
