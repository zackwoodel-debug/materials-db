# Adding a material family (nitrides as the worked example)

Run from repo root. MP_API_KEY comes from `.env` (never printed). Schema is frozen (Aiden): polymorph/axis live in `dataset_label`.

1. match:   `python3 scripts/match_ri_info_nitrides.py`  -> data/nitride_ri_matches.json, data/step1_selections_nitrides.json
   (multi-match = selection left null + flagged; only prior human selections are carried over; missing = gap)
2. select:  edit data/step1_selections_nitrides.json / USER_SELECTIONS by hand to resolve a null. Never auto-picked.
   Si3N4: optical = amorphous film (Luke primary, Philipp secondary), encoded `amorphous | Luke2015` (isotropic => axis segment omitted, same as
   TiN/VN, since migration 004 is unapplied); density/SLD = calculated crystalline beta mp-988, labeled `beta | ...`. Not the same phase.
   Kischkat/Beliaev/Vogt x3 (non-stoichiometric SiNx) are logged in nitride_gaps.csv, not loaded.
3. build:   `python3 scripts/build_nitrides_csv.py`  -> data/nitrides.csv, data/nitride_gaps.csv
4. load:    `python3 scripts/load_nitrides_db.py [--dry-run] [--strict] [--report out.json]`  -> fresh data/materials_nitride_test.db
5. audit:   `python3 -m pytest tests -q`;  `PYTHONPATH=.:src python3 src/materials_db/verify_all.py`;
            audit: `python3 -c "import sys;sys.path.insert(0,'src');from materials_db.core.audit import run_audit;run_audit()"`
6. merge:   families go into the release DB only: `python3 scripts/build_release.py --version X.Y.Z` (upserts every family onto
            data/materials_oxide_test.db; see README "Downloadable dataset"). Do NOT merge into data/materials_normalized.db (below).
7. parquet: `python3 scripts/generate_ml_training_set.py` (reads data/materials_normalized.db ONLY; refits the scaler).

