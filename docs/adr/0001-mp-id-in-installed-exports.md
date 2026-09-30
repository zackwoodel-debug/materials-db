# ADR 0001: `mp_id` in installed ModalFit exports

- Status: **proposed** (plan only; nothing implemented). Decision needed from the maintainer.
- Date: 2026-09-30
- Context: Phase 2 found, and `docs/installation.md` records, that installed and checkout ModalFit exports are **not
  equivalent**.

## Problem

`materials_db.export.modalfit._lookup_mp_id()` finds a material's Materials Project id by globbing the checkout's
`data/*.csv`. An installed wheel has no `data/`, so the lookup returns `None` and every exported layer carries `mp_id` as
missing. Checked on 3 materials in Phase 2: of 145 exported fields only `mp_id` differed (`mp-1143` vs `None` for sapphire);
the n,k files were byte-identical. `tests/test_wheel_install.py` pins the current behaviour.

The export presents this as an ordinary missing value. The project's own rule elsewhere is to refuse (`ExportError`) rather than
emit a guessed or quiet null.

## What `mp_id` is

An external identifier (a pointer to a Materials Project entry), not a measurement. It is provenance: it says which calculated
structure a density or descriptor came from.

## Licence check (the redistribution question)

- Materials Project data is CC BY 4.0: it may be copied, redistributed and adapted with attribution to the Materials Project
  ([MP terms](https://legacy.materialsproject.org/terms); [MPContribs terms](https://next-gen.materialsproject.org/about/mpcontribs-terms)).
- This repository already redistributes the ids. Every release's `family_tables/*.csv` (e.g. `oxides_50.csv`) has an `mp_id`
  column, and `DATA_LICENSE.md` declares the compiled data CC BY 4.0 and credits the Materials Project (Jain et al. 2013) as
  an upstream source, passing its attribution requirement on.
- Conclusion: shipping the same identifiers inside the wheel is covered by the same licence and attribution; it does not
  create a new obligation, provided the wheel's metadata carries the same `DATA_LICENSE.md` attribution. (Not legal advice;
  the facts above are what the decision rests on.)

## Options

1. **Refuse.** Installed, with no id source, `export_layer` raises `ExportError` naming the missing lookup source, unless the
   caller opts in (e.g. `allow_missing_mp_id=True`). Matches the project's refuse-don't-guess rule; breaks installed callers
   that don't need `mp_id` until they opt in.
2. **Flag explicitly.** Export continues, but the layer records why the id is absent: `mp_id: null` plus
   `mp_id_status: "unavailable: no id source (installed without a checkout)"` (a checkout would record `"found"` or
   `"no MP entry"`). No silent null; no breakage.
3. **Ship the ids.** Package a small `material name/key -> mp_id` map (generated from the family tables at build time) as
   package data, with the attribution, so installed and checkout exports become equivalent. Needs a single source of truth and
   a test that the packaged map equals the checkout lookup.
4. **Status quo.** Keep the documented non-equivalence. Not recommended: the null is indistinguishable from "this material has
   no MP entry".

Options 2 and 3 combine well: 3 removes the difference; 2 keeps any remaining gap visible.

## Recommendation

**3 + 2**: ship the id map (licence-compatible, as the ids are already redistributed under the same terms), and add the
explicit status field so a missing id can never look like an ordinary null. If shipping data in the wheel is unwanted, use
**2** alone; use **1** if silent continuation is unacceptable even with a flag. Your stated preference (refuse or explicitly
flag over a quiet missing value) is met by 1, 2 and 3+2.

## Required before implementing

- A parity test: for every exported material, installed export == checkout export, field by field (it currently differs only in
  `mp_id`).
- The ModalFit contract and pin (`export/modalfit_contract.py`) are not touched; a new field must be one ModalFit ignores, or
  be confirmed against the pinned ModalFit commit first.
- The existing pinned-behaviour assertion in `tests/test_wheel_install.py` changes deliberately, in the same commit.
