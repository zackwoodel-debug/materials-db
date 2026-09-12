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
correct entry (an `EXPECTED_SPACEGROUP`-style override, if a citable alternative exists at or
near the hull) or treat it as a genuine unresolved/excluded case -- never accept the phase claim
on the strength of the source description alone. See `scripts/build_oxides_csv.py`'s
`EXPECTED_SPACEGROUP` and `scripts/fluoride_nitride_sulfide_material_list.py`'s equivalent for
the pattern, including entries added purely as defensive pins for cases that were already
correct at the time they were checked (LaF3, MgF2, YbF3, LiCaAlF6, YLiF4, PbS, AlN, GaN, CdS,
GaS) -- pinning an already-correct match costs nothing and protects against a future MP update
or near-tie silently flipping it.

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
