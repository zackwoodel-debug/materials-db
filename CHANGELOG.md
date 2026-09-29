# Changelog

All notable changes to the materials-db release (the SQLite database and its package). Format: [Keep a Changelog](https://keepachangelog.com);
versions follow the release tags. Counts are materials / optical datasets.

## [Unreleased]

## [0.20.1] - 2026-09-29 (2129 / 2605)

### Fixed
- The glass catalogs re-admitted three SCHOTT pages the glasses family had excluded on review (DURAN: one inconsistent
  refractive-index point; LITHOSIL-Q and LITHOTEC-CAF2: obsolete grades of materials already present). They are withdrawn;
  their permanent ids (1798-1800) are retired, never reused. Found by the new database audit (scripts/analyze_db.py).
  The catalog builder now honours every family's excluded pages.

## [0.20.0] - 2026-09-28 (2132 / 2608)

### Added
- Glass catalogs: 1,675 optical glasses from SCHOTT, OHARA, HIKARI, CDGM, HOYA, SUMITA and LZOS (manufacturer Sellmeier formulas,
  internal-transmittance k, datasheet densities; nd, Vd, glass code, dPgF, thermal expansion and status in the family table).
  Each formula reproduces its datasheet's nd and Vd. ML splits: optical equivalents share a group across makers.

## [0.19.0] - 2026-09-27 (457 / 933)

### Added
- 2D perovskites (Song 2021, films on glass): Ruddlesden-Popper (BA)2(MA)n-1PbnI3n+1, n = 1-5, and Dion-Jacobson
  (4AMP)(MA)m-1PbmI3m+1, m = 1-4. Formulas from charge neutrality of the ions the source names (its RP formula 'I3n-1' is a
  typo). Both series share 3D MAPbI3's ML split group (their n -> infinity limit).

## [0.18.0] - 2026-09-27 (448 / 924)

### Added
- Brass (90, 85 and 70 wt% Cu; Querry 1985) and permalloy Ni80Fe20 (four film variants; Tikuisis 2017). Their pages do not say
  atomic or weight %, but for Cu-Zn and Ni-Fe the readings differ by < 1 at.%. Au-Ag stays deferred (up to 15 at.%).

## [0.17.0] - 2026-09-27 (444 / 917)

### Added
- Alloys (57 materials): AlGaAs (16 compositions), AlGaSb, SiGe, ZnCdO, SiOx series; InGaAs, GaInP, AgGa0.86In0.14S2; KRS-5,
  KRS-6; yttria-stabilized zirconia and hafnia; MgO:LiNbO3, Mg:LiTaO3, ITO, AZO, AlON. Each composition is its own material
  with the fractional formula its page states; doped crystals without an exact composition have no formula.
- Perovskites (6): MAPbI3, MAPbBr3, CsPbBr3, CsPbCl3, CsPbBr1.3Cl1.7, CsPbBr1.8Cl1.2.
- ML splits: a composition series joins its first end member's group; no existing material moves.

## [0.16.0] - 2026-09-27 (381 / 831)

### Added
- Descriptors v2 (in `descriptor_json`; no schema change). Compositional: first ionization energy, electron affinity, molar
  volume, van der Waals radius, valence electrons (all and per s/p/d/f), s/p/d/f block fractions. Molecular: Crippen molar
  refractivity, sp3 fraction, valence electrons, ring / heteroatom / aromatic-atom counts, charge, topological indices.
  Chemistry: Pauling ionic character and oxidation-state guesses (labelled as guesses). Structural (194 MP entries): CrystalNN
  coordination, bond lengths, packing fraction; elastic moduli for 153. The ML feature matrix gains 75 columns.

## [0.15.0] - 2026-09-27 (381 / 831)

### Fixed
- Dispersion-formula datasets are sampled adaptively: interpolating the stored points is within 1e-6 of the formula in n
  (0.1% of n-1 for gases), where the fixed 500-point grid was up to 4e-3 off at 633 nm (ZnTe, TlBr, alkali halides) and far
  more elsewhere. Pages with a formula n and a tabulated k keep the table's own points, so k reproduces the table exactly
  (was up to 2.8% off at 633 nm). n and k at 633 nm in the family tables now agree with the stored rows. Optical rows
  719,720 -> 815,596; up to 7e-4 change in 633 nm consensus values; 3 new dataset comparisons.

### Added
- Spectral ML set (`data/ML_release_spectra.parquet`, not part of the release package): one row per optical dataset with n and
  k on a 128-point log grid (200 nm - 25 um), masks where the dataset has no data or a gap > 1.5x, no extrapolation.
- Grouped ML splits (`data/ML_splits.csv`): train / validation / test and 5 folds per group of materials (identical
  composition, or one product line), assigned by hash so a material keeps its split in later releases.
- ML package (`scripts/package_ml_dataset.py` -> `release/ml-dataset-vX.Y.Z.zip`): per-split Parquet, MLCommons Croissant
  1.1 metadata, a Hugging Face dataset card, Zenodo metadata; `CITATION.cff` at the repository root.
- Read-only access layer (`materials_db.access`): a Python library, an HTTP API and an MCP server for AI assistants over a
  release (search, material records with sources, n/k at a wavelength without extrapolation, comparisons, read-only SQL).
- Datasette browsing (`scripts/build_datasette.py`): described tables, a faceted material index, saved queries.

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
