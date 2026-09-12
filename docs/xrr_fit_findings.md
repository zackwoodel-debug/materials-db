# Real XRR fit through the full chain: findings

A real fit exercise (DB -> exporter -> ModalFit's FitEngine, not just "does ModalFit parse
it") run on a synthetic-but-realistic HfO2-on-native-SiO2-on-Si stack, using literature-typical
ALD film parameters as ground truth and real DB-derived SLD values throughout. No raw
instrument file was available for this exercise; the "data" is ModalFit's own `compute_xrr()`
evaluated at known true parameters plus realistic multiplicative noise -- sufficient to test
every question below, since the goal was pipeline correctness, not a new scientific result.

## Stated rules (read this section, not the narrative below, before writing a new
## reflectivity path)

These are the two conventions every exporter of a ModalFit layer/stack, and every reflectivity
implementation in this repo, MUST follow. Both were verified directly against refnx (the
package ModalFit's own fitting code uses) and against ModalFit's actual consumption code
(`physics.py`'s `_make_xrr_slab`/`_make_xrr_boundary`), not assumed from parsing successfully.

1. **A layer's `structural.roughness` value describes the interface ABOVE that layer** (between
   the previous entry in the stack and this one), never below. This is refnx's own
   `Scatterer.__call__(thick, rough)` convention. Concretely: the film/substrate interface
   roughness belongs on the SUBSTRATE entry's own `structural.roughness`, not on the last film
   layer's -- `export_stack()`'s `substrate_roughness_a` parameter exists because of this.
   `src/materials_db/simulation/xrr.py`'s `parratt()` had this backwards until this exercise
   (`roughness[j]` was read as "interface between layer j and j+1"; the correct read is
   `roughness[j]` = "interface above layer j", i.e. between j-1 and j).

2. **A positive imaginary SLD means absorption.** This is the convention `periodictable`'s
   `xray_sld()`, this DB's `xray_sld_imag` column, and every exported `xray.sld_imag` /
   `neutron.sld_imag` field already use -- do not conjugate it when handing it to refnx.
   `refnx.reflect.SLD` consumes it correctly as-is. `refnx.reflect.MaterialSLD` (the DEFAULT
   path ModalFit's `_make_xrr_slab` takes whenever `molecular.formula` + `molecular.density`
   are both present -- i.e. every layer this exporter emits) recomputes SLD independently from
   refnx's own tables rather than reading the field at all, and agrees with this DB's
   periodictable-derived value to 5 significant figures (verified for HfO2), so the two paths
   are consistent with each other, not silently divergent. Both of this repo's own `parratt()`
   implementations (`simulation/xrr.py`, `calculators/simulate_xrr.py`) used the imaginary SLD
   directly, unconjugated, in their `k_z`-style formula -- wrong for their own internal math,
   even though the DB's stored sign is the correct one to export.

A third, unrelated bug was found and fixed in `calculators/simulate_xrr.py`'s `parratt()`
specifically: its phase factor was `exp(2i*q_j*d)`, double what its own "full-Q" convention
(`q_j = 2*k_z`) needs. This doubled every Kiessig fringe frequency for any stack with a film,
independent of absorption -- a different bug from the two above, found the same way (cross-
checking against refnx on a real stack, not trusting that the formula "looked" like the
literature Parratt recursion).

All three are exact, not approximate: after fixing them, both `parratt()` implementations
reproduce refnx's reflectivity for a real absorbing air/HfO2/SiO2/Si stack to machine precision
(~1e-16 in log10(R)) -- see `tests/test_simulation_xrr_parratt.py` and
`tests/test_calculators_simulate_xrr_parratt.py`.

3. **Tightening a fit's bounds is not a substitute for choosing an appropriate optimizer, and
   doing one without the other can make a fit worse, not better.** Tight, physically-reasonable
   bounds run with L-BFGS-B (a local optimizer) produced a dramatically WORSE fit than the
   exporter's wide auto-defaults on the identical stack and starting guess -- chi^2 100x higher,
   every varying parameter pinned at its bound edge (a local-minimum trap, not a bounds
   failure). The SAME tight bounds recovered the true values exactly (matching the wide-bounds
   result) under Differential Evolution (a global optimizer). Before narrowing a parameter's
   bounds to "help" a fit converge, either verify the result doesn't change under a global
   optimizer first, or don't narrow bounds and switch optimizers in the same step -- you cannot
   tell which one fixed (or broke) the fit if you change both at once.

4. **A thin, low-contrast layer buried beneath a much thicker, higher-contrast film has a real,
   optimizer-independent thickness identifiability limit** -- not a bug, and not something a
   different algorithm or tighter bounds will fix. Confirmed here: SiO2 (15A) beneath HfO2
   (250A) recovered to only -8.9% thickness under BOTH L-BFGS-B and Differential Evolution,
   identically. A future fit on a similar geometry landing in this same range is reproducing a
   known measurement limitation, not regressing -- don't treat it as a new bug without first
   checking whether the buried layer is thin and low-contrast relative to what's above it.

## What was checked at the exporter boundary specifically

Fixing `xrr.py`'s internal conventions against refnx does NOT by itself prove the EXPORTER
writes JSON that ModalFit's fitting path reads with the same conventions -- those are two
different boundaries. Both were checked directly, not inferred:

- **Roughness**: `physics.compute_xrr()` consuming a stack built by `export_stack()` (with the
  substrate-roughness fix applied) was compared against the fixed `parratt()` fed the exact same
  per-entry roughness values pulled straight out of the exported JSON. They agreed to machine
  precision. Conclusion: the exporter was never wrong here -- `export_layer()`/`export_stack()`
  just write "this layer's own roughness value" into this layer's own JSON entry, and BOTH refnx
  and the fixed `parratt()` interpret that value as "interface above this layer" identically.
  The gap that existed was `export_stack()`'s substrate entry having no `structural` key at all
  (fixed separately, see the commit that added `substrate_roughness_a`) -- a missing field, not
  a wrong-convention field.
- **Imaginary SLD sign**: verified `refnx.reflect.SLD(complex(real, +imag))` (the fallback path,
  used when `molecular.formula`/`density` are absent) produces correctly-damped, not amplified,
  reflectivity with the value exactly as stored -- no conjugation needed on export. Verified
  `refnx.reflect.MaterialSLD` (the default path, used for every layer this exporter emits, since
  it always sets both `molecular.formula` and `molecular.density_g_cm3`) independently computes
  a consistent value (67.679+4.414j from `MaterialSLD("HfO2", 10.241, probe="x-ray")` vs.
  67.679+4.414j from this DB's periodictable-derived value). No double-conjugation anywhere in
  either path.

Net: **no exporter fix was needed for either convention** -- both were already correct at the
JSON boundary. The bugs were entirely inside this repo's own `parratt()` implementations, which
nothing had ever cross-checked against ModalFit/refnx before. `export_layer()`/`export_stack()`
now state both conventions explicitly in their docstrings so a future caller (or a future
reflectivity implementation) doesn't have to re-derive them the way this exercise did.

## Answers to the original fit questions

**Do the auto-defaulted bounds produce a usable fit, or do they need per-parameter overrides?**
Yes, as-is. The exporter's defaults (no explicit `thickness_min/max`/`roughness_min/max`) fed
into `extract_params()`'s fallback formula (`[0.2*t, 3*t+50]` for thickness, `[0, 50]` for
roughness, computed from the STARTING value) produced a usable fit with L-BFGS-B from a
substantially perturbed starting guess (thickness off by 25-35%, roughness off by 40-60%): HfO2
thickness and roughness recovered to within 0.01%/0.52% of truth, SiO2 (native oxide) roughness
to 0.02%. Tighter, hand-picked bounds made the SAME fit dramatically worse under the same
optimizer -- see stated rule 3 above. No exporter change is recommended here; this is an
algorithm-selection concern for the fit's caller, not a schema/bounds defect.

**Can the schema express a full stack -- substrate, multiple layers, ambient -- or has it only
worked for single layers?** Yes, once the substrate-roughness gap above was fixed. A real
4-entry stack (ambient=air, HfO2 film, native SiO2 film, Si substrate) assembled via
`export_stack()` was consumed correctly end-to-end by `extract_params()`, `compute_xrr()`, and
`FitEngine` with no schema-level failures. This exerciser is the first time `export_stack()`
(not just `export_layer()`) has actually been run through a real fit rather than just JSON-
validated.

**Do the fitted values contradict any DB SLDs we're confident in?** No. SLD was held fixed at
the DB's values throughout (only thickness/roughness were varied) and the fit still converged
to within 0.01-0.5% of the true HfO2 thickness/roughness -- if the DB's HfO2 SLD were
meaningfully wrong, the fit would have had to bias thickness/roughness to compensate for the
mismatch (thickness and SLD trade off against each other in the optical path length), and it
didn't need to. This corroborates the DB's SLD values rather than contradicting them.

**One residual, real (not a bug) finding**: SiO2 thickness recovered to only -8.9% (13.67A fit
vs. 15A true) under both L-BFGS-B and Differential Evolution, identically -- see stated rule 4
above. Not a schema or exporter defect.

## Other things export_stack() has never been exercised on before this session

The substrate-roughness gap was found specifically because `export_stack()` had never been run
with more than one film layer before. Auditing the rest of the exporter for the same "only ever
exercised single-layer/single-stack" shape found one more, confirmed by reproducing it directly:

- **Two layers sharing the same default label silently collide.** `export_layer()`'s default
  `label` is `formula` (or `formula_polymorph`) when the caller doesn't supply one, and
  `export_stack()` writes every film layer's sidecar n,k CSV into the SAME `nk_csv_dir` using
  `f"{label}_nk.csv"`. A stack with the same material appearing twice at the same dataset_label
  (e.g. a repeated-unit multilayer/Bragg mirror/superlattice -- a common real sample type, not a
  contrived case) writes the second layer's sidecar file over the first's, and -- more
  significantly -- `physics.extract_params()` builds each fittable parameter's key as
  `f"{label}:thick"` etc., so both layers get the IDENTICAL key. Confirmed directly: a
  3-layer stack (SiO2 / Ta2O5 / SiO2, both SiO2 layers at 50A and 15A respectively) produces two
  `ParamSpec` objects both keyed `"SiO2_amorphous:thick"`. Since `FitEngine._x_to_vp` builds a
  plain dict keyed by this string, marking both as `vary=True` means the optimizer cannot move
  the two physically distinct layers independently -- whichever value the dict resolves to gets
  applied to both. Not fixed in this pass (the fit exercise's stack has no repeated material); a
  fix would need `export_stack()` to auto-disambiguate a caller-unspecified label when the same
  formula+dataset_label appears more than once in one `layers` list (e.g. suffixing repeats with
  `#2`, `#3`, ...), or to raise rather than silently collide. Flagging this now rather than
  finding it the same way the substrate-roughness gap was found.
