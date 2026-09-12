# Pipeline principles

Durable rules this project has learned the hard way -- found by deliberately looking, never by
something failing loudly on its own. Read this before starting a new material batch or a new
reflectivity/export code path; it exists so neither has to rediscover what's already here.

## 1. An RI.info page name or COMMENTS agreeing with the intended phase is NOT verification

A material's RI.info page literally stating the phase you expect (e.g. "Bond et al. 1967:
alpha-HgS", "Cubic ZnS", "h-BN") is necessary evidence but not sufficient. It tells you what the
person who wrote the RI.info entry believed they measured -- it says nothing about whether
Materials Project's lowest-`energy_above_hull` entry for that formula is actually that phase.

**The default case, not an edge case**: of the 5 batch-2 materials cleared this way (ZnS, GaN,
BN, HgS, As2S3), 3 (60%) had a wrong lowest-hull MP pick once actually queried -- HgS's
lowest-hull entry was metacinnabar, a different polymorph from the alpha-HgS (cinnabar) RI.info's
page names; ZnS's was a different stacking polytype from the cubic sphalerite two of its five
pages state explicitly; BN's was a different, non-standard stacking polytype from the h-BN every
one of its pages states. Only GaN's happened to already be correct, and As2S3's amorphous
resolution didn't have an MP structure to get wrong.

**The rule**: every material with an asserted polymorph/phase -- however that assertion was
reached, whether from RI.info metadata, general crystallographic knowledge, or a prior batch's
spot-check -- gets an actual MP query, compared against the specific space group the intended
phase implies, before it's accepted. If MP's lowest-hull entry doesn't match, either find the
correct entry (an `EXPECTED_SPACEGROUP`-style override) or treat it as a genuine
unresolved/excluded case -- never accept the phase claim on the strength of the source
description alone. See `scripts/build_oxides_csv.py`'s `EXPECTED_SPACEGROUP` and
`scripts/fluoride_nitride_sulfide_material_list.py`'s equivalent for the pattern, including
entries added purely as defensive pins for cases that were already
correct at the time they were checked (LaF3, MgF2, YbF3, LiCaAlF6, YLiF4, PbS, AlN, GaN, CdS,
GaS) -- pinning an already-correct match costs nothing and protects against a future MP update
or near-tie silently flipping it.

### 1a. A large energy_above_hull gap is a signal to investigate, not grounds to exclude

Every override found through rule 1 above, up through batch 2, was a NEAR-degenerate tie (CeF3,
BN, HgS, ZnS, Se: all within ~2 meV/atom of the hull). That pattern quietly became an unstated
assumption: "the correct structure, if it exists in MP at all, will be near the hull; if nothing
near the hull matches, there's nothing to find." **VN (batch 3) disproved this directly**: its
correct entry (mp-925, Fm-3m, the well-documented rock-salt structure isostructural with the
already-confirmed TiN) sits at +190 meV/atom -- two orders of magnitude further from the hull
than every prior override, and would have been missed entirely by a "check near the hull, stop"
search.

**The corrected rule**: search MP's FULL candidate set for a formula, not a window near the hull
-- `mp-api`'s `summary.search(formula=...)` already returns everything regardless of
`energy_above_hull`; the mistake was in how far down the sorted list a human kept looking, not in
the query itself. A large gap between the lowest-hull entry and the one that actually matches the
measured structure is a signal that something (a magnetic-ordering sensitivity, a DFT-functional
limitation for that particular chemistry, a genuinely metastable-but-real experimental phase) is
making the DFT ground state disagree with reality -- investigate why, the way VN's entry was
attributed to vanadium's partially-filled d-orbitals being a known difficulty for standard
DFT-GGA, rather than silently accepting lowest-hull OR silently excluding for lack of a
NEAR-hull alternative.

**Consequently: "no near-degenerate alternative exists" is not sufficient grounds for a
NAMED_EXCLUSION.** Before excluding a material for lack of an MP match, confirm the full
candidate set was searched (not just the first few sorted by energy_above_hull) and that
NOTHING in it -- at any energy_above_hull -- matches the expected structure. GdF3 was
re-examined under this corrected rule and confirmed to still be a genuine named exclusion: MP
has exactly ONE entry for GdF3 (mp-972965) at any energy_above_hull, full stop, so there was
never anything a wider window could have found. That is a different, and stronger, finding than
"no NEAR-hull alternative exists" -- it is the actual reason a named exclusion is justified here,
not the previously-implied "the alternative wasn't close enough."

