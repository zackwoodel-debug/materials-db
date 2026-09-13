# ModalFit launcher

A wrapper CLI (`scripts/modalfit_launcher.py`), not a fork: ModalFit's own source
(pinned commit, `src/materials_db/export/modalfit_contract.py`) is never modified.
Selecting and loading a material used to be entirely manual; this tool searches
materials_oxide_test.db, assembles an ambient/film(s)/substrate stack, exports it
with the existing `export_stack()`, and launches ModalFit pre-loaded with the result.

## Entry-point finding (checked before writing any launcher code)

No command-line argument for a model path exists anywhere in ModalFit -- grepped the
whole pinned repo for `sys.argv`/`argparse`: zero hits. But `model_predictor.py` (the
standalone Tkinter desktop tool, distinct from `server.py`'s Flask web app) is cleanly
importable as a module: `load_slab_model(path)` is a pure function, and
`ModelPredictorApp`'s "Load Model" button is bound to `self._load_model()`, which calls
`filedialog.askopenfilename()` then `load_slab_model()`. The launcher drives this exact
production code path by monkeypatching `askopenfilename` in *its own process's memory*
(never touching ModalFit's files on disk) to return the generated model path, then
calling `_load_model()` -- identical to a user clicking "Load Model" and picking the
file. See `src/materials_db/launcher/modalfit_bridge.py`.

**Why the desktop tool and not the web app**: read `server.py`'s `/api/model/upload`
route directly (lines 69-112 at the pinned commit). It accepts exactly one JSON file,
parses it, and calls `normalize_stack()` -- `_json_dir` is never set anywhere in that
path, and there's no second route for a companion CSV. `export_stack()`'s sidecar n,k
CSVs are written as paths relative to the JSON, so only the standalone tool (which
tracks the on-disk file location, `model_predictor.py:549-552`) can resolve them.

**Confirmed empirically, not just read**: built a disposable venv with real Tk +
ModalFit's actual dependencies (numpy/scipy/matplotlib/refnx/periodictable), exported a
real stack, and ran the launcher's exact sequence against the real `ModelPredictorApp`
class from the pinned clone. It loaded correctly on the first attempt.

## Environment requirement: Tk >= 8.6 (found on a real desktop run, now guarded against)

A real desktop run of this launcher came up with ModalFit's window as a genuinely blank
white rectangle -- no exception, nothing in stderr, just an empty window that never
painted, on every run. Isolated by ruling out every materials-db-side variable one at a
time, down to running ModalFit completely on its own (`python3 model_predictor.py`, zero
materials-db code involved) -- still blank. The actual cause: Tk version. A disposable
venv built with `python3 -m venv` from Apple's bundled system Python (`/usr/bin/python3`)
inherits Tk 8.5 (from roughly 2007), which cannot render ModalFit's Tk/matplotlib UI at
all on this machine. Rebuilding the identical venv from a Tk-8.6 Python already present
on the same machine (`/Library/Frameworks/Python.framework/Versions/3.13`, a standard
python.org installer) with the exact same dependencies fixed it immediately -- confirmed
with a full end-to-end run (HfO2 on sapphire, SE curves plotted, stack diagram correct,
see below).

`launcher/modalfit_bridge.check_tk_version()` now checks this before ever constructing
ModalFit's window, raising a clear, actionable error instead of reproducing that blank,
signal-free confusion for the next person: "This Python's Tk is version 8.5, but
ModalFit's GUI needs Tk >= 8.6 ... Use a Python built against Tk 8.6+ instead." Check any
candidate Python with `python3 -c "import tkinter; print(tkinter.TkVersion)"` before
pointing `--modalfit-path`/`MODALFIT_PATH` at it.

A separate, smaller, genuinely-real bug was also found and fixed along the way (kept
regardless of the Tk-version fix, since it's the objectively correct pattern):
`_load_model()` was being called synchronously right after constructing
`ModelPredictorApp()`, before `mainloop()` ever started -- normally it only runs as a
button-click callback while the event loop is already pumping and the window is already
mapped on screen. `launch()` now defers it via `app.after(0, ...)` so it fires as the
first event the running loop processes, matching how a real click would. Confirmed this
was NOT the cause of the blank window on its own (the same blank window still reproduced
with this fix applied, on Tk 8.5; it disappeared entirely on Tk 8.6 with or without it) --
worth keeping anyway as the correct ordering, not as the fix for the bug that was
actually found.

## Substrate: now DB-driven, not a fixed placeholder

`export_stack()`'s substrate used to be a fixed, non-DB-sourced Silicon constant
(`density_g_cm3=2.329, xray_sld_real=20.0620, xray_sld_imag=0.457236`) -- every fit run
before this launcher, including the HfO2 validation in `docs/xrr_fit_findings.md`, used
a substrate that never came from the database. Substrate is now resolved exactly like a
film layer, via `export_layer(role="substrate")`, picking up the same
`density_confidence`/`density_bounds`/citation fields a film layer already has (the old
placeholder had none of that visibility at all). Default is still "Silicon" (now the
real batch-3 DB material, not a constant); any of the 133 exportable materials --
including sapphire, quartz, and MgO -- can be picked instead. Cross-checked once for the
record: routing "Silicon" through `export_layer()` reproduces the legacy hardcoded
numbers to displayed precision (confirmed via `refnx.MaterialSLD("Si", 2.329, probe=
"x-ray")` -> 20.0620+0.4573j).

A real, concretely-triggered bug was found while validating this: Sapphire's polymorph
label is `"corundum/sapphire"` (a real, pre-existing DB value) -- `export_layer()`'s old
`nk_filename = f"{label}_nk.csv".replace(" ", "_")` only sanitized spaces, so the
embedded `/` in the label silently created a nested subdirectory (`Al2O3_corundum/
sapphire_nk.csv` resolved via `os.path.join` into an *accidental* `Al2O3_corundum/`
directory containing `sapphire_nk.csv`) instead of the flat file in `nk_csv_dir` the
function's own docstring promises. It happened to still resolve (ModalFit's own
`_resolve_nk_path` does the same `os.path.join`), so nothing had ever crashed -- the
bulk full-catalog exporter (`export_all_materials_modalfit.py`) sidesteps it entirely by
always passing an explicit `label=name` (the plain material name, no slash), so this had
never been exercised through a caller that uses the *default* label until this launcher
did. Fixed with a full filesystem-safe sanitizer (same pattern as
`export_all_materials_modalfit.py`'s own `_safe_dirname()`), not a wider `.replace()`.
One other DB material (`"scheelite/wulfenite"`, Lead molybdate) had the same latent
exposure.

## Ambient: presets, not DB-driven -- checked, not assumed

materials_oxide_test.db has zero liquid/gas materials, so there is nothing to build a
DB-driven ambient picker *from*. Checked against ModalFit's actual ambient-handling code
before deciding this (`physics.py:_make_xrr_boundary`, `compute_se`) rather than assumed:
ambient accepts either `molecular.formula`+`density` (computed live via refnx's
`MaterialSLD`, the same path every DB layer already uses) or a raw SLD value, plus its
own `optical` block for ellipsometry.

Air and vacuum have no real chemical formula (`MaterialSLD("Air", ...)` raises "unknown
element Ai") -- both get the raw-SLD path, exactly 0 for both probes (real air's SLD is
~10,000x smaller than any solid/liquid in this DB and is not modeled). D2O and H2O *are*
real formulas refnx and `periodictable` parse correctly -- deuterium is recognized as its
own element, confirmed empirically: `periodictable.formula("D2O", density=1.107)
.neutron_sld()` matches `refnx.MaterialSLD("D2O", 1.107, probe="neutron")` to 10+
significant figures, and both match the standard reflectometry-textbook contrast values
(H2O -0.56e-6 Å⁻², D2O +6.35-6.37e-6 Å⁻²) -- the real, well-established neutron
contrast-variation technique, not a knob that does nothing. Optical index for D2O/H2O is
a **constant** literature value at the sodium D-line (1.328/1.333), not a real dispersion
curve -- RI.info has tabulated water data, but wiring it in would mean adding water to
the DB as a real enriched material, out of scope here and flagged explicitly in the
preset's own `note` field rather than silently presented as equivalent to a DB material's
real dispersion. See `src/materials_db/launcher/ambient.py`.

## Optimizer rule, surfaced where it's relevant

`docs/xrr_fit_findings.md`'s stated rule 3 (tight bounds + a local optimizer trapped a
real fit at 100x chi², recovered exactly under a global optimizer) is printed by the CLI
at two points: immediately when a user actually narrows a thickness/roughness bound
(the exact moment it's relevant, not a doc they have to go find), and once more as a
reminder right before launch.

## End-to-end validation

HfO2 (300 Å, ALD-typical bounds) on Aluminium oxide / sapphire (a real DB substrate, not
Silicon) through the full pipeline: `scripts/modalfit_launcher.py`'s interactive flow
(scripted input, verified against real user-shaped choices) -> `export_stack()` -> the
real `ModelPredictorApp._load_model()` from the pinned ModalFit clone, in a venv with
ModalFit's actual dependencies installed.

- Stack loaded with 3 entries, correct roles (`ambient`/`layer`/`substrate`).
- Sapphire substrate's SLD, loaded back out of the stack ModalFit itself parsed,
  independently recomputed live via `refnx.MaterialSLD("Al2O3", <DB density>, probe=
  "x-ray")`: 32.60997 (stored) vs. 32.60998 (live refnx) -- agrees to 6 significant
  figures. Same check for HfO2: 67.67877 (stored) vs. 67.67903 (live refnx) -- agrees to
  4 significant figures, the same tolerance already documented for HfO2 in
  `docs/xrr_fit_findings.md`.
- Sidecar n,k CSV resolved correctly via `_json_dir`, confirmed on disk.

This is the first time a fit-oriented stack export in this project has used a
DB-sourced substrate instead of the fixed Silicon placeholder.

**Visually confirmed on a real interactive desktop session**, after the Tk-8.6 fix above
(this is the run that matters -- everything before it was data-correctness verification
against a blank window; this is the first time the actual rendered GUI was inspected):
title bar "ORNL Model Predictor -- SE * XRR * QCM", "Slab Model JSON:
hfo2_on_sapphire_final.json", the Layer Parameters panel showing HfO2 at exactly d=300.0
Å / σ=5.0 Å as entered through the CLI, and the Stack Diagram panel correctly rendering
Air -> HfO2 (300 Å, tabulated n,k) -> Al2O3_corundum/sapphire (tabulated n,k, "Total: 305
Å"), with live SE Ψ/Δ prediction curves already plotted from the real DB-derived optical
constants. Full round trip, from CLI selection through a real, correctly-painted ModalFit
window.
