# Dataset release v0.22.0: expected diff (declared before any edit)

Closes `as2s3_amorphous_in_polymorph`, the one exception v0.21.0 left (docs/release-0.21.0-expected-diff.md): As2S3 (batch 2,
material id 72) still has `polymorph = amorphous`. Same option (iii) pattern. Compared with v0.21.0 as sorted logical records,
every table; any undeclared difference is a failure.

## Evidence (Case A, for the optical and the density rows)

- Optical, Rodney 1958 (`main/As2S3/nk/Rodney.yml`): COMMENTS "Arsenic trisulfide glass. 25 C".
- Density 3.2 g/cm3: the AMTIR-6 datasheet (Amorphous Materials, Inc.) is for "amorphous As40S60 glass", and cites the same
  Malitson, Rodney & King 1958 paper for its own index table (scripts/fluoride_nitride_sulfide_material_list.py
  LITERATURE_DENSITY). Unlike the v0.21.0 oxides, whose density rows had an uncited structural basis and so lost the prefix, this
  density's source states the structure, so its rows carry `structure:amorphous` too.

## Declared changes

| Table | Rows | v0.21.0 | v0.22.0 |
|---|---|---|---|
| optical_dispersion `dataset_label` | 788 | `amorphous \| Rodney1958` | `structure:amorphous \| Rodney1958` |
| physical_properties `dataset_label` | 5 | `amorphous \| density_literature`, `amorphous \| xray_sld_real \| periodictable_CuKalpha`, ... | the same with `structure:amorphous` in place of the leading `amorphous` |
| consensus_properties `property_name` | 1 | `n_633nm \| amorphous` | `n_633nm \| structure:amorphous` |

Every value, wavelength, source and id in those rows is unchanged.

- **Family table:** `data/batch2_31.csv` As2S3 `polymorph` cleared (empty); its `flags` text is unchanged.
- **Derived:** the data dictionary's label vocabularies; the ML feature matrix `meta_primary_dataset_label` and the ML spectra
  `dataset_label` / `variant_or_phase` for As2S3 (as v0.21.0 did for SiO2). ModalFit export layer name and n,k file name lose
  `_amorphous` (`As2S3_amorphous` -> `As2S3`), as for the v0.21.0 materials.
- **Tracked base DB `data/materials_oxide_test.db`:** the same 793 rows (788 optical, 5 physical; it has
  no consensus rows), regenerated from the edited inputs; `tests/test_batch3b_loader.py` checks it is reproducible.

## Kept, with compatibility

- Material id 72 and its stable key `batch2_31:As2S3@amorphous` (a registry key alias from the newly derived `batch2_31:As2S3`);
  the ML `meta_key` / `key` stay `batch2_31:As2S3@amorphous`.
- Old labels keep resolving through `materials_db.core.label_aliases`: `amorphous | Rodney1958` (access layer, exporter),
  `As2S3[amorphous]` (XRR stack syntax) and `export_layer(..., "amorphous")`; a wrong label still raises.
- The structure-in-polymorph test's exception list becomes empty.

## Must be unchanged

Every n, k, wavelength, temperature, density, SLD, dielectric, descriptor value and missing-value mask; every source row;
exclusions; primary-dataset selections and model-fit flags; dataset validation; every other material's rows; ML splits, folds,
groups and keys; counts (2,129 materials / 2,605 datasets / 1,753,649 optical rows).
