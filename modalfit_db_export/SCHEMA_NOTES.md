# ModalFit slab-model JSON contract -- schema notes (CHECKPOINT 1)

Source: read-only clone of https://github.com/agauer/modalfit (shallow, 1 commit)
at a scratch dir outside materials-db. Per the task doc, the README is NOT
authoritative -- these notes are from `physics.py`, `slab_model_builder.py`,
`model_predictor.py`, `server.py`, and `loaders.py` directly, plus empirical
tests against the installed `refnx`/`periodictable` packages ModalFit depends on.

**Biggest finding up front:** there are TWO independent, mutually-incompatible
schema conventions for a layer's SLD in this codebase (see Q1/gaps). The one
that matters is whichever `server.py` actually imports -- confirmed to be
`physics.py` (`server.py:25: import physics as P`). `model_predictor.py`,
despite its name, is a separate standalone Tkinter tool not wired into the
live app at all, and expects a different, incompatible convention.

## Q1: Exact JSON shape

### Top-level (from `slab_model_builder.py:_collect()`, lines 1193-1226)

```json
{
  "stack_id": "20260101_sample1_slab_v1",
  "sample_id": "sample1",
  "created_at": "2026-01-01T12:00:00",
  "version": 1,
  "provenance": {"user": null, "proposal_id": null},
  "material": {"morphology": null, "blend_ratio": null, "casting_solvent": null,
               "deposition_method": null, "deposition_conditions": null,
               "annealing_conditions": null},
  "n_layers": 2,
  "stack": [ /* ambient, layer1, ..., layerN, substrate -- one list, ordered */ ]
}
```

`physics.py` and `model_predictor.py` only ever touch the `stack` list --
`stack_id`/`sample_id`/`provenance`/`material` are metadata the GUI builder
writes but the physics/extraction code never reads. This means **the
`provenance` dict is a safe, existing, tolerated place to put our own
citation/mp_id/dataset_label metadata** (Q: task step 2's provenance
requirement) -- nothing downstream will choke on extra keys there, since nothing
reads that block at all currently. Confirmed no code path raises/validates on unknown top-level keys.

### Per-entry (`stack` list items), from `slab_model_builder.py` `LayerEditor.get_data()` (747-768), `AmbientEditor.get_data()` (467-...), `SubstrateEditor.get_data()` (893-...), cross-checked against `physics.py`'s readers:

```json
{
  "label": "TiO2_layer",
  "role": "layer",
  "material_type": "oxide",
  "molecular": {"formula": "TiO2", "density_g_cm3": 4.2362},
  "structural": {
    "thickness": {"value": 500.0, "min": 400.0, "max": 600.0},
    "roughness": {"value": 5.0, "min": 0.0, "max": 20.0}
  },
  "optical": {"model": "Tabulated n,k", "params": {"file": "tio2_rutile_nk.csv"}},
  "xray":    {"sld_real": {"value": 34.5178, "min": null, "max": null},
              "sld_imag": {"value": 1.742017}},
  "neutron": {"sld_real": {"value": 2.6313}, "sld_imag": {"value": 0.000541}},
  "viscoelastic": {"density": {"value": 4236.2}, "viscosity": null,
                    "modulus_storage": null, "modulus_loss": null}
}
```

**Required vs optional, per `physics.py`:**
- `label`, `role`: role is read as `entry.get("role")`, with `None`/anything not
  literally `"ambient"`/`"substrate"` treated as a film layer everywhere in
  `physics.py` (`compute_se:280`, `_compute_reflectometry:439`,
  `extract_params:885-887`, each with an explicit comment that a *missing*
  `role` key must be treated the same as `"layer"` -- this was clearly a fixed
  bug at some point, so exporting an explicit `"role": "layer"` for every film
  layer is the safe, unambiguous choice rather than relying on this fallback).
- `structural.thickness`/`roughness`: needed by XRR/NR/SE (a layer with no
  thickness set is effectively skipped/zero -- `_layer_thickness_A` defaults
  to `0.0` if absent, no error raised).
- `xray.sld_real` / `neutron.sld_real`: only required if `molecular.formula`+
  `molecular.density` are absent -- see `_make_xrr_slab` (336-377):
  `MaterialSLD` (from `molecular`) is tried FIRST when
  `use_material_sld=True` (the default); direct `xray.sld_real`/
  `neutron.sld_real` is the fallback, and only raises
  `ModelInputError` if BOTH are missing. **So for our exporter, populating
  both `molecular` and `xray`/`neutron` is redundant-but-safe** (ModalFit
  will just recompute from `molecular` and ignore the direct SLD unless
  `use_material_sld=False` is explicitly set by the ModalFit user).
