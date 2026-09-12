# Batch 2 Scoping Report

Read-only analysis. No ingestion, no schema changes, no DB writes. RI.info clone pinned at
`src/materials_db/pipeline/refractiveindex_contract.py`
(`polyanskiy/refractiveindex.info-database @ c5c2f188e848453def5970e347399d653df2ffc2`,
the same commit `materials_oxide_test.db`'s existing pipeline was built against).

**Correction (post-triage, before bulk processing):** the sulfide count below (14 books) was
wrong. Re-walking the pinned catalog directly while assembling
`scripts/fluoride_nitride_sulfide_material_list.py` found only 8 binary-ish sulfide books
(As2S3, CdS, EuS, GaS, GeS2, HgS, PbS, ZnS) after excluding TMDCs/ternary chalcopyrites/gases/
CaSO4 (a sulfate, not a sulfide)/PBS (buffer-solution misparse) -- verified against
`catalog-nk.yml` directly, not re-trusted from the count below. **Corrected total: 32
materials (18 fluorides + 6 nitrides + 8 sulfides), not 38.** See that module's docstring for
the full reasoning and the final per-material resolution record (including a 9th trap found
beyond the original 8-material triage list: HgS's RI.info page states the correct phase
name directly, but its lowest-`energy_above_hull` MP entry is still the wrong polymorph).

## A. Trait-cluster counts (main + other shelves, 368 books / 1471 pages)

| Trait | Split | Books |
|---|---|---|
| 1. `periodictable.formula()` parses the book id | parses / doesn't | 266 / 102 |
| 4. Dispersion data shape | tabulated-only / formula-only / mixed | 181 / 118 / 69 |
| Contains oxygen (already our territory) | yes / no | 72 / 296 |

Anion-class breakdown (only meaningful for the 266 that parse):

| Class | Books | Pages |
|---|---|---|
| oxide (existing 50-oxide territory) | 72 | 266 |
| pure element | 59 | 420 |
| other_chalcogenide (Se/Te-based) | 32 | 131 |
| other_halide (Cl/Br/I-based) | 25 | 38 |
| **sulfide** | 24 | 112 |
| **fluoride** | 19 | 66 |
| other_binary_or_more | 18 | 95 |
| **nitride** | 11 | 49 |
| carbide/other-C | 6 | 28 |
| unparseable id | 102 | 266 |

Trait 3 (polymorph vs. composition-parameter vs. deposition-method vs. manufacturer vs.
tacticity) doesn't reduce to clean counts the way 1/2/4 do -- it's page-name/comment
classification, not a formula property. Regex-based scanning across all 368 books found:
zero tacticity hits (expected -- that's a polymer-shelf concept, `organic`/`glass`, not
`main`/`other`), a handful of manufacturer/grade hits (glass-adjacent books that leaked into
`other`), and real hits for polymorph, composition-parameter, and deposition-method language
concentrated almost entirely in the fluoride/nitride/sulfide candidate pool itself -- detailed
in B/C below, since that's where it matters for batch 2.

## B. Testing the fluoride/nitride/sulfide hypothesis

**Cleanup needed before counting "the batch":** the raw anion-class buckets include false
positives my formula-based clustering can't filter on its own:
- Gases, not solids: `SF6`, `NH3`, `N2`, `CS2` -- optical constants for a gas/liquid aren't the
  same kind of material as a crystalline film.
- Organic-inorganic hybrids caught only because they contain an N atom: `CH3NH3PbBr3/Cl3/I3`
  (methylammonium lead halide perovskites) -- not nitrides in any useful sense.
- **A real misparse, not a judgment call**: book id `PBS` parses cleanly under
  `periodictable.formula()` as P+B+S -- but the book is **"Phosphate Buffered Saline (PBS)"**,
  a biology buffer solution, not a chemical compound at all. This is the concrete answer to
  "where does it break": criterion 1 (does the identifier parse) is necessary but **not
  sufficient** -- a parseable string is not proof the string denotes the material it looks like.
  Any batch-selection process needs a name/identity sanity check, not just a periodictable try/except.
- Ternary chalcopyrite-type NLO crystals (`AgGaS2`, `BaGa4S7`, `CdGa2S4`, `CuGaS2`,
  `HgGa2S4`, `LiGaS2`, `Ag3AsS3`, `NiPS3`) are real sulfides but not "simple" the way
  CaF2/MgF2/BaF2/LiF are -- excluded from the core count, noted separately.
- Transition-metal dichalcogenides (`MoS2`, `WS2`, `TaS2`, `ReS2`, `PtS2`, `SnS2`) are
  overwhelmingly **layer-count-dependent** (MoS2 alone: 29 pages, mostly monolayer/2L/3L/.../bulk
  variants) -- this is a genuinely new axis type, not one of the 4 traits and not something our
  `dataset_label` convention (`polymorph | source | axis`) has a slot for. Picking "which
  layer-count is the default" is a new kind of decision, not a repeat of the oxide workflow.
  Recommend excluding from a "no new machinery" batch; a dedicated 2D-materials batch later
  would need to design for this axis explicitly.

**Cleaned counts:**

| Class | Books | Pages | Tabulated-only | Formula-only | Mixed |
|---|---|---|---|---|---|
| Fluorides (excl. SF6) | 18 | 65 | 2 | 9 | 7 |
| Nitrides (excl. gases/hybrids) | 6 | 37 | 2 | 0 | 4 |
| Binary-ish sulfides (excl. ternary/TMDC/CS2/PBS) | 14 | 79 | 8 | 2 | 4 |
| **Total** | **38** | **181** | 12 | 11 | 15 |

All 38 satisfy trait 1 (parse) and trait 4 (both tabulated and formula datasets present, no new
loader logic needed -- exactly the same two DATA block families the oxide pipeline already
handles). Trait 2 (density source) spot-checked below. Trait 3 checked per-material in the
triage list.

**Density spot-check, 20 materials (Materials Project, read-only queries):**

| Material | MP entries | Lowest-hull space group | Matches expected structure? |
|---|---|---|---|
| BaF2, CaF2, CdF2, CsF, KF, LiF, NaF, PbF2, RbF, SrF2 | 1-4 each | Fm-3m (#225) | Yes -- fluorite (MX2) or rock-salt (MX) as expected, textbook match |
| LaF3 | 8 | P-3c1 (#165) | Yes -- tysonite, expected for light lanthanide trifluorides |
| YbF3 | 3 | Pnma (#62) | Yes -- YF3-type, expected for heavy lanthanide trifluorides |
| ThF4 | 2 | C2/c (#15) | Plausible, consistent with reported ThF4 structure |
| AlN | 4 | P6_3mc (#186) | Yes -- wurtzite, expected |
| CdS | 6 | P6_3mc (#186) | Yes -- wurtzite (greenockite), expected |
| **CeF3** | 4 | Cmcm (#63), Ehull=0.00 | **No** -- P-3c1 (#165, tysonite, matching its light-lanthanide neighbor LaF3) is ALSO at Ehull=0.00. A tie at the hull, and the wrong one sorts first. |
| **GdF3** | **1 total** | Fm-3m (#225) | **No** -- expected YF3-type Pnma (#62) for a heavy lanthanide trifluoride (same family as YbF3 above). No alternative exists in MP at all -- worse than CeF3, same shape of problem as BeAl6O10 in the oxide batch. |
| **BN** | 27 | P-6m2 (#187), Ehull=0.00 | **No** -- our RI.info pages are all explicitly labelled "h-BN". The standard hexagonal h-BN space group P6_3/mmc (#194) exists at only +1.75 meV/atom (mp-629015), a near-degenerate stacking-polytype situation, well documented physically for layered BN, not a DFT artifact. |
| **Si3N4** | 16 | P6_3/m (#176), Ehull=0.00 (β-Si3N4) | **Unresolved, not simply "no"** -- α-Si3N4 (P31c #159) is at only +3.54 meV/atom, also a real, well-known near-degenerate polymorph pair. But neither may be right: see below. |

**Verdict on B's core claim ("changes nothing"): partially right, more precisely stated.**
Every one of these 20 has *a* density source (MP coverage is actually better here than the
oxide set's -- no `LuAl3(BO3)4`-style total misses in this spot-check). But **4/20 (20%)**
already need the exact same "don't trust lowest-hull blindly" scrutiny the oxide batch required
(CeF3, GdF3, BN, Si3N4) -- so the honest framing isn't "this batch needs no verification," it's
"this batch needs the *same, already-built* verification workflow, with no new machinery." That
is still a real, meaningful advantage over building 2D-materials layer-axis handling from
scratch -- just not literally zero-touch.

**Single-dominant-phase triage list** (the batch's VO2/TeO2/Ta2O5 equivalent):

- **ZnS** -- confirmed, as you predicted. Two industrially-relevant phases: cubic sphalerite
  (stable, RT) and hexagonal wurtzite (higher-temp, also common in nanostructures). Two of five
  RI.info pages explicitly say "Cubic ZnS"; the other three (Querry, Bond, Amotchkina) don't
  state phase.
- **GaN** -- a second confirmed case, same shape as ZnS: page `Lin-wurtzite` and page
  `Lin-zincblende` are explicitly two different measurements from the *same* 1993 paper on the
  *two different* polymorphs. Also has an `axis_polymorph` + `axis_deposition_method` hit in the
  automated scan.
- **AlN, Si3N4** -- non-stoichiometric composition-parameter datasets exist alongside the
  presumed-stoichiometric ones (`Beliaev1/2`, `Kischkat` for AlN; `Vogt-1.91/2.09/2.13` for
  Si3N4 -- the `1.91` etc. are literal N:Si stoichiometric ratios). This is trait 3's
  "composition parameter" category confirmed concretely, and the default choice (stoichiometric
  bulk vs. non-stoichiometric film) needs to be made deliberately, same as we did for MoO3/Nb2O5's
  process variants.
- **TiN, VN, EuS** -- no bulk single-crystal reference dataset at all; every entry is a thin
  film with an explicit deposition method or anneal temperature (`TiN`: sputtering vs. ALD,
  and 700/800/900°C anneal variants). This is the Ta2O5/Nb2O5 shape of problem (deposition-method
  axis, no crystalline default), not a new one -- but it does mean these three don't have a
  "just pick the obvious bulk entry" answer either.
- **Si3N4 (separately from the polymorph tie above)** -- the two candidate optical datasets
  (Philipp 1973, Luke 2015) are near-certainly **amorphous** CVD-deposited films in actual
  practice (Luke's is the well-known LPCVD stoichiometric-Si3N4 photonics platform), which would
  make the α/β-vs-lowest-hull question moot -- neither crystalline polymorph would be the right
  MP pairing at all, same resolution as SiO2/Ta2O5/GeO2/Nb2O5 in the oxide batch. RI.info's own
  COMMENTS field doesn't state this explicitly (Philipp: empty; Luke: describes the film stack,
  not crystallinity) -- this is the one in this list that genuinely needs a source read, not
  metadata inference.
- **GaS, HgS** -- checked and likely fine: HgS's RI.info page name explicitly says "α-HgS"
  (cinnabar, the stable phase; metacinnabar is the other known polymorph but isn't what's
  measured here). GaS has multiple known polytypes (2H/4H etc.) and nothing in the RI.info
  metadata states which; lower confidence than HgS, worth a quick source check rather than
  assuming.
- **As2S3** -- mirrors the SiO2 quartz-vs-fused-silica precedent directly: the RI.info default
  data (Slavich et al., biaxial α/β/γ) is necessarily *crystalline* (orpiment) since biaxial
  optics only apply to ordered crystals -- but As2S3 is far more commonly used and known as an
  *amorphous* chalcogenide glass in photonics. Whichever one is intended needs to be a deliberate
  choice, not a default.

## C. Recommendation and the resolution gate

**Recommended batch 2: the cleaned fluoride/nitride/sulfide set, 38 materials, with 8 flagged
for individual triage before inclusion** (ZnS, GaN, AlN, Si3N4, TiN, VN, EuS, As2S3 -- GaS/HgS
lower-priority spot-checks). This is still the better candidate than the alternatives I can see
in the walk (TMDCs need new layer-axis machinery; `other_chalcogenide`/`other_halide` haven't
been scoped at all yet) -- I'm not proposing a different cluster, just a corrected count and an
explicit triage list, the same shape of adjustment the oxide batch went through.

**The gate, stated as you asked -- 100% resolved, not 100% verified:**

Every one of the 38 (minus any dropped after triage) ends the batch in exactly one of three
states, no fourth option:
1. **Verified**: MP structure confirmed to match the intended phase (via provenance/ICSD chain
   or a literature space-group check, same standard as the oxide batch's `EXPECTED_SPACEGROUP`
   entries), or no-MP-match confirmed with a cited literature density.
2. **Named exclusion**: no density obtainable from either source, stated with a reason
   (`LuAl3(BO3)4`-shaped outcome).
3. **Explicitly flagged unresolved**: a real ambiguity exists (phase, axis type, or missing
   reference structure) and is recorded as such with what's blocking it -- never silently
   defaulted to "lowest energy_above_hull" or "first dataset alphabetically."

**What's automatable from RI.info metadata alone** (no source read needed):
- Detecting axis type from page-name patterns: polymorph names, non-stoichiometric labels,
  temperature/anneal conditions, deposition method keywords -- all directly stated in page
  names/COMMENTS for every case found above except Si3N4's amorphous question.
- Flagging "no bulk single-crystal reference exists" (TiN/VN/EuS) -- derivable from the absence
  of any dataset lacking a deposition-method or thin-film qualifier.
- Flagging "MP lowest-hull disagrees with the compound's known structural family" for the
  fluorides/nitrides (CeF3 vs. LaF3's family, GdF3 vs. YbF3's family, BN vs. h-BN's standard
  space group) -- this is exactly the `EXPECTED_SPACEGROUP` cross-check pattern already built
  for the oxide pipeline, reusable directly, no new logic.
- Confirming HgS's phase (page name states "α-HgS" directly).

**What needs you to read a source:**
- Si3N4: whether Philipp 1973 and Luke 2015's samples are amorphous or crystalline -- RI.info's
  own metadata doesn't say, and it's the single highest-leverage unresolved question in this
  batch (it changes whether Si3N4 needs an MP pairing at all).
- GaS: which polytype (2H vs. others) Kato/Zotev actually measured -- not stated in RI.info
  metadata.
- GdF3: whether ICSD or a crystallography reference confirms Fm-3m or the expected YF3-type
  Pnma structure -- MP has no alternative to cross-check against, same situation as BeAl6O10,
  which needed a literature/ICSD-provenance check rather than an in-database comparison.

Waiting on your approval before running anything.
