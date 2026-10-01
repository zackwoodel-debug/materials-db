# Phase 5 pilot: batch 3b on the shared family loader

Status (2026-09-30): **done for batch 3b**; the other standalone loaders are described below, not converted.

## What changed

`scripts/load_batch3b_db.py` (188 lines, its own insert / source / InChIKey logic) is now an 80-line wrapper over
`scripts/load_family_db.py run_family`, keeping its command name. The batch's policies are explicit, either in data or in the
wrapper's call (maintainer decision (a), 2026-09-30: options on the shared loader whose defaults leave every other family
unchanged):

| Batch-3b policy | Where it lives now |
|---|---|
| selections (one per material, exact dataset labels) | `data/step1_selections_batch3b.json`, generated from `scripts/pure_element_material_list.py` by `scripts/build_batch3b_selections.py` |
| keyed by name (Diamond and Graphite share formula "C") | `run_family(selection_key_column="name")` |
| shared InChIKey stored as NULL for the later allotrope | `run_family(on_duplicate_inchikey="store_null")` (default `"skip"`) |
| the batch's own source rows, never reusing an earlier row | `run_family(reuse_existing_source_rows=False, named_source_fields=..., bulk_approx_source=...)` (defaults: reuse) |
| density-citation notes as the original loader wrote them | `run_family(citation_catalog_name="oxides_50.csv")`; the text is wrong (tracked: `batch3b_citation_notes_name_wrong_catalog`) |
| append only onto the 131-material state | the wrapper's precondition, as before |

## Parity

- **Defaults unchanged:** with the new options at their defaults, rebuilding the whole base DB (oxides through `run_family`) gave
  a database identical to the pre-change rebuild in every table and column, ids included.
- **Batch 3b:** on the 131-material state, the new wrapper adds exactly what the original loader added (4 materials, 9 sources,
  20 physical rows, 4,806 optical rows) and the result is identical to the original loader's in every table and column, ids
  included. No skips, conflicts or warnings.
- **Kept true by `tests/test_batch3b_loader.py`:** the tracked `data/materials_oxide_test.db` is rebuilt from its committed inputs
  with the current loaders and compared table by table (optical rows by content; `record_id` is an insertion counter); the
  selections file is regenerated and compared; the new options' defaults still refuse what they refused before. A one-word change
  to the batch's source text fails it.

## Remaining migrations (described, not done)

1. `load_batch2_db.py` (159 lines) and `load_pure_element_db.py` (159 lines): the same append pattern as batch 3b (selections in
   Python lists `MATERIALS_31` / `MATERIALS_PURE_ELEMENTS`, their own source rows, their own preconditions of 50 and 81 materials).
   The options added here should cover them; each needs its selections file generated from its list, its source text moved into
   the wrapper verbatim, and the same base-DB reproduction test, which already covers them (it rebuilds all four).
2. The builders (`build_*_csv.py`) are a different layer: they query PubChem and Materials Project (network, API key) and write
   the family CSVs. Twelve are standalone; consolidating them is a separate project and needs cached responses to be testable
   offline.
3. Findings to resolve separately: the wrong catalog name in two batch-3b citation notes; Boron's "amorphous" in its polymorph slot
   (`boron_amorphous_in_polymorph`, with Phase 4A).