- `optical`: only required for SE and SPR predictions (`compute_se`,
  `compute_spr`) and for `_make_refellips_ri`; XRR/NR (`compute_xrr`/
  `compute_nr`) never call `get_nk`/`_make_refellips_ri` at all -- so a
  layer with NO `optical` block still works fine for XRR/NR, just not SE.
- `viscoelastic`: only required for QCM (`_voigt_layer_impedance`,
  `_qcm_substrate_params`) and NR/XRR density-varying fits;
  `_layer_density` defaults to `1200.0` kg/m3 if absent, no error.
- **Requirements differ per technique**: XRR/NR need `xray`/`neutron` or
  `molecular`; SE/SPR need `optical`; QCM needs `viscoelastic`. A layer can
  omit blocks for techniques it isn't used with.

### THE major inconsistency: `scattering` vs `xray`/`neutron`

`slab_model_builder.py`'s `LayerEditor.get_data()` (758-761) serializes SLD
under a **single combined `"scattering": {"sld_real", "sld_imag"}`** block
(XRR only -- there's no separate neutron scattering block anywhere in the
GUI builder's own persisted schema). But `physics.py`'s `_get_sld()`
(314-321), the function the LIVE web app (`server.py`) actually calls, reads
from **separate top-level `"xray"` and `"neutron"` blocks** depending on
`probe`, and never looks at `"scattering"` at all.

This means: a file saved by the GUI builder itself, with only its own
`"scattering"` block populated and no `molecular.formula`+`density`, would
NOT actually supply any real XRR SLD to a `physics.py`-driven prediction --
`_get_sld` would find nothing and raise (for a non-ambient layer) or default
to 0. The GUI's own save format and the live app's own read format disagree
on this one block. (`model_predictor.py`'s *own*, third, separate
implementation of `_get_sld` at model_predictor.py:273-287 DOES read
`"scattering"` -- but `model_predictor.py` is a standalone, unconnected
Tkinter tool per the finding above, not part of the live app.)

**Decision for our exporter: use `physics.py`'s convention (`xray`/`neutron`
blocks)**, since that's what the live app actually runs. See "gaps" section
below -- this is worth flagging to Aiden, and we should ALSO emit a
`"scattering"` alias block for cheap compatibility with the standalone
`model_predictor.py` tool, since nothing forbids extra keys.

## Q2: Units (traced through the actual arithmetic, not assumed)

- **X-ray/neutron SLD (`xray.sld_real`/`sld_imag`, `neutron.sld_real`/`sld_imag`)**:
  units of **1e-6 Å⁻²** (i.e. a value of `34.5` means `34.5e-6 Å⁻²`), matching
  our own DB convention exactly -- **no conversion needed.** Confirmed two ways:
  (a) `extract_params` (911-924) sets a default upper bound of `max(sv*2.0, 150.0)`
  for `sld_real_xray` -- only sensible if the value itself is O(1-150), which
  matches known SLDs in 1e-6 Å⁻² units (e.g. gold ~125), not plain Å⁻² (which
  would be O(1e-4)). (b) Empirically: `MaterialSLD('TiO2', 4.2362, probe='x-ray',
  wavelength=1.5406).complex(1.5406)` returns `(34.5176+1.7421j)` -- this is
  **identical to our own DB's `xray_sld_real`/`xray_sld_imag` for TiO2 rutile**
  (34.5178, 1.742017) to 4 decimal places. Confirmed by installing refnx and
  running it directly (see Q4/Q6).
- **Thickness / roughness (`structural.thickness`/`roughness`)**: **Å**.
  Labelled explicitly in the GUI ("Thickness (Å)", `slab_model_builder.py:708-709`)
  and used directly as `d_A`/Angstrom in `physics.py` (e.g. QCM's
  `_voigt_layer_impedance` call site converts `d_A * 1e-10` to meters,
  confirming the *input* unit is Å). **No conversion needed** -- our DB has
  no thickness/roughness data anyway (structural is caller-supplied, per the
  task doc).
