# Changelog

All notable changes to the materials-db release (the SQLite database and its package). Format: [Keep a Changelog](https://keepachangelog.com);
versions follow the release tags. Counts are materials / optical datasets.

## [Unreleased]

### Added
- Spectral ML set (`data/ML_release_spectra.parquet`, not part of the release package): one row per optical dataset with n and
  k on a 128-point log grid (200 nm - 25 um), masks where the dataset has no data or a gap > 1.5x, no extrapolation.

## [0.14.0] - 2026-09-27 (381 / 831)

### Added
- Permanent material ids: `material_id` no longer changes between releases (it used to follow the load order: 150 of 379
  materials changed id between v0.12.0 and v0.13.0). v0.13.0's ids are kept; new materials get new ids; ids are never
  reused. `material_registry.csv` gives each id a stable text key (`semiconductors:GaAs`, `oxides_50:TiO2@rutile`).
- Data dictionary: `data_dictionary.json` and `DATA_DICTIONARY.md` describe every table and column (type, key, unit,
  meaning), the label grammar and the vocabularies found in the data; the build stops if they drift from the schema.
- This changelog, shipped in the package; a versioned build requires an entry for its version.
- ML set: `meta_key` (the stable key).

No data values changed from v0.13.0.

## [0.13.0] - 2026-09-27 (381 / 831)

### Added
- Ge2Sb2Te5 (crystalline and amorphous, Frantz 2024), no density (the source does not state the crystal structure).
- GaSe, with non-physical formula samples (n^2 <= 0 in the reststrahlen band) dropped and Kato 2013 sampled over its
  stated 0.8-162 um; epsilon-GaSe density.

### Changed
- Primary dataset: a model fit covering 633 nm is primary only when no measured dataset covers it; CdTe, CdSe and PbSe
  now have n(633 nm).
- Liquid crystals prefer a dataset with a stated temperature (5CB and E7 primaries at 25 degC).

## [0.12.0] - 2026-09-27 (379 / 823)

### Added
- Gases: air, N2, O2, rare gases (with liquid and solid Ar/Kr/Xe), H2, D2, CO, CO2, NH3, SF6, C1-C2 hydrocarbons. Pressure
  is part of the variant label; temperature on every row.

## [0.11.0] - 2026-09-27 (361 / 728)

### Added
- Biological media: PBS, DMEM, human blood (whole blood, serum, plasma), adipose, liver and colon tissue.

### Fixed
- Optical media's molecular-descriptor note wrongly said "extended inorganic solid".

## [0.10.0] - 2026-09-27 (355 / 713)

### Added
- Liquid crystals: 5CB, 5PCH and seven commercial mixtures, ordinary and extraordinary rays, temperature series.

## [0.9.0] - 2026-09-26 (346 / 668)

### Added
- MicroChem 495 and 950 PMMA resists.
- Optical media: Cargille index-matching liquids, Norland NOA 61 (cured), Eukitt and FluorSave mounting media.

## [0.8.0] - 2026-09-26 (336 / 655)

### Added
- Glasses: soda-lime variants, SCHOTT N-BK7 / B 270 / BOROFLOAT 33 / D 263 T eco / AF 32 eco / ZERODUR, Corning EAGLE XG,
  LZOS K108, BGG, ZBLAN.

## [0.7.0] - 2026-09-26 (325 / 632)

### Added
- Inorganic batch 4: berlinite, anhydrite, KDP, ADP, KTP, RTP.

## [0.6.0] - 2026-09-26 (319 / 617)

### Added
- Materials Project DFPT dielectric constants (static and electronic) for 86 materials, where MP's band gap is >= 0.5 eV
  and the MP entry is the material itself.

## [0.5.0] - 2026-09-25 (319 / 617)

### Added
- `material_synonyms` (220 names) and Crossref DOIs for 5 citations.

### Fixed
- 23 duplicate source rows merged.

## [0.4.0] - 2026-09-25 (319 / 617)

### Added
- `dataset_validation` (like-for-like comparisons of datasets) and `consensus_properties` (n, k at 633 nm from measured
  datasets).

## [0.3.0] - 2026-09-25 (319 / 617)

### Added
- Compound semiconductors: III-V, tellurides, chalcopyrite pnictides, with temperature series.

### Changed
- Primary dataset: measured data before model fits of the dielectric function.

## [0.2.1] - 2026-09-25 (303 / 533)

### Fixed
- 37 bulk-approximation densities cited another batch's literature source.
- Wavelength ranges were empty for 134 family-table rows.

## [0.2.0] - 2026-09-25 (303 / 533)

### Added
- Liquids and biomolecules family (75 materials).

## [0.1.0] - 2026-09-25 (228 / 351)

- First release: oxides, fluorides/nitrides/sulfides, pure elements, polymers, inorganic batch 3, halides, chalcogenides,
  with compositional, structural and molecular descriptors.