### 1b. A material with a known low-temperature phase transition is EXPECTED to trap this way

Applying rule 1a to all 47 remaining pure elements (batch 3) found 16 confirmed traps (34% --
see docs/batch3_scoping_report.md Part G), and they were not scattered: **all 5 alkali metals
present (Li, Na, K, Rb, Cs) were wrong at lowest-hull, every one.** The mechanism is
understood, not mysterious: MP's DFT calculation is a 0K ground-state search, with no
vibrational or entropic corrections. For a material with a genuine low-temperature phase
transition, the 0K ground state IS the low-temperature phase -- correctly, physically, that's
what DFT is supposed to find. But refractiveindex.info's optical measurements are taken at or
near room temperature, where a DIFFERENT phase is the one that actually exists. Lithium and
sodium are the clearest cases: both are well documented to undergo a bcc -> close-packed
martensitic transition below roughly 70-80 K, so DFT correctly returns that low-temperature
phase as lowest-hull, and a room-temperature optical measurement is just as correctly NOT that
phase.

**The rule**: this is not a surprise to rediscover per material -- it is PREDICTABLE in advance.
Before accepting any lowest-hull MP structure for a material, check whether that material has a
well-documented phase transition at or below typical measurement conditions (roughly 0-350 K
covers most RI.info entries, including "room temperature" and most stated cryostat studies). If
it does, the ambient/room-temperature phase -- not lowest-hull -- is the one to check for a
matching entry first, the same way `EXPECTED_SPACEGROUP` already encodes "the phase we expect,"
just applied proactively from known thermodynamics rather than reactively from a hull-gap
surprise. Alkali metals, and any material with a documented martensitic or order-disorder
transition near typical lab conditions, should be treated as HIGH PRIOR RISK for this specific
failure mode from the start of triage, not discovered by accident.

This is related to, but distinct from, the broader "small hcp/fcc/bcc energy differences
sensitive to magnetic ordering and DFT functional choice" pattern behind Co, Ag, Sr, Ti, In, Ta,
and VN's traps -- those are DFT-energetics-sensitivity issues without necessarily involving a
literal temperature-driven transition, and are still covered by the general rule 1a (search the
full set, treat a gap as a signal). Rule 1b is the narrower, MORE PREDICTABLE special case: a
DOCUMENTED low-temperature transition is a known, checkable fact about the material, not
something that can only be found after the fact.

**Audit of already-loaded materials for this specific exposure** (a temperature-driven phase
transition near typical RI.info measurement conditions), done on request rather than assumed
clean:

- **VO2** (oxide batch) -- NOT newly exposed, but the reason it wasn't is worth stating
  explicitly rather than leaving as "we got lucky": VO2's transition (68 C, insulating M1 below,
  metallic rutile above) was independently verified against the specific paper's stated
  measurement condition (Beaini et al., 25 C, confirmed below the transition) -- this is rule 1b
  applied correctly by accident, not because the risk was recognized as a category at the time.
