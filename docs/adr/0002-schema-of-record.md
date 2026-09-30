# ADR 0002: Schema of record, legacy scope, and the path off `data/materials.db`

- Status: **proposed** (plan only). Nothing is dropped, merged, retired or ported by this document.
- Date: 2026-09-30. Facts below were measured on `release/materials-db-v0.20.1` and the tracked `data/materials.db`
  (SHA-1 229b951…), read-only.

## 1. Authoritative schema per workflow

| Workflow | Schema of record | Canonical read path |
|---|---|---|
| Published dataset (release, ML sets, Datasette) | the release SQLite built by `scripts/build_release.py` from `data/materials_oxide_test.db` (base, `updated_sql_schema.sql` shape) plus every family | `materials_db.access.ReleaseDB` (library), `access.http`, `access.mcp_server`; `$MATERIALS_DB_RELEASE` |
| ModalFit export / launcher | the same family-table databases (`materials_oxide_test.db` and the per-family test DBs) | `materials_db.export.modalfit`, `materials_db.launcher` |
| Legacy MatChat stack, stack builder, XRR calculators' default, `verify_all`, `core.audit` | the legacy `data/materials.db` (its own schema: `materials`, `optical_nk`, `references_db`, …) | direct `sqlite3` in each module (no shared layer) |

The release is the canonical database (NOTES.md, 2026-09-25). `data/materials.db` is legacy but still read.

## 2. What still needs `data/materials.db`, and why

Readers (Phase 0 inventory): `api/server.py` (and the SQL agent it builds), `pipeline/stack_exporter.py`,
`calculators/simulate_xrr.py` and `calculators/xrr_engine.py` (default `--db`), `core/audit.py`, `launch.py`, `verify.py`,
`verify_all.py`, `pipeline/fetch_*` (writers; `init_db` is deprecated). They need it because:

- **Data the release does not have** (compatibility gaps, section 3).
- **Legacy identities.** `data/stacks/*.json` reference legacy row ids (e.g. the SiO2 stack: "materials.db id=3").
- **Legacy table names and shapes** (`optical_nk`, `references_db`, the `materials_flat` view) that code queries directly.

## 3. Compatibility gaps: the release does not contain everything the legacy DB has

| Legacy table | Rows | Release equivalent | Gap |
|---|---|---|---|
| `viscoelasticity` | 11 | `rheology`, `mechanical_properties` (both 0 rows) | none populated: the release has no viscoelastic data |
| `dielectric` / `dielectrics` | 21 / 9 | `physical_properties` rows `dielectric_* \| MP_DFPT` (calculated, 90 static + electronic) | legacy rows are literature/measured at stated conditions (e.g. Water 80.1 at 1 kHz, 20 °C vs 78.4 static, 25 °C); they are **distinct evidence**, not duplicates of each other or of MP_DFPT; all 9 `dielectrics` rows have no source |
| `calculated_sld` / `calculated_slds` | 68 / 46 | `physical_properties` SLD rows (periodictable, Cu Kα and thermal neutron) | energies and conventions differ (legacy 1/Å², release 1e-6/Å²); `calculated_slds` has 12 rows for materials absent from `calculated_sld`; all 46 have no source |
| `lab_measurements_needed`, `pubchem_data` | 6, 17 | none | legacy-only bookkeeping |
| `materials` (23 rows) | 23 | `materials` | see the mapping below |

Material mapping, legacy -> release (by exact name / synonym, else by formula):