- **Wavelength (`optical` inputs, tabulated n,k file column)**: **nm**.
  `nk_cauchy` does `wl_um = wl_nm / 1000.0` (physics.py:134), confirming the
  function's input array is nm. The tabulated-n,k CSV loader
  (`nk_tabulated`, 170-213) explicitly checks the median of the wavelength
  column and auto-converts micron-scale data (median < 50) to nm, with a
  comment warning this exact silent-unit-mismatch failure mode. **Our RI.info
  data is already in nm in the DB -- no conversion needed**, but we must
  make sure our exported CSV's wavelength column doesn't accidentally read
  as micron-scale (i.e. don't restrict to a narrow deep-UV-only slice whose
  median could dip under 50nm and get wrongly rescaled -- check this in Step 2).
- **`molecular.density` / `molecular.density_g_cm3`**: **g/cm3**. Read via
  `_get_molecular` (324-333, aliases both key names) and passed directly
  into `MaterialSLD(formula, density, ...)`, whose own docstring/parameter
  (confirmed via `inspect.getsource(MaterialSLD.__init__)`) declares
  `units="g / cm**3"`. **Matches our DB's `density_g_cm3` exactly.**
- **`viscoelastic.density`**: **kg/m3**, NOT g/cm3 -- distinct from
  `molecular.density`. Confirmed by `_make_xrr_slab:348`:
  `density = float(rho_ve) / 1000.0  # kg/m3 -> g/cm3` and the GUI label
  "Density ρ (kg/m³)" (`slab_model_builder.py:731`). We don't populate this
  block from the DB (viscoelastic/QCM data doesn't exist in our oxide
  dataset), so this is moot for our exporter, but worth noting so nobody
  later copies a `density_g_cm3` value into `viscoelastic.density` unconverted.
