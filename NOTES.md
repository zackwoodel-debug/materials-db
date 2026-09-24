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
6. merge:   `python3 scripts/load_nitrides_db.py --merge-into <db> --report r.json` (idempotent upsert, one transaction, conflicts reported
            never overwritten). Back up <db>, data/ML_feature_matrix.parquet and data/ML_feature_metadata.json first.
7. parquet: `python3 scripts/generate_ml_training_set.py` (reads data/materials_normalized.db ONLY; refits the scaler).

NOT MERGED YET. Rehearsal into materials_normalized.db worked (+6 materials, parquet 23 -> 29, no conflicts) but broke 4 existing
guards (test_chemical_descriptors x2, test_property_inventory, test_validation_layer: pinned 2819 optical rows / a descriptors row per
material). Merge only after deciding whether to update those guards. Also: the tracked parquet is stale vs the tracked DB (BSA smiles,
Al2O3/ZnO/BSA fingerprints); regenerating refreshes those rows and refits 11 scaled feat_ columns for existing rows.
data/materials.db is the legacy schema and cannot take these tables; audit/verify_all read it and do not exercise nitrides.
Generic loader: scripts/load_family_db.py (--family/--catalog/--selections/--db/--fresh/--dry-run/--strict/--report).

## FOLLOW-UPS
1. Guard test vs spec: one guard pins a chemical-descriptors row per material; spec says oxides/nitrides get none. Blocks merge into materials_normalized.db. Decide before Phase 5.
2. Tracked parquet is stale vs the DB independent of nitrides (wrong BSA SMILES; fingerprints for Al2O3/ZnO rows no longer in DB). Regenerate as its own commit.
3. TiN/VN density rows cite a source whose note reads "used for As2S3 and HgS" (pre-existing). Attach a correct source; do not silently rewrite.
4. ri_wl_min_nm / ri_wl_max_nm are empty for all nitrides (batch 2/3b never produced them).
5. Non-stoichiometric SiNx (Kischkat, Beliaev, Vogt x3) not yet modelled; no SiNx material rows exist.
6. Migrations 002-004 pending Aiden. Until 004, polymorph/axis live in dataset_label.
