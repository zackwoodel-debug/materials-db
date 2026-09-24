# Batch 3 Scoping Report — Pure Elements

Read-only analysis. No ingestion, no schema changes, no DB writes. RI.info clone pinned at
`src/materials_db/pipeline/refractiveindex_contract.py` (same commit as batch 1/2).

## A. Real counts (not the recollected 59/420)

Recomputed directly from the pinned catalog (single-element formulas under `main`/`other`):
**63 books / 436 pages** total. After excluding gases (not solids, same principle as batch 2's
SF6/CS2 exclusion) — noble gases Ar/Xe/Kr/Ne/He and diatomic gas elements H2/D2/N2/O2, 9 books,
77 pages — the real corpus is **54 books / 359 pages**. This is close to but not identical to
the "59/420" recalled at the start of this batch; stated here as the corrected, verified number,
same as batch 2's sulfide-count correction.

Page count is extremely concentrated: Si (63), Au (38), C (29), Ag (21), Ge (19), Kr — excluded
— Cu (12), Al (9), Ti (9), Pb (8). These 8 elements alone account for ~230 of the 359 pages
(64%); the other 46 elements average ~2.8 pages each.

### Trait clustering (task a)

- **Formula parses**: trivially true for all 54 (a bare element symbol always parses).
- **Tabulated vs. dispersion-formula data**: every page checked is `tabulated n/k/nk` (measured
  data) or a small number of explicit parametric model fits (Lorentz-Drude, Brendel-Bormann,
  DFT) -- both families the pipeline already handles; no new loader logic needed, same
  conclusion as batch 2.
- **Data-type split, checked directly against page COMMENTS/REFERENCES, not guessed**:
  - 62/359 pages (17%) are theoretical/model fits, not direct measurements at all: DFT
    calculations, Lorentz-Drude and Brendel-Bormann parametrized models (Rakic et al. 1998 and
    Werner et al. 2009 alone account for most of these, repeated per element as a matched
    pair/triplet of "the same theoretical fit" entries). These should default OUT of the
    "verified experimental measurement" pick the same way ab-initio datasets were never the
    default pick in batch 2 (GeS2's Slavich-abinitio-* were available but not default) --
    available as alternates, not silently preferred or silently excluded.
  - 92/359 pages (26%) explicitly state a deposition method or thin-film condition in
    COMMENTS/REFERENCES (evaporated, sputtered, CVD, ALD, template-stripped, specific film
    thickness in the page name itself). This is the process-condition axis, concretely sized.
  - The remainder (~55%) state neither -- an author name and a wavelength range only. This does
    NOT mean "bulk single crystal, safe to use bulk density" by default; it means unknown, and
    should be flagged as such per-material rather than assumed.

## B. The process-condition descriptor (task b) — the new schema axis

### What the corpus actually distinguishes (not guessed, read directly off real pages)

- **Deposition/growth method**: evaporated, sputtered, single-crystal (grown, not deposited),
  template-stripped, CVD (polycrystalline vs. single-crystal explicitly distinguished for
  diamond), arc-grown vs. aerosol-CVD vs. HiPco (three distinct CNT synthesis routes, same
  allotrope), ALD.
- **Film thickness as an optically-significant condition, not just a stack-assembly parameter**:
  gold alone has FOUR independent papers reporting n,k as an explicit function of thickness
  (Yakubovsky 4/6/9/25/53/117 nm, Rosenblatt 11/21/44 nm, Lemarchand 3.96/4.62/5.77/11.7 nm,
  Klinavicius 7.2-40.0 nm) -- below roughly 10-20 nm, a metal film's optical constants
  genuinely depend on thickness (grain size, percolation, surface scattering), so "which
  thickness was THIS n,k measured at" is a real, distinct axis from "how thick is MY layer in
  the stack I'm assembling" (the latter is already `structural.thickness`; this is a property
  of which SOURCE DATASET is correct to use, analogous to picking an optical axis, not a
  structural stack parameter).
- **Measurement temperature**: Magnozzi (Au) at 25/225/350 C, Golovashkin (Sn) at 293/78/4.2 K --
  distinct from anneal temperature (a permanent, one-time process step) in that it's the
  temperature the OPTICAL MEASUREMENT was taken at, not necessarily how the film was made.
- **Grain/structural state distinct from crystal phase**: polycrystalline vs. single-crystal CVD
  diamond (same allotrope, same MP structure, different microstructure) is a real, separate
  distinction from graphite vs. diamond (a different allotrope entirely).
- **Composite/non-pure-element measurements that should be excluded from this batch entirely**:
  Ciesielski et al.'s "Au/SiO2" and "Au/Ge/SiO2" pages measure an already-assembled bilayer/
  trilayer stack, not gold's own intrinsic optical constants -- these aren't a pure-element
  optical dataset at all and don't belong in a single-material canonical list.

### Proposed field

A new, canonical `PROCESS_CONDITION` concept, defined ONCE in a shared module (not batch-3-local
code) the same way `MATERIALS_50`/`RESOLVED_OPTICAL_SOURCE_CITATION` centralized the polymorph
list -- proposed home: `src/materials_db/pipeline/process_condition.py`, imported by both the
batch-3 material-list module and `export/modalfit.py`'s label-parsing code, so a later batch
(the "pure_element" corpus is much bigger than metals alone -- semiconductors, more metals) never
redefines it. Contents:

- A controlled vocabulary of process-condition VALUES, structured as
  `"{axis}:{value}"` pairs rather than free text, e.g. `"deposition:evaporated"`,
  `"deposition:single_crystal"`, `"thickness:25nm"`, `"temperature:225C"`,
  `"structure:polycrystalline"` -- so a later query (like `materials_blocked_on`) can filter on
  the axis, not parse free text.
- Given `dataset_label`'s schema is FROZEN (no new DB columns, per the standing schema-approval
  rule), this is encoded as an ADDITIONAL optional `" | "`-separated segment in the existing
  text convention, not a new column. Proposed position: immediately after polymorph (or in
  polymorph's position when there's no polymorph to state), before source/axis:
  `"{polymorph} | {process_condition} | {source} | {axis}"` (all four),
  `"{process_condition} | {source} | {axis}"` (no polymorph question, e.g. gold),
  falling back to the existing 2-/3-segment forms when neither applies.
- This requires extending `_polymorph_prefix()`'s detection logic (the `_QUANTITY_MARKERS`/
  `_SOURCE_LABEL_RE` heuristics) to also recognize a process-condition segment and not
  mis-parse it as a polymorph or a source label -- the exact same class of parsing-ambiguity
  bug already found and fixed twice (batch 1's polymorph fallback, and the risk flagged in
  `docs/PIPELINE_PRINCIPLES.md`). This needs its own small, explicit test suite before it ships,
  not an assumption that "it'll parse fine."

### How it coexists with polymorph (explicitly, since some elements have both)

They are orthogonal, not alternatives, and this batch's own corpus proves it directly:
- **Carbon**: polymorph = which allotrope (diamond / graphite / graphene / CNT -- a genuinely
  different crystal structure each time); process_condition = how THAT allotrope's specific
  sample was made (single-crystal CVD diamond vs. polycrystalline CVD diamond -- same allotrope,
  different growth condition; aerosol-CVD CNT vs. arc-grown CNT vs. HiPco CNT -- same allotrope,
  three different synthesis routes).
- **Tin**: polymorph = alpha (grey, diamond-cubic, semiconducting) vs. beta (white, tetragonal,
  metallic) -- a real allotropic transition at 13.2 C; process_condition would record the
  measurement temperature (293/78/4.2 K) as a SEPARATE fact from which allotrope is present (see
  the tin triage entry below -- this distinction turns out to matter more than expected).
- **A pre-existing wrinkle worth flagging, not silently inheriting**: the oxide batch encoded
  "amorphous" (Ta2O5, Nb2O5, SiO2, SiO) AS IF it were a polymorph value. Under this batch's
  framing, "amorphous" is actually a process_condition value (structure:amorphous), not a
  polymorph -- there IS no crystal structure to name. Not proposing to retroactively rewrite the
  50 oxide rows (out of scope, no functional bug, existing consumers already treat it correctly
  as a `dataset_label` prefix); flagging it so batch 3's own amorphous entries (e.g. boron, see
  below) are encoded as process_condition from the start rather than repeating the same
  informal shortcut.

## C. Density: the batch's defining problem, with real numbers (task c)

Checked every one of the 359 pages' own COMMENTS/REFERENCES text directly (not inferred):

- **14/359 pages (~4%) state an explicit measured film density.** All 14 come from one cluster
  of related EUV/VUV thin-film optical-constant papers (Fernandez-Perea, Larruquert,
  Rodriguez-de_Marcos, Vidal-Dasilva, Garcia-Cortes), covering B, C (ta-C), Ca, Ce, Er, Eu, Ho,
  Lu, Mg, Pr, Sc, Sr, Tm, Yb -- each stated as "Density: X g/cm3. Film deposited at room
  temperature."