- Resolve by name or synonym: Chromium, Ethanol, Gold, ITO, PEI, PVA, Polystyrene, Silicon, Silver, Water.
- Resolve only by formula, and ambiguously or approximately: Al2O3 (-> "Aluminium oxide / sapphire"), DMSO (-> "Dimethyl
  sulfoxide"), PDMS (3 Dow Corning variants), PMMA (3 candidates), TiO2 (-> "Titanium dioxide (rutile / anatase)"), ZnO
  (-> "Zinc oxide"). SiO2 is stored as formula `O2Si` in the legacy DB and has no name/synonym match; the release's SiO2
  (material 38) is itself under review (`material38_identity_correction`).
- **Absent from the release:** BSA, DPPC, Nylon66, PEEK, PEG, PTFE (and their legacy data).

So parity tests for the seeded set (Water, Gold, SiO2, Polystyrene, DPPC, PMMA, Ethanol, DMSO, PEG, Silicon, TiO2) are only
possible for part of it: DPPC and PEG cannot be ported at all without adding them to a release family first; PMMA, TiO2, SiO2
and DMSO need an explicit, reviewed mapping (an ambiguous name must raise, never pick a row).

## 4. Migration mappings, preserved evidence, rollback

- **Evidence is preserved, never merged by name.** Rows move only with their conditions (frequency, temperature, regime,
  energy), their source, and a unit conversion that is recorded and tested (SLD 1/Å² -> 1e-6/Å²). Rows without a source are
  carried as unsourced (flagged), not dropped, and not silently attributed.
- **No drops** of `calculated_sld`, `calculated_slds`, `dielectric`, `dielectrics`, or `data/materials.db` without explicit
  approval (Phase 4 rule).
- **Stacks:** legacy ids in `data/stacks/*.json` get an explicit legacy-id -> registry-id map, reviewed per material;
  unmappable references raise.
- **Rollback:** every step is additive; `data/materials.db` stays in git unchanged, and consumers switch through one read path,
  so reverting a port is reverting its commit.

## 5. Constraint promotion (`migrations/001`): not as written

`migrations/001_constraints_indexes.sql` adds CHECK-style triggers; it is not applied by any script or test today. Its note says
"zero existing rows violate any of them", which held for the oxide base DB when written. Against v0.20.1:

| Trigger | Rule | Release rows that would violate |
|---|---|---|
| `trg_materials_formula_nn_*` | `materials.formula` NOT NULL | **1,733 of 2,129** (glasses, mixtures, polymers without a page formula: NULL by design) |
| `trg_optical_check_*` | wavelength > 0, n ≥ 0 | 0 |
| `trg_mechanical_check_*` | frequency > 0 | 0 (table empty) |
| `trg_physical_check_*` | frequency > 0 and wavelength > 0 when set | **90** (static dielectric constants store `frequency_hz = 0`, i.e. static) |

The formula rule contradicts the release's deliberate NULL-formula policy, and the frequency rule contradicts the encoding of
"static". Promote only the optical rule as written; the other two need a decided representation first (e.g. static as
`frequency_hz IS NULL` with a regime label, which changes 90 rows and needs its own parity gate). `k` is correctly
unconstrained (negative k is allow-listed per dataset).

The release gate **already** runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check` (`build_release.py` validation
stage); no change needed there.

## 6. Tests required before any deprecation

1. Schema-drift test: the built release's DDL equals the schema of record (`updated_sql_schema.sql` + documented additions).
2. For each ported consumer: old-path vs new-path output parity for every material that exists in both (section 3 list), with
   an explicit expected-difference list for mapped/ambiguous ones.
3. Every `data/stacks/*.json` loads through the new path with identical numbers, or fails with a named, reviewed reason.
4. A test that every legacy-only row (section 3) is either migrated with its conditions and source, or listed as retained
   legacy-only evidence; none disappears.
5. The SQL agent's read-only boundary (open safety issue from Phase 0: writable setup connection, `startswith("SELECT")`
   allowlist, no row/time caps) is proven before `api/server.py` is pointed at anything new.

## 7. Order of work (proposed)

1. Section 5: promote the optical trigger only; decide the static-frequency and NULL-formula representations.
2. Schema-drift test (6.1).
3. Port `stack_exporter` + stacks with the id map (6.3), then `simulate_xrr` / `xrr_engine` defaults.
4. SQL-agent boundary tests (6.5), then port `api/server.py`.
5. Decide legacy-only evidence (viscoelasticity, dielectrics, unsourced SLDs): migrate with conditions, or keep `data/materials.db`
   as a documented read-only legacy archive. Only then consider retiring anything, with approval.
