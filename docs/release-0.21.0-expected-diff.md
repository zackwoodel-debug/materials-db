# Dataset release v0.21.0: expected diff (declared before any edit)

Phase 4A, maintainer decisions of 2026-09-30 / 2026-10-01: option (iii) (structure in the process-condition grammar) and the
batch-3b citation-note fix. Compared with v0.20.2 as sorted logical records, every table; any undeclared difference is a failure.

## Why

"Amorphous" is a structure / process condition, not a polymorph (process_condition.py). It sat in the polymorph slot of four
oxides (Nb2O5, SiO, SiO2, Ta2O5) and Boron. Structure is now asserted only where the dataset's own recorded evidence states it
(docs/phase3-evidence-and-couplings.md), in the repository's process-condition grammar (`structure:amorphous`), which the
ModalFit exporter recognises as not a polymorph, so optical and density rows still pair.

## Declared changes

**Optical `dataset_label` (every row of the dataset; values, wavelengths, sources unchanged):**

| Material (id) | v0.20.2 | v0.21.0 | Basis |
|---|---|---|---|
| SiO2 (38) | `amorphous \| Malitson1965` | `structure:amorphous \| Malitson1965` | Case A: COMMENTS "Fused silica, 20 °C" |
| Ta2O5 (39) | `amorphous \| Bright2013` | `structure:amorphous \| Bright2013` | Case A: COMMENTS "Amporphous thin film" |
| GeO2 (20) | `Fleming1984` | `structure:amorphous \| Fleming1984` | Case A: catalog page "Fleming 1984: Fused germania" |
| Nb2O5 (33) | `amorphous \| Franta2024` | `Franta2024` | not stated (Case D); gap kept |
| SiO (37) | `amorphous \| Hass1954` | `Hass1954` | not stated (Case B); gap kept |
| Boron | `amorphous \| FernandezPerea2007` | `FernandezPerea2007` | not stated ("Film deposited at room temperature"); gap recorded |

**Physical `dataset_label` (density + 4 SLD rows each; values unchanged):** the leading `amorphous | ` is removed for Nb2O5, SiO,
SiO2, Ta2O5 and Boron (25 rows), e.g. `amorphous | density_literature` -> `density_literature`. The density rows assert no
structure: their structural basis is uncited (`density_provenance_upgrade`, still open). GeO2's physical labels are unchanged.

**Family tables:** `polymorph` cleared (empty) for those five materials (`oxides_50.csv`, `batch3b_4.csv`).

**Derived:** `consensus_properties.property_name` for these materials follows the label's phase segment (e.g.
`n_633nm | amorphous` -> `n_633nm` for Nb2O5 and SiO; `n_633nm | structure:amorphous` for SiO2 and GeO2); the data dictionary's
label vocabularies; the ML spectra `label` column for these six datasets. ModalFit export layer and n,k file names for these
materials lose the `_amorphous` suffix (e.g. `SiO2_amorphous_nk.csv` -> `SiO2_nk.csv`).

**Batch-3b citation notes (decision 4):** two source notes ("Cited for C density ..." and "Cited for B density ...") name
`data/batch3b_4.csv` instead of the wrong `data/oxides_50.csv`.

**Tracked base DB `data/materials_oxide_test.db`:** regenerated from the edited inputs with the loaders (reproducible, tested);
it differs from today's only in the rows above.

## Kept, with compatibility

- Every material id and stable registry key (`oxides_50:SiO2@amorphous` etc. stay the keys: the registry gains a tested key
  alias from the new derived key to the registered one; no id is minted or retired).
- Old labels keep resolving: `SiO2[amorphous]` (XRR stack syntax), `export_layer(..., "amorphous")`, and every old optical
  `dataset_label` in the access layer map to the new label through one tested alias table; an unknown label still raises.
- Not in scope, recorded as an explicit exception: As2S3 (batch 2) still has `polymorph = amorphous` (tracked).

## Must be unchanged

Every n, k, wavelength, temperature, density, SLD, dielectric, descriptor value and missing-value mask; every source identity
and citation other than the two notes above; exclusions; primary-dataset selections and model-fit flags; dataset validation;
every other material's labels, names and synonyms; counts (2,129 materials / 2,605 datasets / 1,753,649 optical rows).