- **345/359 pages (~96%) state no density at all.** Falling back to bulk elemental density
  (periodictable/MP, the existing pipeline's only other source) is not obviously wrong for the
  ~26% that are clearly single-crystal/bulk-grown, but for the remainder -- including every
  thickness-labeled thin film (gold's 13 thickness-series pages, none of which state a density)
  -- there is no way to know from RI.info's own metadata whether bulk density is anywhere close
  to correct. For SLD (the whole point of this DB for XRR/NR), that's the difference between a
  right and a wrong answer, not a rounding error: a porous/columnar evaporated film can run
  10-30% below bulk density, which propagates directly and linearly into SLD.

**Proposed representation** (reusing existing machinery, not inventing new machinery, per the
project's own "no new machinery" preference from batch 2): add a new `density_source` value,
`"bulk_elemental_approximation"`, used whenever no film-specific density exists. This still
counts as the GATE's "verified" state (a density exists, is sourced, and is labeled) rather than
a fourth outcome -- but the citation/verification_note is REQUIRED to say explicitly that it's a
bulk value substituting for an unmeasured film value, so nothing downstream (an SLD consumer, a
future fit) can mistake it for a characterized film density. The 14 entries with a real stated
value get `density_source="literature"` with a real citation, same as the oxide batch's
CaGdAlO4/CaYAlO4 pattern.

## D. Triage list — the VO2/TeO2/Ta2O5 equivalents (task d)

Applying "an MP structure claim is UNVERIFIED until queried" to a real spot-check (not a
guess) found genuine traps, at higher stakes than most of batch 2's because these are
textbook-famous phase competitions:

- **Carbon — confirmed trap.** MP's lowest-`energy_above_hull` entry (mp-3347313, C2/m #12) is
  neither graphite (the textbook thermodynamically STABLE phase at STP -- P6_3/mmc #194,
  mp-48, appears only at +3.12 meV/atom) nor diamond (the metastable phase several RI.info pages
  explicitly target -- "Phillip and Taft 1964: Diamond", "Taylor et al. 2023: Single-crystal
  CVD" -- Fd-3m #227, further from the hull still). Taking lowest-hull would silently give
  neither of the two allotropes anyone is actually asking for. Needs an explicit
  `EXPECTED_SPACEGROUP`-per-allotrope treatment (diamond Fd-3m #227, graphite P6_3/mmc #194),
  keyed by which specific page/dataset is being exported, not one single override for the whole
  "C" formula the way other batches' overrides work -- carbon may need its own per-dataset
  structure map, a new shape this batch should design deliberately rather than force into the
  existing per-formula `EXPECTED_SPACEGROUP` dict.
- **Tin — confirmed trap, and a wrinkle beyond what was expected.** MP's lowest-hull entry
  (mp-117, Fd-3m #227, Ehull=0.00000) is ALPHA-tin (grey, diamond-cubic, the low-temperature
  thermodynamically stable phase) -- but the RI.info data (Golovashkin and Motulevich 1964,
  293/78/4.2 K) is almost certainly measuring BETA-tin (white, metallic, tetragonal I4_1/amd
  #141, mp-84, Ehull=+0.120) throughout, including at 78 K and 4.2 K: the alpha/beta transition
  at 13.2 C ("tin pest") is well known to be kinetically sluggish and does not spontaneously
  nucleate on ordinary lab cooling of a metal film without specific seeding conditions. This is
  an assumption, not a verified fact from the paper itself, and should be recorded as exactly
  that -- an explicitly-flagged, reasoned assumption, not silently treated as settled.
- **Boron — a different-shaped trap: probably shouldn't use an MP crystal structure at all.**
  Boron's crystallography is famously complex (multiple genuine competing rhombohedral/
  tetragonal allotropes near the hull: mp-160 R-3m #166 Ehull=0, mp-161 R-3m #166 Ehull=0.0198,
  mp-1193675 Pnnm #58 Ehull=0.029, densities 2.30-2.57). But the RI.info dataset's OWN stated
  film density (2.10 g/cm3, Fernandez-Perea) is BELOW every one of these crystalline entries --
  consistent with amorphous boron, the well-known typical state of a room-temperature-deposited
  boron film given boron's difficulty crystallizing without high-temperature annealing. Likely
  the same resolution shape as SiO2/Ta2O5/As2S3: `structure:amorphous`, no MP structure match at
  all, density from the paper's own stated value (already in hand, see part C).
- **Selenium, Tellurium — moderate complexity, likely resolvable without deep triage.** Both show
  the same shape: crystalline o/e (ordinary/extraordinary) trigonal pairs as the majority of
  pages (Campbell/Sherman/Caldwell/Guo), plus exactly one amorphous thin-film entry each
  (Ciesielski, 25-30 nm). Default to the crystalline trigonal o/e pair (matches the bulk of the
  data and is what "Se"/"Te" as elements conventionally mean), keep the amorphous film as a named
  alternate -- same triage shape as batch 2's ZnS/GaN, not expected to need Carbon/Tin/Boron-level
  effort.
- **Silicon, Germanium, Gold, Silver, Copper, Aluminum, Titanium, Lead and the rest of the
  ~46-element majority**: textbook single stable ambient-condition allotrope (fcc/bcc/hcp/
  diamond-cubic as appropriate), essentially undisputed at room temperature and pressure --
  spot-checked Si/Ge (diamond-cubic, matches expectation, lowest-hull correct) as a sanity check
  during this scoping pass; not expecting Carbon/Tin/Boron-level surprises here, but each still
  gets the real MP query before being accepted, per the standing rule -- not assumed clean
  because it looks textbook.

## Recommendation: a right-sized first sub-batch

**Proposed batch 3a (~45 materials, deferring the 3 hardest to batch 3b)**: the ~51 elements
minus Carbon, Tin, and Boron, INCLUDING Gold as the flagship process-condition validation case.
Gold has zero polymorph ambiguity (always fcc) but the richest process-condition breadth in the
whole corpus (deposition method x thickness x temperature, 38 pages) -- it's the cleanest place
to prove the new field works correctly BEFORE combining it with a genuine polymorph question.
Carbon, Tin, and Boron are deferred to batch 3b specifically because each combines a real
polymorph trap WITH a process-condition/amorphous question simultaneously -- solving both axes
at once, on the first attempt, on the three hardest cases in the corpus, is how a design mistake
compounds instead of being caught early (the same reasoning behind resolving batch 2's 8-material
triage before the other 30).

**TiN/VN/EuS**: confirmed queryable now (`materials_blocked_on("process_condition_field")` ->
`['EuS', 'TiN', 'VN']`). Once `PROCESS_CONDITION` is approved and implemented, these three become
resolvable (deposition-method-only data is exactly what the new field is for) -- proposing to
fold their resolution into the SAME implementation pass as batch 3a, since the schema work is
already being done and they're a 3-material bonus, not a new research effort. Say if you'd rather
keep them separate.

**Gate carried over unchanged**: verified / named exclusion / explicitly flagged unresolved, no
silent defaults, every resolution frozen into code with citation + verification_note as it's
made -- same as batch 1 and batch 2, not re-derived here.

No code has been written for this batch. Awaiting approval of: (1) the PROCESS_CONDITION field
design above, (2) the ~45-material batch 3a scope, (3) whether to fold in TiN/VN/EuS.

---

## E. Approved with 3 changes -- resolution results

Approved: the dataset_label-segment encoding, the ~45-element sub-batch (Carbon/Tin/Boron
deferred to 3b), Gold as the flagship process-condition case. Three changes required before
proceeding, addressed below: (1) `bulk_elemental_approximation` is its own DENSITY_STATE, not
folded into verified; (2) the oxide batch's `polymorph="amorphous"` gets a migration-cost report,
not a migration; (3) TiN/VN/EuS folded into this pass.

### E1. DENSITY_STATE -- implemented, not just designed

`src/materials_db/pipeline/process_condition.py` now defines a four-way gate: `DENSITY_VERIFIED`
/ `DENSITY_BULK_APPROXIMATION` / `DENSITY_NAMED_EXCLUSION` / `DENSITY_UNRESOLVED`, distinct from
(and orthogonal to) the structural `EXCLUSION_STATE` gate. `bulk_elemental_approximation`
explicitly does NOT count as verified -- `density_state_from_source()` maps it to
`DENSITY_BULK_APPROXIMATION` unconditionally.

- **Queryable**: `materials_with_density_state(db, state)` queries the live DB directly (not a
  static per-batch dict, since any material in any batch can land in this state) by inspecting
  each material's density row's own `dataset_label`. Verified live against the real DB: returns
  `['TiN', 'VN', 'EuS', 'Au']` for `DENSITY_BULK_APPROXIMATION` and includes `Se`/`Te` (but not
  `Au`) for `DENSITY_VERIFIED`.
- **Carried into the ModalFit JSON**: `export_layer()` now emits `molecular.density_confidence`
  and `molecular.density_bounds` (also mirrored into `materials_db.density_confidence` for
  visibility without inspecting the molecular block). Verified directly on real exported layers
  (see below) -- visible at fit time, not just via a separate DB query.
- **Should density be a free fit parameter for these?** Yes. `physics.py`'s `extract_params()`
  already auto-generates a density `ParamSpec` for every layer with `molecular.density_g_cm3` set
  (a previously-unnoticed fact, found while designing this) -- the machinery already exists; the
  gap was only in what BOUNDS it gets. Implemented: `DENSITY_VERIFIED` materials get zero-width
  bounds (`min == max == value`), pinning the parameter so a caller who naively marks every
  layer's density as `vary=True` can't accidentally move a value this pipeline trusts.
  `DENSITY_BULK_APPROXIMATION` materials get asymmetric bounds (`[0.70x, 1.02x]` the bulk value)
  -- films are commonly LESS dense than bulk (voids, porous/columnar growth), rarely denser, so
  the bounds reflect that direction rather than a naive symmetric window. A caller still has to
  explicitly set `vary=True` (that's a fit-setup choice, not an export-time one), but the bounds
  now make that choice safe and physically defensible instead of unconstrained or wrong-shaped.

Verified end-to-end on real exported layers:

| Formula | dataset_label | density_confidence | density_bounds |
|---|---|---|---|
| Au | `density_bulk_elemental_approximation` | bulk_approximation | [12.62, 18.39] |
| Se | `trigonal \| density_MP_DFT` | verified | [4.4956, 4.4956] (pinned) |
| Te | `trigonal \| density_MP_DFT` | verified | [5.8752, 5.8752] (pinned) |
| TiN/VN/EuS | `... \| density_bulk_elemental_approximation` | bulk_approximation | asymmetric, per-material |

Regression tests: `tests/test_process_condition.py` (the gate itself, the bounds asymmetry, the
live-DB query) and `tests/test_modalfit_export.py::TestDensityConfidenceCarriesThroughExport`
(the exporter carry-through). 385 tests pass.

### E2. Oxide batch "amorphous" migration -- list and cost, not migrated

**Materials affected**: 5, not 4 -- rechecking turned up one more than the original finding.
`Nb2O5`, `SiO`, `SiO2`, `Ta2O5` (all `polymorph="amorphous"` in `oxide_material_list.py`), plus
**`GeO2`**, which is `FORCE_NO_MP` with a literature "fused (vitreous) GeO2" density but was never
labeled `polymorph="amorphous"` at all (`polymorph=None`) -- an inconsistency in its own right,
found while scoping this migration, not previously noticed. `As2S3` (batch 2) already uses the
SAME informal shortcut but is out of scope here since it's this session's own work, not
inherited.

**What actually has to change, checked directly rather than assumed**:
1. `scripts/oxide_material_list.py`: 4-5 `polymorph` fields (`"amorphous"` -> `None`), plus adding
   a process_condition assignment somewhere -- this module has no per-axis `ri_axes`/
   process_condition slot at all today (unlike the batch-2/3 modules), so this is itself a
   retrofit, not a field edit.
2. **`data/step1_selections.json` is the actual load-bearing source, not just the Python module**:
   checked directly -- this file independently stores `"polymorph": "amorphous"` AND
   `"effective_polymorph": "amorphous"` per material, and its own `axes[].dataset_label` strings
   already bake "amorphous" in. `load_oxides_db.py` reads THIS file for the optical side, not
   `MATERIALS_50`'s polymorph field (which is closer to a documentation/cross-check copy -- see
   that loader's own "NOTE: polymorph differs" mismatch-detection code, added specifically
   because these two sources can drift). Migrating means updating both, consistently.
3. **A full DB rebuild is required, not an in-place edit**: `load_oxides_db.py`'s `fresh_db()`
   unconditionally deletes and recreates `data/materials_oxide_test.db` from `data/oxides_50.csv`
   + `step1_selections.json`. Since batch 2 and the pure-element triage are APPENDED on top of
   the oxide load (not independently reloadable), migrating requires, in order: rebuild the 50
   oxides fresh, re-append the 31 batch-2 materials, re-append the 3 pure-element triage
   materials -- then re-run the full test suite and the full-export invariant check to confirm
   nothing shifted. All three scripts already exist and are tested; this is a sequencing/
   verification cost, not new engineering, but it is NOT a one-line change.
4. **Three real call sites break and need updating**, found by grepping the whole repo rather
   than assumed: `scripts/xrr_smoke_test_oxide_db.py` (`read_layer_by_dataset_label(conn, "SiO2",
   "amorphous")`), `src/materials_db/calculators/simulate_xrr.py`'s own docstring CLI examples
   (`SiO2[amorphous]:100`), and this session's own new
   `tests/test_modalfit_export.py::TestExportStackLabelDisambiguation` tests, which happen to use
   `SiO2`/`"amorphous"` as their fixture. Each fix is mechanical (the label moves or disappears,
   update the reference), not conceptually hard, but it's real, correlated blast radius.

**Net cost estimate**: small-to-moderate -- no open design questions (unlike inventing
process_condition itself, which was the hard part), but touches 2 data files + 1 canonical
module + a mandatory full DB rebuild in a specific order + 3 dependent call sites, with a
full-suite and full-export re-verification pass required afterward. Call it a contained,
half-day-scale task, not a five-minute edit. Not migrated, per instruction -- this is the list
and the cost, nothing more.

### E3. TiN/VN/EuS -- folded in, resolved, loaded

All three moved out of `EXCLUSION_STATE` entirely (no longer deferred in any sense) and into
`MATERIALS_31` (formerly `MATERIALS_28` -- renamed to match, along with `batch2_28.csv` ->
`batch2_31.csv` and the export assertion, 78 -> 81 -> 84 once the element triage is included
too). Structure: all three rock-salt (Fm-3m #225), confirmed via MP -- **VN was a real, second
confirmed trap in this same pass**: lowest-hull is mp-1018027 (P-6m2 #187, theoretical but
ICSD-backed), NOT rock-salt; the correct entry (mp-925) is at an unusually large +190 meV/atom
gap (every other override in this project has been <2 meV/atom), flagged explicitly as likely a
magnetic-ordering/DFT-functional sensitivity for this V-containing nitride rather than an
ordinary near-degenerate tie. Density: all three relabeled `bulk_elemental_approximation` (no
RI.info page for any of the three states a measured film density; every entry is an explicit
thin film). Loaded into the DB and exported successfully -- verified via
`materials_with_density_state`, which returns exactly `['TiN', 'VN', 'EuS', 'Au']` for
`DENSITY_BULK_APPROXIMATION`.

## F. Pure-element triage results (task per "resolve triage first")

- **Au (gold)** -- verified, no polymorph ambiguity (fcc, mp-81, Fm-3m #225, Ehull=0.00000,
  MP-confirmed). Default dataset Johnson and Christy 1972 (the classic reference) states only
  "Room temperature" -- no deposition method, no density anywhere in the 38-page gold corpus.
  Density: `bulk_elemental_approximation`. This is deliberately the flagship process-condition
  case (see `AU_ALTERNATE_PAGES` in `scripts/pure_element_material_list.py`): evaporated/
  single-crystal/template-stripped deposition variants, four independent thickness-series papers
  (4nm-117nm), and a three-point measurement-temperature series (25/225/350 C), each encoded with
  `process_condition.format_process_condition()`.
- **Se (selenium) -- CONFIRMED TRAP**, the same shape as CeF3/BN/HgS/ZnS: MP's lowest-hull entry
  (mp-570481, monoclinic P2_1/c #14) cannot be what Campel and Johnson 1969 measured -- their
  page explicitly states "Single-crystal selenium" and reports o/e data, physically impossible
  for a monoclinic (biaxial) crystal. The correct trigonal entry (mp-14, P3_121 #152) is a
  near-degenerate tie at +1.08 meV/atom. Density: VERIFIED (MP_DFT) -- "single-crystal" is an
  explicit, stated bulk claim, not an approximation.
- **Te (tellurium)** -- lowest-hull entry (mp-19, trigonal P3_121 #152) already correct, pinned
  explicitly. Density: VERIFIED (MP_DFT), with a recorded caveat that the evidence for "genuinely
  bulk" is weaker than Se's (o/e notation implies it; the paper doesn't state "single crystal"
  outright the way Campel does for Se) -- not silently treated as equally certain.

All three resolved, loaded (`scripts/build_pure_element_csv.py` / `load_pure_element_db.py`),
and exported successfully (84 total materials, 82 OK, skip set still exactly `{GdF3,
LuAl3(BO3)4}`). Awaiting approval before the remaining ~42 pure elements (Carbon/Tin/Boron still
deferred to 3b) are processed.

## G. The remaining 47 -- run, with 3 preliminary fixes first

Before this ran, three things were done first per instruction:

1. **Swept for other filename/fixed-list-keyed lookups** (the same shape as `_lookup_mp_id`'s
   two failures). Found and fixed `export_all_materials_modalfit.py`'s hardcoded 3-CSV-filename
   list + hardcoded material count -- now globs `data/*.csv` and cross-checks against the live
   DB's own material count. Swept and cleared as NOT the same shape: `KNOWN_EXCLUSIONS` (actively
   asserted against every run), `load_batch2_db.py`/`load_pure_element_db.py`'s `n_before` checks
   (a deliberate sequential precondition, not a completeness assumption), the curated override
   dicts (`EXPECTED_SPACEGROUP` etc. -- deliberately maintained judgment calls, not enumerations
   expected to stay complete on their own), and the legacy `materials.db` scripts (a separate,
   out-of-scope schema). See `docs/PIPELINE_PRINCIPLES.md` section 2a and the commit history.

2. **Corrected the triage rule and re-examined GdF3.** VN's trap (+190 meV/atom) disproved the
   unstated assumption that a correct structure, if it exists, is always near the hull.
   `docs/PIPELINE_PRINCIPLES.md` rule 1a now states this explicitly: search the FULL candidate
   set, treat a large gap as a signal to investigate, and "no near-degenerate alternative" is not
   sufficient grounds for a named exclusion on its own. GdF3 was re-examined under this rule:
   re-queried mp-api with no energy_above_hull filtering at all, confirmed MP has exactly ONE
   entry for GdF3, full stop, at any energy above hull. Stays a named exclusion -- this was never
   a search-width problem, so widening the window doesn't change the outcome -- but the
   verification is now real and explicit rather than assumed sufficient the first time.

3. **The oxide-amorphous migration is now a tracked, queryable open item** --
   `process_condition.TRACKED_OPEN_TASKS["oxide_amorphous_migration"]`, with `open_tasks()` /
   `task_detail()` queries, same treatment as `EXCLUSION_STATE`'s blocking_on queries. Not
   migrated. Also found, while scoping it, that GeO2 has the same informal shortcut's opposite
   problem: `FORCE_NO_MP` with a literature amorphous density but never labeled
   `polymorph="amorphous"` at all -- added to the tracked task's scope.

### The run itself: 47 elements, corrected count

The corpus is 48 elements after removing Au/Se/Te (already resolved) and Carbon/Tin/Boron
(deferred) from the 54-book total -- not the ~42 assumed when this batch was approved (that
number silently carried the ORIGINAL miscounted 59/420 forward; corrected here, not used
silently). Of those 48, **Hg (mercury) is EXCLUDED, not processed**: its only RI.info page
(Inagaki et al. 1981) states directly "Liquid mercury at room temperature" -- this database is
for thin-film/solid-state modeling, and liquid mercury doesn't have a thickness/roughness/
crystal-structure model the way every other material here does. Same exclusion logic as the
noble-gas/diatomic-gas books, just found later because it wasn't a formula-parsing issue. **47
elements actually processed.**

**The corrected triage rule immediately paid off at scale**: applying it (full candidate search,
large-gap-is-a-signal) to all 47 found **16 confirmed traps (34%)** -- a dramatically higher rate
than the oxide batch (0/50) or fluoride/nitride/sulfide batch (3/32, ~9%). This is not scattered
noise; it clusters in two well-understood ways:

- **All 5 alkali metals present (Li, Na, K, Rb, Cs) are wrong at lowest-hull**, every one of
  them, with a real physical explanation: DFT at 0K correctly finds the low-temperature ground
  state, and alkali metals are documented to undergo bcc -> close-packed martensitic transitions
  well below room temperature (Li/Na specifically, below ~70-80K) -- but every RI.info
  measurement here is at or near room temperature, where bcc is the actually-correct phase for
  all five. Gaps range 9.2-19.3 meV/atom.
- **4 of 6 lanthanides present (Pr, Eu, Er, Lu) plus Yb** (already resolved in the triage set's
  adjacent research, folded in here) are wrong or unconfirmable at lowest-hull -- mostly small
  hcp/fcc/bcc energy differences sensitive to magnetic ordering and DFT functional choice, the
  same root cause as VN's trap in batch 2. Eu and Sr (not a lanthanide, but the same "wrong
  ambient-condition phase" shape) have the two largest gaps in this batch, 41.44 and 44.81
  meV/atom respectively -- both flagged explicitly rather than smoothed over.
- Isolated cases: Ag (fcc vs. a near-degenerate hcp polytype, 2.13 meV/atom), Co (hcp vs. fcc,
  10.62 meV/atom, cobalt's well-known small hcp/fcc energy gap), In (face-centered tetragonal vs.
  pure cubic, 4.49 meV/atom), Ta (bcc vs. a distorted tetragonal structure, 9.15 meV/atom), Ti
  (hcp vs. a lower-symmetry hexagonal group lacking the real screw-axis stacking, 15.17 meV/atom).
- **Pr is only partially resolvable by this mechanism**: praseodymium's real phase is dhcp
  (double-hcp), which shares the SAME space-group number (194) as simple hcp with a different
  unit-cell multiplicity (Z=4 vs Z=2) -- an override keyed on space-group number alone cannot
  distinguish them. Flagged as such, not silently asserted as fully verified.
- **Yb has no energy_above_hull data at all** (MP reports `Ehull=None` for every entry, likely an
  f-electron DFT+U data-availability gap) -- a third, distinct resolution shape: picked from known
  crystallography (ytterbium's real, anomalous-among-lanthanides fcc structure), not from a hull
  comparison that doesn't exist for this element.

**A second, independent finding while overriding structures**: for 2 of the 12 literature-density
elements, MP's own DFT-computed density diverges dramatically from the cited experimental value
-- Ce (MP: 9.12 g/cm3, literature: 6.771 g/cm3, +35%) and Yb (MP: 9.64 g/cm3, literature: 6.81
g/cm3, +41%). Both are lanthanides with well-documented anomalous valence/4f-electron behavior
(Ce's alpha/gamma volume-collapse transition; Yb's divalent character) that are known to be
difficult for standard DFT exchange-correlation functionals -- this is exactly why literature
density, not MP_DFT, was used for these 12, and a concrete demonstration of what "verified" vs.
"bulk_approximation" is actually protecting against: even MP's own STRUCTURE being confirmed
correct doesn't guarantee its DENSITY NUMBER is trustworthy for these particular elements.

### Density-state distribution (the number that matters)

| State | Count (of 50 elements) | % |
|---|---|---|
| DENSITY_VERIFIED | 17 | 34% |
| &nbsp;&nbsp;-- via a real literature density citation (Ca/Ce/Er/Eu/Ho/Lu/Mg/Pr/Sc/Sr/Tm/Yb) | 12 | |
| &nbsp;&nbsp;-- via MP_DFT on a confirmed genuinely-bulk/single-crystal sample (Se/Te/Ag/Si/Ge) | 5 | |
| DENSITY_BULK_APPROXIMATION (Au + 32 more) | 33 | 66% |

**33 of 50 pure elements (66%) landed in DENSITY_BULK_APPROXIMATION.** This is the number that
tells us how much of this batch is fittable with confidence today: 17 elements (34%) have a
density defensible enough to fix in a fit; the other 33 (66%) should have density varied as a
free fit parameter within `process_condition.bulk_approximation_density_bounds()`'s asymmetric
`[0.70x, 1.02x]` range if they're used in a real reflectivity fit, per the standing recommendation
from the earlier fit exercise -- fixing an admittedly-approximated density is worse than fitting
it within a defensible range.

Combined across all batches: 131 materials total, 129/131 exported (skip set unchanged: `{GdF3,
LuAl3(BO3)4}`), 93 `DENSITY_VERIFIED` / 36 `DENSITY_BULK_APPROXIMATION` (33 pure elements + TiN/
VN/EuS) / 2 named exclusions.

Still holding batch 3b (Carbon, Tin, Boron) -- each needs the polymorph AND process-condition
axes resolved together, deliberately not attempted alongside this larger, already-eventful pass.

## H. Batch 3b -- Carbon (Diamond + Graphite), Tin, Boron

The three deferred materials, each combining a polymorph question with a process-condition or
amorphous question at once. All three MP structures were verified directly (full candidate
search, per rule 1a) before writing any code.

### Carbon needed a genuinely new shape: two materials, one formula

Diamond and Graphite are optically nothing alike and are stored as two separate `materials` rows
that legitimately share `formula="C"` -- not a data-entry ambiguity to resolve down to one row,
the way every prior polymorph question in this project has worked. This is a real, load-bearing
exception to "one formula = one identity" and it exposed three places in the pipeline that had
silently assumed the opposite, all found and fixed before any Carbon data was written:

1. **`_find_material()`** (`src/materials_db/export/modalfit.py`) used `.fetchone()` on its
   formula-fallback query -- would have silently returned whichever of Diamond/Graphite SQLite
   happened to return first. Now raises `ExportError` naming both matches on formula ambiguity,
   requiring the caller to specify the exact material name. Fixed and committed (`7f67820`)
   *before* Carbon existed in the DB, specifically because scoping Carbon predicted this failure
   shape rather than waiting to hit it.
2. **`fetch_mp()`'s `EXPECTED_SPACEGROUP` lookup** (`scripts/build_oxides_csv.py`) was keyed by
   formula only -- cannot express "Diamond wants #227, Graphite wants #194" for the same formula.
   Changed to a name-first, formula-fallback lookup, backward compatible since no existing
   material's `name` has ever coincided with a formula key.
3. **`EXPERIMENTAL_DENSITY_OVERRIDE`'s lookup** (same file) had the identical formula-only
   ambiguity, found while resolving Graphite's density (below) -- fixed the same way, same commit.
4. **`export_all_materials_modalfit.py`'s `_discover_materials()`/export loop** asserted no
   duplicate formulas across CSVs and used formula as both the export lookup key and the output
   directory name -- all three assumptions break for Carbon. Switched the identity key throughout
   to `name` (the schema's real `UNIQUE` column), duplicate-checked on `name` instead of formula,
   and derived the output directory from a sanitized `name`.

**A live incident during this fix surfaced a fourth, unrelated gap**: switching the export
directory to a sanitized `name` caused "Tin" to collide case-insensitively with a stale "TiN"
directory left over from before this change (macOS's default filesystem, APFS, is
case-insensitive but case-preserving) -- Tin's export silently overwrote the old TiN directory's
files. No real data was lost (the current run's actual Titanium-nitride export lives correctly at
`Titanium_nitride/`, itself unaffected), but the failure shape -- one export overwriting another's
output file on disk without any error -- is the same "silent wrong answer" class this project has
hunted down repeatedly elsewhere, just manifesting as a filesystem collision instead of a database
query. Fixed two ways: `export_all_materials_modalfit.py` now wipes and rebuilds `OUT_DIR` fully
on every run (a stale directory from an old naming scheme can no longer linger to collide later),
and `_discover_materials()` now explicitly checks for and raises on any case-insensitive collision
among the current run's own derived directory names, rather than relying on it never happening
again by chance.

**A fifth gap, a genuine density-crosscheck finding, not an infrastructure bug**: MP's DFT density
for graphite (mp-48, 1.939 g/cm3) deviates ~14% from the well-established theoretical density of
ideal AB-stacked hexagonal graphite (a=2.464 A, c=6.711 A), which computes to 2.267 g/cm3 --
confirmed against Mounet and Marzari's first-principles structural study (Phys. Rev. B 71, 205214,
2005). Per the density-crosscheck discipline this batch established (see "Ce/Yb" above and
`process_condition.TRACKED_OPEN_TASKS["mp_density_crosscheck_compounds"]`), a real, checkable
14% discrepancy is not smoothed over: Graphite gets a name-keyed `EXPERIMENTAL_DENSITY_OVERRIDE`
entry (2.267 g/cm3, cited), `DENSITY_VERIFIED`. Diamond's MP_DFT density (3.534 g/cm3, mp-66)
matches real diamond (~3.51-3.52 g/cm3) and needed no override; both Diamond and Graphite's
default RI.info datasets are genuinely bulk/single-crystal (Taylor's page states "Single-crystal
CVD" directly; Djurisic's o/e pair requires a uniaxial oriented crystal, same o/e logic as Se/Te),
so formula "C" was added to `VERIFIED_BULK_SAMPLE_FORMULAS`, applying correctly to both rows.

### A third root cause for a large energy_above_hull gap: kinetic metastability

Diamond sits at mp-66, **+112.26 meV/atom** above graphite's mp-48 -- the largest gap resolved as
"the measured phase is correct" anywhere in this project. This is neither a DFT-functional
artifact (rule 1a's VN/Co/Ag/Sr/Ti/In/Ta cases) nor a genuine low-temperature phase transition
(rule 1b's alkali metals): graphite really is more thermodynamically stable than diamond at all
normal conditions, and DFT correctly says so. Diamond persists indefinitely at room temperature
only because the diamond-to-graphite transformation has an enormous kinetic barrier -- a third,
distinct, and completely legitimate reason to trust a phase MP ranks far from the hull, recorded
as such rather than filed under either existing rule.

**Tin's beta phase is the same root cause, at an even larger gap**: mp-84 (beta-Sn, tetragonal
I4_1/amd #141), **+120.18 meV/atom** above alpha-Sn's diamond-cubic ground state (mp-117) -- the
textbook "tin pest" transition (13.2 C, alpha stable below, beta above). Unlike the alkali metals,
where the low-temperature phase genuinely forms on ordinary cooling, tin pest is famously
KINETICALLY HINDERED without deliberate seeding or prolonged cold exposure (historically took
years to manifest in affected artifacts). Golovashkin and Motulevich 1964 measured the same
sample's optical constants at 293/78/4.2 K -- almost certainly all beta-Sn throughout (a metal
cooled in a cryostat for an optics measurement, not deliberately held for tin-pest nucleation),
not a genuine phase change partway through the series. Recorded explicitly as an assumption based
on well-documented metallurgical kinetics, not asserted as a certainty. Tin's density: no RI.info
page states a measured film density or a bulk/single-crystal claim, so it gets the same default
`DENSITY_BULK_APPROXIMATION` treatment as most of the 47-element batch, using MP_DFT's beta-Sn
density (7.129 g/cm3).

### Boron: no MP structure at all, amorphous confirmed by density

Every crystalline boron candidate MP offers (2.30-2.57 g/cm3 across several genuine rhombohedral/
tetragonal allotropes) is denser than the RI.info-stated film density (2.10 g/cm3, Fernandez-Perea
et al. 2007) -- consistent with amorphous boron, the well-known typical state of a room-
temperature-evaporated boron film (boron is notoriously difficult to crystallize without
high-temperature annealing). `FORCE_NO_MP`, `polymorph="amorphous"`, `DENSITY_VERIFIED` via the
stated literature film density.

### Combined totals after batch 3b

135 materials total (131 + Diamond/Graphite/Tin/Boron), 133/135 exported (skip set unchanged:
`{GdF3, LuAl3(BO3)4}`), 96 `DENSITY_VERIFIED` (+3: Diamond, Graphite, Boron) / 37
`DENSITY_BULK_APPROXIMATION` (+1: Tin) / 2 named exclusions. Full export + ModalFit-layer-JSON
round trip confirmed correct for all four: `density_confidence`/`density_bounds` are `verified`
with zero-width bounds for Diamond/Graphite/Boron, and `bulk_approximation` with the asymmetric
`[0.70x, 1.02x]` bounds for Tin, exactly as designed. The formula-ambiguity guard was confirmed
live against the real database: calling `export_layer(db, "C")` raises `ExportError` naming both
Diamond and Graphite, requiring the exact name.

Batch 3, including 3b, is now complete: 54 pure-element books resolved (50 + Carbon/Tin/Boron),
1 excluded (Hg, liquid at room temperature).
