# Phase 3: oxide "amorphous" evidence, and why the fix was not implemented

Status (2026-09-30): **the oxide_amorphous_migration fix was not implemented.** This phase recorded the evidence, the per-dataset
decisions and the couplings that block the fix under the current rules. No data, label, registry, selection-file or database
change was made. `data/materials.db` (SHA-1 229b951…) and `data/materials_oxide_test.db` (SHA-1 720dddf…) are unchanged.

The tracked task is `oxide_amorphous_migration` in `src/materials_db/pipeline/process_condition.py` (TRACKED_OPEN_TASKS). It is
now blocked on `oxide_density_labels_and_polymorph` (Phase 4A), which is blocked on `density_provenance_upgrade`.

## Where structure is represented today

- There is no dedicated per-dataset structure field. The only per-dataset slot is the optional first segment of `dataset_label`:
  `optical_dispersion.dataset_label` is "[variant or phase |] source tag [| axis]"; `physical_properties.dataset_label` is
  "[phase |] quantity[_origin] [| method]". That free-text slot already holds "amorphous", "single crystal" and "crystalline" in
  other families.
- For the five oxides below, the slot's text was copied from the family-table `polymorph` / `effective_polymorph`, not from
  per-page evidence.
- The process-condition grammar (`structure:amorphous`) exists in code, but no released label uses it.
- Each of the five materials has exactly one optical dataset, so material and dataset coincide today.

## Per-dataset classifications (optical)

Evidence is quoted from the pinned refractiveindex.info checkout (commit c5c2f18) or from this repository.

**A. SiO2, id 38, key `oxides_50:SiO2@amorphous`, page Malitson1965 (`main/SiO2/nk/Malitson.yml`)** — Case A (supported).
COMMENTS: "Fused silica, 20 °C"; reference title: "Interspecimen comparison of the refractive index of fused silica". Scope:
this optical sample only; it says nothing about any other SiO2 page.

**B. Ta2O5, id 39, key `oxides_50:Ta2O5@amorphous`, page Bright2013 (`main/Ta2O5/nk/Bright-amorphous.yml`)** — Case A.
COMMENTS: "Amporphous thin film" (sic); reference title: "Infrared optical properties of amorphous and nanocrystalline Ta2O5 thin
films". Also recorded in `src/materials_db/export/citations.py` (Ta2O5 verification_note). Scope: this optical sample.

**C. GeO2, id 20, key `oxides_50:GeO2`, page Fleming1984 (`main/GeO2/nk/Fleming.yml`)** — Case A.
Catalog page name (`catalog-nk.yml`): "Fleming 1984: Fused germania"; reference title: "Dispersion in GeO2-SiO2 glasses". Scope:
this optical sample. Its polymorph is None today and stays None.

**D. Nb2O5, id 33, key `oxides_50:Nb2O5@amorphous`, page Franta2024 (`main/Nb2O5/nk/Franta.yml`)** — Case D, BLOCKED.
COMMENTS: "Deposited by magnetron sputtering; Heterogenous data processing combining ellipsometric and spectrophotometric
measurements of five samples with thicknesses between 20 and 250 nm; Room temperature." Structure is never stated. This
repository's own note: "amorphous inferred from the Franta 2024 RI.info dataset's deposition method … the Franta paper itself was
not directly accessed to confirm". Recorded in `data/oxide_gaps.csv` (structure_unresolved).

**E. SiO, id 37, key `oxides_50:SiO@amorphous`, page Hass1954 (`main/SiO/nk/Hass.yml`)** — Case B.
No COMMENTS; reference title "Optical properties of silicon monoxide in the wavelength region from 0.24 to 14.0 microns"; no sample
description. The only other record ("SiO confirmed manually", `scripts/build_oxides_csv.py`) cites nothing. The "amorphous" label
is unresolved. Recorded in `data/oxide_gaps.csv` (structure_unresolved).

## Density records: all five BLOCKED

| Material | Density | Structural wording (repo note) | Source |
|---|---|---|---|
| SiO2 (38) | 2.20 | "literature: fused silica, standard value" | placeholder, sources id 4 |
| GeO2 (20) | 3.65 | "literature: fused (vitreous) GeO2, commonly cited value" | placeholder, sources id 4 |
| Ta2O5 (39) | 7.90 | "literature: amorphous Ta2O5 thin film, commonly cited value (vs 8.37 crystalline)" | placeholder, sources id 4 |
| SiO (37) | 2.13 | "literature: evaporated amorphous SiO film, commonly cited value" | placeholder, sources id 4 |
| Nb2O5 (33) | 4.45 | "stoichiometric amorphous Nb2O5 thin film density from XRR/RBS (amorphous inferred from …)" | sources id 40, Venkataraj 2001 (title states no structure) |