DECIDED 2026-09-25: materials_normalized.db is NOT merged into. It stays frozen as the legacy 23-material benchmark its guard tests
pin (2819 optical rows, a descriptors row per material). Reason: its SLDs are in 1/A^2 (Au xray 1.31e-4) and repeated 4-6x per
material, while the families store 1e-6/A^2 with anomalous-scattering terms (Au xray 116.5); a merge would mix both in one column.
The release DB (release/materials-db-vX.Y.Z/*.sqlite, published on GitHub) is the canonical database. The rehearsal merge (+6
nitrides, parquet 23 -> 29, no conflicts) is therefore not pursued, and the 4 guards stay as they are.
data/materials.db is the legacy schema and cannot take these tables; audit/verify_all read it and do not exercise nitrides.
Generic loader: scripts/load_family_db.py (--family/--catalog/--selections/--db/--fresh/--dry-run/--strict/--report).

## FOLLOW-UPS
1. DONE (decision above): guard tests kept; materials_normalized.db is not merged into.
2. DONE (PR #16): parquet regenerated; only BSA (wrong SMILES, was N,O-bis(trimethylsilyl)acetamide) and the Al2O3/ZnO fingerprints changed.
3. DONE (PR #18): wider than TiN/VN. 37 bulk_elemental_approximation densities (TiN, VN, EuS, 33 elements, Sn) cited another batch's
   literature source; the legacy loaders now cite an "MP bulk DFT density used as a film approximation" source. Values unchanged.
4. DONE (PR #17): ri_wl_min_nm / ri_wl_max_nm were empty for 134 rows (nitrides, halides, chalcogenides, inorganic3, liquids); now
   taken from the parsed primary-axis data.
5. Non-stoichiometric SiNx (Kischkat, Beliaev, Vogt x3) not yet modelled; no SiNx material rows exist.
6. Migrations 002-004 pending Aiden. Until 004, polymorph/axis live in dataset_label.
7. After PRs #17 and #18 merge, publish v0.2.1 (v0.2.0 on GitHub still has the old citations and empty ranges).
8. DONE: release ML set, `python3 scripts/generate_ml_release_set.py` -> data/ML_release_feature_matrix.parquet (303 materials;
   targets n,k at 633 nm + density; features = compositional/structural/molecular descriptors; unscaled; no target leaks into
   features). The legacy generate_ml_training_set.py / ML_feature_matrix.parquet stay with the frozen benchmark DB.
   Regenerate after every release build; tests/test_ml_release_set.py checks it matches the newest local release.
9. Negative k: already decided before this note. build_release.NEGATIVE_K_ALLOWED (kept equal to tests/test_family_optical_sanity.py)
   allow-lists noise around k = 0 per dataset with a floor: Cu2O Querry, Fe2O3 Querry-o, ma-N 1407 Sarkar, and now GaP Jellison1992
   (-0.003, 500-815 nm). The ML set flags them (meta_primary_has_negative_k). Nothing to do.
10. DONE (user decision 2026-09-25): primary rule is now "measured before model fits, then widest range" in the auto-selected
   families (halides, chalcogenides, liquids, semiconductors); scripts/dataset_kind.py classifies a page as a model fit only on
   explicit source evidence (RI.info calculation script, "fit ... to a simplified model", or a title whose subject is a model).
   Changed primaries: 9 semiconductors (4 III-Vs now Aspnes & Studna 1983) + CdSe, PbSe. CdTe, CdSe, PbSe now have no primary
   n_633: RI.info has no MEASURED data at 633 nm for them (only Adachi-group model fits, still loaded). The ML set takes the
   primary from each release's own family table. Ge2Sb2Te5 deferred.

11. DONE: cross-source validation (scripts/release_validation.py, build stage 3b). dataset_validation: 351 like-for-like pairs over
   52 materials (291 excellent / 51 warning / 9 suspicious); consensus_properties: 424 rows, n and k at 633 nm per phase/axis from
   measured ambient datasets only. Real findings surfaced: InP Panah2016 vs Pettit1965 differ 11% at 5-10 um (both measured);
   As2Se3 400 vs 700 nm films differ 17% in k. Next depth steps (see chat plan): per-dataset metadata table (Aiden), recorded
   uncertainties, synonyms + missing DOIs (99/317), CI.

12. Uncertainties (plan step 3): NOT built. Only 2 of 617 datasets state one numerically (Perner GaAs: relative 3.3e-4 on n;
   Schnepf PVA: k = 0.0050 +- 0.0004), with different meanings, so sources.uncertainty stays empty; the usable uncertainty is the
   cross-source spread in consensus_properties. Revisit with the per-dataset metadata table (Aiden) and the original papers.
13. DONE (plan step 4, scripts/release_curation.py, build stage 3a): 23 duplicate source rows merged (317 -> 294), 5 Crossref DOIs
   (scripts/fetch_source_dois.py -> data/descriptors/source_dois.json; 20 citations have none: reports, theses, datasheets,
   handbooks, a conference abstract); 220 synonyms for 144 materials (PubChem titles cached by scripts/fetch_pubchem_titles.py).
   Every name bracket is reviewed in release_curation.NAME_SYNONYMS / NAME_QUALIFIERS; an unreviewed one stops the build.
14. Naming ambiguity in our own data: Bi12GeO20 is "Bismuth germanate" and Bi4Ge3O12 is "Bismuth germanate (BGO)"; RI.info calls
   both "Bismuth germanate, BGO". Consider renaming Bi12GeO20 (e.g. "Bismuth germanium oxide (sillenite)").

15. DONE: MP DFPT dielectric constants (scripts/fetch_mp_dielectric.py -> data/descriptors/mp_dielectric.json; build stage 4b
   scripts/release_dielectric.py): static + electronic epsilon for 86 materials. Not stored: 5 where the MP entry is only a
   crystalline reference (film/amorphous), 10 with MP band gap < 0.5 eV (Ge, GaAs, InP, GaSb, InSb, PbS, PbSe, Te, AGSe, hematite:
   +30..+62% vs measured). Kept values: -3..+11% for insulators, +11..+26% for semiconductors. Possible next: experimental static
   epsilon from literature for the semiconductors, and dielectric as ML features/targets.

16. DONE: inorganic batch 4 (scripts/*inorganic4*): AlPO4 berlinite, CaSO4 anhydrite, KDP, ADP, KTP, RTP (6 materials, 15
   datasets). Earlier "remaining crystals" estimate was wrong: CaO, SrO, Ga2O3, Er2O3, Gd3Ga5O12, YAlO3, KTiOAsO4, DyScO3 hold only
   nonlinear n2 data (catalog-n2.yml). ZrO2 deferred (YSZ 12 mol% Y2O3 in other/mixed crystals, an oscillator-model fit,
   nanoparticles): with the composition convention. MgH2/TiH2 (films), Ti3C2 (MXene), MoOCl2 (layered) -> 2D/thin-film follow-up.
   The main shelf is now exhausted except gases, 2D/layered books and logged deferrals. fetch_source_dois.py now only grows its cache
   (a rebuilt release carries the cached DOIs, which the old version then dropped).

17. DONE: glasses family (scripts/glass_material_list.py, build_glasses_csv.py, load_glasses_db.py): 11 glasses, 23 datasets.
   Soda-lime (window glass clear/low-iron/bronze/grey/green + far-IR, microscope slide air/tin side, Fe2O3 5/10/703 ppm, Optiwhite
   float) as one material with variant-labelled datasets; SCHOTT N-BK7 (+ Lane BK7 IR), B 270, BOROFLOAT 33, D 263 T eco, AF 32 eco,
   ZERODUR; Corning EAGLE XG; LZOS K108; BGG; ZBLAN. Formula NULL (no SLD/structure); density only from datasheets (4). DURAN
   excluded (single n point; page nd 1.527 contradicts its n 1.473). Next coverage without decisions: IR chalcogenide glasses need
   mapping onto As2S3/As2Se3 + composition convention; resists/adhesives/immersion oils/index liquids/commercial polymers next.

18. DONE: MicroChem PMMA resists as polymer-family photoresists: PMMA-495-resist (spec sheet) and PMMA-950-resist (spec sheet
   primary + Tsuda 2018 950k film baked 100 degC + its Lorentz-Drude and Brendel-Bormann IR fits). They were deferred only to keep
   them out of BULK PMMA. Unchanged earlier decisions: uncured SU-8 2000 / IP-S / IP-Dip are not material constants (user
   decision); ma-N 405 : ma-T 1050 1:1 mixture stays BLOCKED. match_ri_info_polymers RESOLUTIONS accept an optional `labels` list.
   The 950 resist's formula (C5H8O2)n comes from the RI.info PMMA book; the 495 book states none (source-only rule).

19. DONE: optical media (scripts/optical_media_material_list.py, build_optical_media_csv.py, load_optical_media_db.py): Cargille
   BK7 / fused silica 06350 / 50350 / acrylic / acrylic double matching liquids (densities at 25 degC), Norland NOA 61 (cured spec
   sheet), Eukitt and FluorSave mounting media (NIR only). The glass builder is now the shared scripts/listed_family.py (glass
   outputs byte-identical). Deferred: Loctite 3526, NOA 170, NOA 1348 (Iezzi 2020 films, cure state not stated) and NOA 61 Joseph
   (uncured). Immersion oils: k only, nothing to load. Cross-check: each matching liquid's n(633) equals its target material.

20. DONE: liquid crystals (scripts/liquid_crystal_material_list.py, build_liquid_crystals_csv.py, load_liquid_crystals_db.py):
   5CB and 5PCH (PubChem identity, molecular descriptors) + E7, E44, MLC-6241-000, MLC-6608, MLC-9200-000, MLC-9200-100, TL-216
   (formula NULL), 45 datasets, o-ray / e-ray, Wu 1993 temperature series labelled Wu1993-<T>C (all below the clearing point).
   Excluded: 5CB Wu-27.2C-e duplicates the 29.9 degC page (source error). listed_family.py now takes optional axis, tag_suffix and
   PubChem identity (glass / optical-media outputs byte-identical). Test helper evaluates RI.info formulas 3 and 6 too.
   Note: primaries of 5CB and E7 are Tkachenko 2006 (widest), whose temperature is not stated; 25 degC data (Li, Wu) are loaded.

21. DONE: biological media (scripts/bio_media_material_list.py, build_bio_media_csv.py, load_bio_media_db.py): PBS (DPBS, + EDTA
   + BSA, 10x), DMEM (plain, + FBS, HEPES + FBS), human blood (whole blood Liu / Rowe, serum, plasma), adipose, liver, colon
   (mucosa / submucosa / serosa); 6 materials, 15 datasets. CAUTION recorded: Liu 2019 whole blood as RI.info reconstructs it
   gives n(633) = 1.348, near serum/plasma, below typical whole blood (~1.38-1.40). Rowe 2017 k noise (to -0.0049 at 2.07 /
   2.33 um) allow-listed. DMEM + 10% FBS reads 0.001 below plain DMEM (within uncertainty). Deferred with the composition
   convention: water:glycerol 20/50 wt%, heavy water:glycerol 25/50/75 wt% (source error: the 50/75 pages say "25 wt%").
   Descriptor text fix: optical media's molecular note said "extended inorganic solid" (published in v0.9.0 / v0.10.0, a text
   note, not a data value); now "a mixture ..., not a single molecule". (A material_kind slip made during this branch was
   caught by the release test before any release.)

22. DONE: gases (scripts/gas_material_list.py, build_gases_csv.py, load_gases_db.py): air, N2, O2, Ar, He, Ne, Kr, Xe, H2, D2, CO,
   CO2, NH3, SF6, CH4, C2H6, C2H4, C2H2 (18 materials, 95 datasets). Pressure lives in the variant label (no pressure column):
   "gas, 101.325 kPa", "gas, 100 kPa", "gas" (unstated); Ar/Kr/Xe liquid and solid phases labelled by phase. listed_family.py
   gained per-page temperature_c overrides (Koch's "lambda_air at 15 degC" is not the gas temperature) and per-material
   not_primary variants (a gas at unstated conditions or a condensed phase is never primary). Excluded: Martonchik 1994 methane
   (liquid pages carry the solid comment; the source warns against interpolation). D2 has no PubChem record (written as H2).

23. DONE (user decisions 2026-09-27): (a) primary_rank in dataset_kind.py: measured covering 633 > model covering 633 > measured
   > model -- CdTe, CdSe, PbSe now have n_633 from their Adachi-group fits; nothing else changed primary. (b) Ge2Sb2Te5 loaded
   (crystalline / amorphous, Frantz 2024), density empty (NO_DENSITY). (c) GaSe loaded with the recorded fix: loader options
   drop_nonphysical_n and formula_range_um (parse_file override), epsilon-GaSe mp-1572 density. (d) Liquid crystals prefer a
   stated temperature (5CB -> Wu1993-25.1C, E7 -> Li2005). (e) Iezzi adhesive films of unstated cure: stay deferred.

24. DONE: permanent material ids (scripts/material_registry.py, data/material_registry.json, seeded from v0.13.0): the build
   renumbers every material to its registry id (stage 1b); an unregistered material stops the build unless
   `build_release.py --register-new` (then commit the registry). Stable key <family table>:<selection_key> or
   <family table>:<formula>@<polymorph>. Releases ship material_registry.csv; the ML set has meta_key. Before this, 150/379 ids
   changed between v0.12.0 and v0.13.0.
   WARNING: the repo lives in an iCloud-synced Desktop. iCloud created 66 " 2" conflict copies of files written this session
   (moved to ../materials-db_icloud_conflict_copies_2026-09-27; all identical to current or earlier committed versions) and
   likely caused a stalled git push and a stalled test run. Move the repo out of iCloud (e.g. ~/code) to avoid corruption.

25. DONE: data dictionary (scripts/release_dictionary.py -> data_dictionary.json + DATA_DICTIONARY.md in every package) and
   CHANGELOG.md (shipped; a versioned build needs a '## [X.Y.Z]' entry, checked before building; 0.0.0* exempt). The dictionary is
   introspected from the release DB + curated descriptions in release_dictionary.TABLES; an undescribed or vanished column stops
   the build. When adding a column or table, describe it there. Before each release: move [Unreleased] notes under the version.
26. DONE: spectral ML set (scripts/generate_ml_spectra.py -> data/ML_release_spectra.parquet + _metadata.json): one row per
   optical dataset, n/k on 128 log-spaced wavelengths 200-25000 nm, linear in log-wavelength inside the dataset's own range only,
   masked across gaps > 1.5x (MAX_GAP_RATIO). From v0.14.0: 813 datasets / 365 materials, 255 with k, 18 datasets entirely
   outside the grid (listed in the metadata). Regenerate after each release, like the per-material ML set. Split by material_id.
27. DONE: grouped splits (scripts/generate_ml_splits.py -> data/ML_splits.csv + metadata). Groups: identical element fractions
   (polymorphs, isomers, grades, monomer/polymer, H2O/D2O), PRODUCT_LINES for formula-less grades (Cargille, silk, MLC-9200,
   EpoClad/EpoCore, IP-S/IP-Dip), else the material. split = sha256(group) mod 10 (8/1/1), fold = independent hash mod 5: stable
   across releases. v0.14.0: 345 groups, 303/42/36 materials. When adding a formula-less grade of an existing line, add it to
   PRODUCT_LINES. Regenerate after the feature matrix.
28. DONE: ML package (scripts/package_ml_dataset.py -> release/ml-dataset-v<rel>/ + .zip, deterministic; CITATION.cff copied to
   the root). materials/ and spectra/{train,validation,test}.parquet carry group/split/fold; croissant.json (Croissant 1.1)
   validated with mlcroissant 1.1.0 (no warnings, all 381 + 813 records load, arrays of 128); README.md loads with HF
   datasets (configs materials [default] and spectra). Neither tool is a dependency: validate in a throwaway venv.
   Release order: SQLite release -> generate_ml_release_set -> generate_ml_spectra -> generate_ml_splits -> package_ml_dataset.
   NOT uploaded. To publish (user's accounts):
     Hugging Face: hf upload <user>/materials-db release/ml-dataset-v<rel> . --repo-type dataset
     Zenodo: new upload, attach the zip, copy fields from .zenodo.json (or the REST API with a token); the DOI then goes in
     CITATION.cff and the card.
29. DONE: agent access (src/materials_db/access/: db.py library, http.py FastAPI, mcp_server.py). Read-only three ways: SQLite
   mode=ro + PRAGMA query_only + an authorizer allowing only SELECT/READ/FUNCTION on ad-hoc SQL. n,k at a wavelength: LINEAR in
   wavelength between the dataset's stored points, inside its range only, as validation and the ML feature matrix do (test: 60
   materials to 1e-9). Only the spectra grid uses log-wavelength. CORRECTION (item 30): the family tables' n_633 is NOT this for
   formula pages; they evaluate the formula exactly. Primary = primary_pages()
   (needs the repo's selection inputs; info() reports primary_unavailable otherwise). Ambiguous names raise with candidates
   (MCP: ToolError, since the SDK hides other exceptions' text). Checked end to end over stdio with mcp 2.2.0 (MCPServer) and
   1.30.0 (FastMCP). The legacy api/server.py (MatChat) is untouched and still reads data/materials.db.
30. DONE (option b, user decision 2026-09-27): two n(633 nm) values existed for formula datasets. The family tables' n_633 evaluates
   the dispersion formula exactly at 633 nm; optical_dispersion stores the formula SAMPLED, and everything that interpolates the
   stored points (ML target_n_633nm, spectra, validation, consensus, materials_db.access) gets a slightly different number.
   v0.14.0: 109 materials differ; most < 1e-6 relative, ~20 halides/chalcogenides 1e-5..3e-4, ZnTe (Li1984) 1.4e-3, TlBr (Palik)
   1.2e-3. Options: (a) ML target_n_633nm takes the family n_633 where it exists (more accurate; changes 109 targets slightly);
   (b) sample formula pages more densely at build (changes optical_dispersion rows); (c) leave and document. Currently (c); the
   Datasette index shows the family value with n_633_origin.
   FIX: fetch_optical_data.sample_formula samples a formula ADAPTIVELY: 500 log-spaced points, then midpoints wherever linear
   interpolation misses the formula by > min(1e-6, 1e-3*|n-1|); only physical intervals (1e-3 < n < 10) are refined, so poles
   (Xe Bideau-Mehu 146.96 nm, GaSe reststrahlen) keep the base grid and never get n <= 0 samples; the page's tabulated-k
   wavelengths are forced samples, so stored k reproduces the table exactly (it was an interpolation of an interpolation: CCl4
   k(633) 2.8% off, Cargille 2.4%). scripts/resample_formula_data.py moved the tracked base DB (98 datasets, 49000 -> 64784 rows)
   and the CSVs whose numbers came from the old grid (base catalogs' n/k cells; later families' k cells and flag values), each
   number proven to be the old computation before it is replaced; idempotent. Result (test build): family n_633 vs interpolated
   stored rows max 4e-7 (was 1.4e-3), k_633 max 3e-14; optical rows 719720 -> 815596; 3 new like-for-like comparisons (GaAs
   Ozaki/Skauli, NaI Jellison/Li, TlBr Palik/Schroter) and 2 GaSe o-ray comparisons worse (warning -> suspicious, excellent ->
   warning): the new samples reach closer to the poles, where the fits disagree. Validation self-pair tests now use rmse (CsI
   Li1976/Rodney1955 correlate at r 0.9999998 with rmse 4e-4). Residual: the Kedenburg k tables stitch overlapping segments
   (a jump at ~1.15 um can't be one sample per wavelength).
31. DONE: Datasette browsing (scripts/build_datasette.py -> release/browse-v<rel>/: symlink to the release sqlite, families.db
   with material_index + every family table, metadata.json from the data dictionary with facets and 5 saved queries). Checked in
   Datasette 0.65.5 (all pages/queries 200; a DELETE is refused). Not published: datasette publish cloudrun/vercel/fly is the
   user's call.
32. DONE: descriptors v2 (release_descriptors.py SCHEMA_TAG v2; fetch_mp_structure_extras.py -> mp_structure_extras.json, MP
   2026.04.13, 194/194 entries, 153 with elastic tensors, 0.5 MB, structures kept so tests recompute). Checks: valence = Z - Z(core)
   for Z 1-94; NIST IE/EA; Crippen MR vs Lorentz-Lorenz of measured n and density, 39 liquids r 0.9992, median 0.9%, max 4.7%
   (styrene) -- also a cross-check of the stored n and densities; CrystalNN recomputed from cached structures; Poisson ratio
   consistent with K, G. Oxidation-state guesses are for reading only (GST top guess Ge+4/Sb+1 is wrong; 48 alternatives) and
   are NOT ML features. generate_ml_release_set emits v2 columns only for v2 releases (a v1 release regenerates identically).
   Not added: atomic polarizability (needs the mendeleev package), molecular descriptors of crystals, anything derived from n.
33. DONE: alloys + perovskites families (alloy_material_list.py, perovskite_material_list.py via listed_family.py; loaders
   load_alloys_db.py / load_perovskites_db.py). 63 materials (ids 382-444, registered_in 0.17.0), 86 datasets. Rules (user,
   2026-09-27): each composition its own material, fractional formula from the page (x or exact mol% conversion), never
   guessed; preparation = variant; end members not loaded (already materials); a series joins its first end member's split
   group (existing materials never move; second end members listed in splits metadata). Source conflicts recorded (Gadras-90,
   Jellison-48, Mg:LiTaO3 -o page, Ferrini-0 'GaAs'). PubChem: MAPbI3, CsPbBr3 found; MAPbBr3, CsPbCl3 not found under any
   common name (identity from the formula). Descriptors: material_kind 'solid solution' / 'hybrid organic-inorganic
   perovskite' / 'doped crystal or conducting oxide'; no oxidation-state guess for fractional formulas (pymatgen needs integers).
   DEFERRED (needs a decision): Au-Ag, PEDOT:PSS / P3HT:PCBM blends.
   2026-09-27: 2D HOIPs LOADED (ids 449-457): formula from charge neutrality of the page's own ions (BA+, MA+, 4AMP2+, Pb2+, I-)
   -> RP I3n+1 (the page's I3n-1 leaves +2: typo), DJ I3m+1 (as written). Physics checks (tests): every 2D film has a wider gap
   and lower n(1500 nm) than 3D MAPbI3; DJ edge 2.31 -> 1.84 eV and n(1500) 2.02 -> 2.11 strictly monotone; RP n = 3 edge
   (1.80 eV) below n = 4 (1.86): an absorption tail from 633 nm, consistent with mixed phases in n >= 3 RP films -- no strict RP
   order asserted. n(633) itself is NOT monotone (the edge crosses 633 nm between n = 3 and 4: Kramers-Kronig, not an error).
   2026-09-27 (user: "1"): brass + permalloy LOADED (ids 445-448): % basis unstated, but at% vs wt% differ by < 1 at.% for
   Cu-Zn (<= 0.6) and Ni-Fe (0.8) -- brass converted from wt% (ingots are specified by weight), permalloy Ni0.8Fe0.2 (target
   notation). Au-Ag still deferred: readings differ by up to 14.6 at.% (Au50Ag50), and every Rioux page is the analytic model
   evaluated at a composition; dataset_kind's title regex would NOT flag "An analytic model for the dielectric function" as a
   model fit -- fix that before loading. Paper not reachable (Wiley 403; Mazur-group PDF removed; DTIC down for Querry).

## FOLLOW-UP (logged, NOT started): graphene / 2D carbon as its own family -- materialclass must NOT be 'polymer'
- RI.info main/C, verified read-only: monolayer graphene = Weber 2010 (0.21-1.0 um, exfoliated flake, 3.4 A, on Si/98 nm SiO2), Song 2018 "Graphene"
  (0.193-1.69, CVD mono), Tikuisis 2023 (0.226-4.40, epitaxial on 6H-SiC), El-Sayed 2021 (0.24-1.0, CVD): four, not three. Song 2018 also holds 4 bulk-HOPG pages (graphite).
- Hagemann 1974 (0.0000413-124 um) has NO material description (COMMENTS None): cannot be verified as graphene/graphite/amorphous C from RI.info; treat as NOT graphene.
- Graphene, graphite (Djurisic, Querry pellets, HOPG), few-layer graphene, graphene oxide, rGO, CNTs, ta-C and diamond are DISTINCT materials. Never substitute graphite for monolayer.
- Strongly anisotropic: in-plane (o) and out-of-plane (e) are separate rows. hBN already exists from the nitride batch (BN-hex): check for collision first.
- Open question before any load: can the bulk n,k model represent a monolayer (sheet conductivity, effective-thickness dependence; Weber's n,k is tied to 3.4 A on a substrate)?
  If not, document a schema limitation; do not import.
- Other 2D candidates: MoS2, WS2, MoSe2, WSe2, black phosphorus. Explicit compounds only, no generic "TMD".

34. DONE (2026-09-28): glass catalogs family (glass_catalog_list.py generates the list from catalog-nk.yml; build via
    listed_family with an `extra` hook for datasheet columns; load_glass_catalogs_db.py). 1,675 glasses (17 catalog pages are
    listed twice: loaded once; 6 pages already in the glasses family skipped; popular_glass = aliases of catalog files, used
    as cross-maker equivalents). Checks: formula vs datasheet nd (<= 3.8e-5) and Vd (<= 0.23) for 1,622 glasses; density ==
    datasheet; negative k only HIKARI SK2 / LAK09 (one table point each, allow-listed). Glass code: 6 digits, zero-padded
    (YAML reads 005210 as 5210; nd >= 2 keeps the last three digits); 49 precision-moulding grades (SUMITA (M), OHARA L-...P)
    have a datasheet code of the base glass but post-moulding nd/Vd: glass_code_from_nd kept, splits union both codes.
    Splits: 759 classes; a class with a glasses-family datasheet glass is anchored to it (BK7 class -> glasses:N-BK7).
    COST: 2,132 materials, 1.75 M optical rows, sqlite 315 MB, full build ~10 min (was 2.5), test_release_build much slower.

35. DONE (2026-09-28): v0.20.0 regression found by scripts/analyze_db.py (a 1-point "spectrum"): glass catalogs re-admitted
    SCHOTT DURAN, LITHOSIL-Q, LITHOTEC-CAF2, which data/glass_gaps.csv excluded on review. build_glass_catalogs_csv now reads
    every family's *_gaps.csv excluded_page rows (gap_kind excluded_page in glass_catalog_gaps.csv, reason quoted). Registry:
    the three keep ids 1798-1800 with retired_in 0.20.1 + retired_reason (test: registry = current keys + marked-retired keys).
    Splits: glass classes are now built over the WHOLE catalog from each page's own PROPERTIES (not the repo CSV), so a class
    never depends on which glasses a release holds; reproduces the committed v0.20.0 splits exactly.