- **Energy/wavelength for XRR (`compute_xrr`'s `wavelength_A`/`energy_keV`)**:
  Å and keV respectively (`compute_xrr(... energy_keV=8.04...)`,
  `wavelength_A = 12.3984 / energy_keV`, physics.py:490-503) -- this is a
  simulation-run-time parameter, not a per-layer JSON field, so out of scope
  for the exporter itself, but matches our own `xray_energy_ev=8048`
  convention (8.04 keV vs our 8.048 keV -- Cu K-alpha to 3-4 sig figs either way).

## Q3: Tabulated n,k support

**Yes, but NOT inline in the JSON.** `"optical": {"model": "Tabulated n,k",
"params": {"file": "<path>"}}` -- the `file` value is a path to a **separate
CSV file** (`nk_tabulated`, physics.py:170-213), loaded via
`np.loadtxt(resolved, delimiter=",", skiprows=1)`, expecting >= 3 columns
(`wavelength, n, k`), one header row. `_resolve_nk_path` (110-119) resolves
relative paths against the JSON's own directory (`entry["_json_dir"]`) if
not found as-is or as an absolute path.

This means our exporter must write **one CSV sidecar file per (material,
dataset_label) axis**, not embed the n,k arrays in the JSON, and reference it
by relative path from wherever the JSON itself is written. Not a blocking
gap, just a required design element for Step 2 -- confirmed working, not
degraded to an analytic model.

The other four models (`scalar`, `Cauchy`, `Sellmeier`, `Lorentz`,
physics.py:126-167) ARE analytic-only and would require fitting our tabulated
n,k to one of those forms -- not needed since tabulated is supported directly.

## Q4: `molecular.formula` + `molecular.density` -> MaterialSLD

Confirmed via `inspect.getsource(MaterialSLD.__init__)` (refnx 0.1.64,
installed for this test): `self.__formula = pt.formula(formula)` --
`pt` is `periodictable`, imported directly inside `MaterialSLD.__init__`.
So ModalFit's own `molecular.formula` -> SLD path uses the exact same
`periodictable.formula()` parser our own `xrr_engine.py` now uses.

Empirically tested formula strings from our 50-oxide dataset:
`TiO2`, `LuAl3(BO3)4` (parenthesized), `Bi12GeO20` -- **all parse and
compute successfully** with no errors, via `MaterialSLD(formula, density,
probe='x-ray', wavelength=1.5406).complex(1.5406)`. No formula-cleaning
needed on our side for these; `_clean_formula` (physics.py:307-311) only
strips a bare polymer `"(...)n"` wrapper (matching our own
`_normalize_formula` fix in `xrr_engine.py`), which is a no-op on real
parenthesized oxide formulas like `LuAl3(BO3)4` since that regex requires
the paren group to be followed by the literal letter `n`, not a digit.

`probe` must be literally `"x-ray"` or `"neutron"` (lowercase, hyphenated)
or `MaterialSLD.__init__` raises `RuntimeError` -- confirmed by reading the
constructor.

## Q5: Are min/max bounds required?

**No, always optional.** `_pbounds()` (physics.py:86-89) and `_pv()` (66-69)
both accept a bare scalar OR a `{"value":..., "min":..., "max":...}` dict; a
bare scalar or a dict with `min`/`max` omitted yields `(value, None, None)`.
Every downstream consumer (`_make_xrr_slab`, `extract_params`, `compute_se`)
synthesizes a default bounds range from the value itself when `min`/`max`
are `None` (e.g. thickness defaults to `[0.2*value, 3*value+50]`,
roughness to `[0, 50]`, SLD-real to `[0, max(2*value, 150)]`). Omitting
`min`/`max` entirely is safe and common (this is exactly the caller-supplied,
not-in-the-DB case the task doc calls out for `structural`).

## Q6: Running the bundled example

**The example does not exist in this repository.** The README documents
`examples/example_PS_film_slab_model.json` and
`examples/example_synthetic_xrr_data.txt` (README.md:245-247), but no
`examples/` directory exists anywhere in the cloned tree (confirmed via
`find` across the whole clone, and via `git log --oneline --all -- "examples/*"`
returning nothing in the repo's only commit). This is the README being wrong
in the OPPOSITE direction from what the task doc warned about (claims a file
IS included that isn't, vs. claims one ISN'T included that is) -- worth
flagging to Aiden as a second README inaccuracy.

Since no example file was available, empirical validation was done instead
by installing ModalFit's actual dependencies (`refnx==0.1.64`,
`periodictable`) into this scratch environment and calling `MaterialSLD`
directly (not our own code) with real formulas/densities from our 50-oxide
dataset -- see Q2/Q4 above. This confirms our reading of the SLD unit
convention and formula-parsing behavior empirically, using ModalFit's own
dependency, even without the bundled example. `physics.py`'s `extract_params`
and `_compute_reflectometry` were also read function-by-function rather than
guessed at, per the task's "trust the code" instruction.

## Summary of gaps/mismatches

1. **Two incompatible SLD schemas in this codebase.** The GUI builder
   (`slab_model_builder.py`) persists a combined `"scattering"` block; the
   live app (`physics.py`, imported by `server.py`) reads separate
   `"xray"`/`"neutron"` blocks; the standalone `model_predictor.py` tool
   reads `"scattering"` again but is not wired into the live app at all.
   **We will export `xray`/`neutron` (matches the live app) plus a
   `scattering` alias (for `model_predictor.py` compatibility)**, and this
   needs its own line in `docs/for_aiden.md`.
2. **`role` omission handling is patched in `physics.py` with explicit "some
   exports omit this" comments, but `model_predictor.py`'s own
   `film_layers = [e for e in stack if e.get("role") == "layer"]` (its
   compute_xrr, ~line 314) has NO such fallback -- it requires the literal
   string `"layer"`.** We'll set `"role": "layer"` explicitly on every film
   layer for maximum compatibility across both consumers, not rely on omission.
3. **README documents an `examples/` directory that doesn't exist** in the
   cloned repo (opposite direction from the file-location inaccuracies the
   task doc already flagged) -- blocked the literal "run the bundled example"
   instruction; substituted direct dependency-level empirical testing instead.
4. **Minor GUI-label inconsistency** (not a functional bug, but worth a
   one-line mention to Aiden): `LayerEditor`'s SLD fields are labeled
   "×10⁻⁶ Å⁻²" (`slab_model_builder.py:720-721`) while `SubstrateEditor`'s
   identically-typed SLD fields are labeled plain "Å⁻²"
   (`slab_model_builder.py:843-844`) -- `physics.py` treats both identically
   (same `_get_sld` code path regardless of role), so this is just a
   confusing label, not a real unit difference.
5. **No blocking unit mismatches found** for xray_sld, neutron_sld,
   wavelength, or density -- all four match our DB's existing conventions
   with zero conversion required, once we target `physics.py`'s
   `xray`/`neutron` keys rather than the GUI's `scattering` key.
6. **Tabulated n,k requires a sidecar CSV file per axis**, not inline JSON
   arrays -- design requirement for Step 2, not a gap, but must be built
   into the exporter (`export_layer`) from the start.