Sources id 4 is "Literature density estimate (amorphous/glass materials with no MP structure)", whose own note says "verify against
a primary source before relying on it"; it has no DOI. Evidence about a density sample stays on the density record and does not
transfer to any optical dataset. The labels and DENSITY_STATE of these records are unchanged. Recorded in `data/oxide_gaps.csv`
(density_provenance) and tracked as `density_provenance_upgrade`.

## Material 38 identity anomaly

Material 38 is named "Silicon dioxide / quartz" and carries CAS 14464-46-1, auto-picked as the first of 60 PubChem CAS numbers
(`data/oxides_50.csv` flags). That CAS is believed to denote cristobalite, a crystalline polymorph; this was not verified in this
session (no network), and nothing in the repository records what it denotes. Its only dataset is fused silica. The identity
metadata therefore contradicts its data. Not changed; tracked as `material38_identity_correction` and recorded in
`data/oxide_gaps.csv` (identity_conflict).

## Why the fix was not implemented: two couplings (proven in scratch)

Both were demonstrated by running the oxide family loader (`scripts/load_family_db.py` `run_family`, as `load_oxides_db.py`
calls it) into a scratch directory outside the repository, on copies of the inputs.

1. **Clearing polymorph changes 20 physical-property labels.** The loader builds every physical-property label from the family
   CSV's polymorph: `label_join(csv_polymorph, "density_literature")` and likewise for the four SLD rows. With the committed
   inputs, the rebuilt labels equal the tracked base DB's exactly (optical and physical). With polymorph cleared for Nb2O5, SiO,
   SiO2 and Ta2O5, every optical label is unchanged but 20 physical labels change (5 per material), e.g.
   `amorphous | density_literature` -> `density_literature`, `amorphous | xray_sld_real | periodictable_CuKalpha` ->
   `xray_sld_real | periodictable_CuKalpha`. No value changes. These are exactly the BLOCKED density rows, so clearing
   polymorph takes a position on them. Under the Phase 3 rules (no density-label change, base-DB SHA unchanged, the tracked DB
   reproducible from its own inputs) the three cannot all hold.
2. **selection_key alone cannot keep the registry keys.** `material_key()` uses `selection_key` before `formula@polymorph`, but
   the loader also uses `selection_key` as the key into `data/step1_selections.json`, which is keyed by formula. A column filled
   for only the five oxides is rejected (`CatalogError: blank selection_key in row(s) [2, 3, … 51]`); a column filled for all 50
   rows with the current key suffixes (`SiO2@amorphous`, `TiO2@rutile`, …) misses every selections lookup for an oxide with a
   polymorph, so its optical load is skipped, unless the selections file is re-keyed.

The category-error fix (moving "amorphous" out of polymorph) and the density decision are therefore entangled in the current
representation. Phase 4A (`oxide_density_labels_and_polymorph`) is to resolve the density rows first, then clear polymorph with
declared label changes, re-key selections if needed, and rebuild the base DB under a strict parity gate.

## Source lookups (2026-09-30)

A literature lookup for the blocked rows is recorded per entry in `data/oxide_gaps.csv` (column `source_lookup_2026_09_30`), with its verification level. In short: Franta 2024 and Hass 1954 still state no structure (Nb2O5 stays Case D, SiO Case B; Hass 1954 does describe its samples as evaporated films); Venkataraj 2001 states its own films are amorphous (GIXRD), which concerns the density sample only; candidate sources for the SiO2 and Ta2O5 densities could not be verified (publisher pages refused automated access) and the Ta2O5 candidate gives 7.98, not 7.90; nothing primary was found for GeO2 3.65 or SiO 2.13. No classification, label or value changed as a result.

## Deferred, not addressed here

- `mp_id` packaging (Phase 4): installed and checkout ModalFit exports were not equivalent. Resolved on 2026-09-30 by ADR 0001.
- The ModalFit exporter fills unmeasured k with 0.0: an open scientific-correctness issue conflicting with guardrail 1 (unknown k
  is not zero). Existing zero-filled exports are not evidence the semantics are correct.
- The unsynced vendored citation copies in `modalfit_db_export/citations.py` and `modalfit_export.py` (Phase 6).
- Material 38 identity correction (`material38_identity_correction`).