- **BaTiO3** (oxide batch) -- FLAGGED, not previously re-verified against this specific concern.
  BaTiO3 has THREE phase transitions clustered close to typical lab temperature
  (rhombohedral -> orthorhombic at -90 C, orthorhombic -> tetragonal at 5 C, tetragonal -> cubic
  at 130 C). The existing `EXPECTED_SPACEGROUP` entry (tetragonal, #99) is correct for any
  measurement between 5 C and 130 C, which covers ordinary room temperature -- but the specific
  citation's (Wemple et al. 1968) exact measurement temperature was not cross-checked against the
  5 C lower bound the way VO2's was. Low risk in practice (5 C is an unusually cold "room
  temperature"), but not a verified certainty the way VO2 now is.
- **WO3** (oxide batch) -- FLAGGED as the closest real analogue to the alkali-metal pattern in
  the already-loaded set. WO3 has a transition at 17 C (monoclinic-II below, monoclinic-I above)
  -- 17 C is within normal ambient temperature variance for a lab, not a comfortably-distant
  margin like BaTiO3's 5 C or VO2's 68 C. The two monoclinic phases are crystallographically
  distinct despite the superficial similarity, and the current `EXPECTED_SPACEGROUP` entry
  (`[14, 15]`, monoclinic) was not narrowed to confirm which specific monoclinic phase the
  citation's stated temperature implies.
- **KNbO3** (oxide batch) -- minor flag. Transition at -10 C (rhombohedral below, orthorhombic
  above); the existing orthorhombic assignment is correct for any normal room-temperature
  measurement, comfortably above -10 C. Lower priority than WO3.
- **This audit is a domain-knowledge review, not a fresh literature/MP check per material** --
  unlike the pure-element trap-finding above, WO3/BaTiO3/KNbO3 were not independently re-verified
  against their citations' exact stated temperatures the way this rule calls for. If tighter
  confidence is wanted, that verification (matching each citation's stated condition against the
  known transition temperature, the same check already done for VO2) is the concrete next step,
  not a re-guess from memory.

## 2. Two related but distinct anti-patterns, both found only by looking

### 2a. A lookup or classification silently returning a plausible-looking wrong answer

Four confirmed instances, all the same shape -- code that had a real gap, produced a
plausible-looking value instead of an error, and was only caught by manually inspecting output
rather than by anything failing:

- `_lookup_mp_id()` only read `data/oxides_50.csv`, so every batch-2 material's `mp_id` silently
  came back `None` -- looked like "no MP match found" (a legitimate, common outcome), not like a
  bug.
- `export_layer()` hardcoded `"material_type": "oxide"` for every layer regardless of formula --
  every batch-2 fluoride/nitride/sulfide layer was silently mislabeled, and nothing about a JSON
  file saying `"material_type": "oxide"` looks wrong on inspection unless you already know the
  material isn't an oxide.
- Batch 1's polymorph-prefix parsing (`_polymorph_prefix()`'s original `split(" | ")[0]`) treated
  every physical_properties quantity marker (`xray_sld_real`, `density_MP_DFT`, ...) as if it
  were a distinct named polymorph, for any material with no real polymorph -- again, a
  plausible-looking (if you don't already know the material has no polymorph) wrong grouping.
- `export_stack()`'s substrate entry had no `structural` key at all, so ModalFit's
  `_make_xrr_boundary()` read the film/substrate interface roughness as `0.0` (a perfectly sharp
  interface) with no error -- a value that is itself a valid, unremarkable-looking roughness for
  many real ideal-case fits, not an obviously-wrong sentinel.

**The rule**: where a lookup or classification cannot determine a real answer, it must raise or
emit an explicit, distinguishable "unknown"/`None`-with-a-reason -- never a value indistinguishable
from a correct one. `_classify_material_type()` returning `"unknown"` (never guessing a family
from an unrecognized formula) and `EXCLUSION_STATE`'s three distinct, queryable states (never
collapsing "no answer" into a bucket that also contains "the answer is X") are the shape to copy.

### 2b. A formula that parses and runs, and produces a wrong-but-plausible-looking curve

A different failure shape, found in the same session: `src/materials_db/simulation/xrr.py` and
`src/materials_db/calculators/simulate_xrr.py` each had their own from-scratch Parratt-recursion
implementation, and each had real, independent bugs (absorption-sign inversion in both; a
roughness-interface indexing error in one; a doubled phase factor in the other) that had never
been caught, because nothing had ever cross-checked either one against an independent, trusted
reference implementation (refnx, the package ModalFit's own fitting code uses) -- only against
each other, or against nothing at all. Every one of these functions ran without error, returned
values in `[0, 1]` that looked like a plausible reflectivity curve, and passed every existing
test, because no existing test compared the OUTPUT against a known-correct answer -- only its
shape, range, or internal self-consistency. See `docs/xrr_fit_findings.md` for the full
diagnosis and the stated conventions (roughness attachment side, imaginary-SLD sign) any new
reflectivity path in this repo must follow.

**The rule**: "it parses" and "it runs without an exception" are not evidence of correctness for
any physics/reflectivity/structure-matching code. Validate new quantitative code against an
independent, external, trusted reference (a published value, a different well-established
implementation, a directly-queried external database) before trusting its output -- self-
consistency (does my own code agree with my own code) proves nothing.
