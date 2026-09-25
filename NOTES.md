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

## FOLLOW-UP (logged, NOT started): graphene / 2D carbon as its own family -- materialclass must NOT be 'polymer'
- RI.info main/C, verified read-only: monolayer graphene = Weber 2010 (0.21-1.0 um, exfoliated flake, 3.4 A, on Si/98 nm SiO2), Song 2018 "Graphene"
  (0.193-1.69, CVD mono), Tikuisis 2023 (0.226-4.40, epitaxial on 6H-SiC), El-Sayed 2021 (0.24-1.0, CVD): four, not three. Song 2018 also holds 4 bulk-HOPG pages (graphite).
- Hagemann 1974 (0.0000413-124 um) has NO material description (COMMENTS None): cannot be verified as graphene/graphite/amorphous C from RI.info; treat as NOT graphene.
- Graphene, graphite (Djurisic, Querry pellets, HOPG), few-layer graphene, graphene oxide, rGO, CNTs, ta-C and diamond are DISTINCT materials. Never substitute graphite for monolayer.
- Strongly anisotropic: in-plane (o) and out-of-plane (e) are separate rows. hBN already exists from the nitride batch (BN-hex): check for collision first.
- Open question before any load: can the bulk n,k model represent a monolayer (sheet conductivity, effective-thickness dependence; Weber's n,k is tied to 3.4 A on a substrate)?
  If not, document a schema limitation; do not import.
- Other 2D candidates: MoS2, WS2, MoSe2, WSe2, black phosphorus. Explicit compounds only, no generic "TMD".

