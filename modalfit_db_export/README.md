# modalfit_db_export

Point it at a materials database file and an output directory; it connects,
reads, and writes ModalFit-compatible slab-model JSON.

```
    materials_oxide_test.db  ──▶  modalfit_db_export  ──▶  stack.json
    (SQLite)                                               + TiO2_rutile_nk.csv
                                                           + SiO2_amorphous_nk.csv
                                                           + Si_diamond_cubic_nk.csv
```

Self-contained: copy this one folder anywhere. **Standard library only** —
no install step, no `sys.path` juggling, no assumptions about surrounding
directories. (`pandas` is optional; see *Optional enrichment* below.)

---

## Quickstart

```bash
# what's in the database?
python -m modalfit_db_export --db path/to/materials_oxide_test.db --list

# one stack: 500 Å rutile TiO2 over 1000 Å SiO2 on a Si substrate
python -m modalfit_db_export \
    --db path/to/materials_oxide_test.db \
    --out out/my_sample \
    --layer "TiO2@rutile:500:5" "SiO2:1000:3" \
    --substrate Silicon --substrate-roughness 4

# every material in the database, one layer JSON each
python -m modalfit_db_export --db path/to/materials_oxide_test.db --out out/all
```

Same three things from Python:

```python
from modalfit_db_export import list_materials, export_stack_json, export_all_layers

list_materials("materials_oxide_test.db")

export_stack_json(
    db_path="materials_oxide_test.db",
    out_dir="out/my_sample",
    layers=[
        {"material": "TiO2", "dataset_label": "rutile", "thickness_a": 500.0, "roughness_a": 5.0},
        {"material": "SiO2", "thickness_a": 1000.0, "roughness_a": 3.0},
    ],
    substrate="Silicon",
    substrate_roughness_a=4.0,
)   # -> Path("out/my_sample/stack.json")

export_all_layers("materials_oxide_test.db", "out/all")
```

> **Keep the JSON and its CSVs together.** Each layer's `optical.params.file`
> is a bare filename resolved *relative to the JSON*. Moving the JSON on its
> own silently breaks every tabulated-n,k layer — see *Limitations*.

---

## The pipeline, in pseudocode

This is the whole thing. Everything below is `exporter.py` restated without
the error handling and provenance bookkeeping.

### Top level — database path + output path in, JSON out

```
FUNCTION export_stack_json(db_path, out_dir, layers, substrate):

    connection = sqlite3.connect(db_path)          # plain stdlib sqlite3
    MAKE DIRECTORY out_dir

    # 1. Resolve every label FIRST, before writing anything.
    #    A label is the layer's identity: it names the sidecar CSV AND
    #    becomes ModalFit's fit-parameter key ("SiO2_amorphous:thick").
    #    Two layers sharing a label would overwrite each other's CSV and
    #    collapse into ONE fittable parameter -- a repeated-unit stack
    #    (Bragg mirror, superlattice) would silently stop being fittable.
    substrate_label = resolve_label(connection, substrate)
    seen = {substrate_label: 1}                    # substrate seeds the count
    FOR each layer IN layers:
        base = layer.label OR resolve_label(connection, layer.material)
        seen[base] += 1
        final_label = base IF seen[base] == 1 ELSE base + "#" + seen[base]

    # 2. Build each entry (see export_layer below).
    stack = [ ambient_entry ]                      # air: exact-zero SLD
    FOR each layer, final_label:
        stack.APPEND( export_layer(..., role="layer",     label=final_label) )
    stack.APPEND(     export_layer(..., role="substrate", label=substrate_label) )

    # 3. Serialize. Ambient first, then films outermost-in, substrate last.
    WRITE out_dir/stack.json  <-  {stack_id, sample_id, version, provenance,
                                   n_layers, stack}
    RETURN path to stack.json
```

### Per layer — the actual DB → ModalFit translation

```
FUNCTION export_layer(connection, material_name, dataset_label, out_dir, label):

    # ---- A. Identify the material -------------------------------------
    row = SELECT material_id, name, formula FROM materials WHERE name = ?
    IF no row:
        row = SELECT ... WHERE formula = ?
        IF more than one row:
            RAISE ExportError          # "C" is both Diamond and Graphite.
                                       # Never silently pick one.

    # ---- B. Physical properties, disambiguated by polymorph ------------
    rows = SELECT dataset_label, density_g_cm3, xray_sld, neutron_sld, source_id
           FROM physical_properties WHERE material_id = ?

    # dataset_label packs the polymorph into its first " | " segment:
    #   "rutile | xray_sld_real | periodictable_CuKalpha"  -> polymorph "rutile"
    #   "xray_sld_real | periodictable_CuKalpha"           -> no polymorph
    #   "density_MP_DFT"                                   -> no polymorph
    # so the first segment is only a polymorph if it is NOT a quantity
    # marker ("density_", "xray_sld_real", ...) and NOT an "AuthorYYYY"
    # source label. Splitting blindly on " | " mistakes a quantity for a
    # polymorph.
    polymorphs = DISTINCT polymorph_prefix(r.dataset_label) FOR r IN rows

    IF dataset_label given:   chosen = the polymorph it matches
    ELIF exactly one:         chosen = that one
    ELSE:                     RAISE ExportError   # ambiguous -- caller must say which

    density, xray_sld_real/imag, neutron_sld_real/imag = the rows under `chosen`
    IF density IS NULL:
        RAISE ExportError   # refnx's MaterialSLD takes density as a REQUIRED
                            # positional arg with no fallback. Emitting null
                            # here means ModalFit guesses. Refuse instead.

    # ---- C. Optical dispersion: pick exactly ONE axis ------------------
    candidates = DISTINCT dataset_label FROM optical_dispersion
                 WHERE material_id = ? AND polymorph_prefix == chosen
    IF dataset_label matches one exactly:  use it
    ELIF only one candidate:               use it
    ELSE:                                  prefer isotropic, else o-ray,
                                           else alphabetically first
                                           AND PRINT what was chosen
        # ModalFit's optical block models an ISOTROPIC material. A
        # birefringent material's o/e axes cannot both be represented in
        # one layer. This is a real simplification, announced, not hidden.

    nk_rows = SELECT wavelength_nm, n, k FROM optical_dispersion
              WHERE material_id = ? AND dataset_label = ? ORDER BY wavelength_nm

    # ---- D. Units: one boundary, not scattered per field ---------------
    values = to_modalfit_units(density, slds, thickness, roughness)
        # Every field is currently an IDENTITY pass-through -- the DB and
        # ModalFit already agree:
        #     SLD        1e-6 Å^-2      density    g/cm³
        #     wavelength nm             thickness/roughness  Å
        # Kept as one function anyway, so a future real mismatch has
        # exactly one place to fix.

    # ---- E. Sidecar n,k CSV --------------------------------------------
    filename = sanitize(label) + "_nk.csv"        # "/" too: "corundum/sapphire"
    WRITE out_dir/filename:
        header  wavelength_nm, n, k
        rows    each nk_row, with k=0.0 where k IS NULL
        # ModalFit loads this with np.loadtxt, which needs every cell to
        # parse as a float -- an empty string for a missing k crashes.
        # 0.0 = transparent/non-absorbing. Count is printed, never silent.

    # ---- F. Density confidence decides the FIT BOUNDS ------------------
    IF "bulk_elemental_approximation" IN density's dataset_label:
        confidence = "bulk_approximation"
        bounds     = {min: density * 0.70, max: density * 1.02}
        # A bulk density standing in for an unmeasured film. Films are
        # usually LESS dense than bulk (voids, columnar growth), rarely
        # denser -- hence asymmetric, not ±X%.
    ELSE:
        confidence = "verified"
        bounds     = {min: density, max: density}
        # Zero-width: pins it, so a caller who marks every density
        # vary=True cannot move a value we are confident in.

    # ---- G. Assemble -----------------------------------------------------
    RETURN {
      label, role, material_type,           # material_type from the anion: O->oxide,
                                            # F->fluoride, N->nitride, S->sulfide
      molecular:  {formula, density_g_cm3, density_confidence, density_bounds},
      structural: {thickness: {value,min,max}, roughness: {value,min,max}},
      optical:    {model: "Tabulated n,k", params: {file: filename}},
      xray:       {sld_real, sld_imag},     # <- what the LIVE app reads
      neutron:    {sld_real, sld_imag},     #    (physics.py _get_sld)
      scattering: {sld_real, sld_imag},     # <- alias, x-ray, for the standalone
                                            #    model_predictor.py tool
      materials_db: {dataset_label, optical_dataset_label, mp_id,
                     density_confidence, density_source, optical_source}
    }
```

Two conventions worth stating outright, both verified against ModalFit's
fitting code rather than inferred (see `XRR_FIT_FINDINGS.md`):

- **`roughness` describes the interface ABOVE its layer**, never below —
  refnx's own `sld_obj(thick, rough)` convention. Get it backwards and every
  interface attaches to the wrong side with no error.
- **Positive imaginary SLD means absorption.** Both of ModalFit's consumption
  paths agree with that sign as-is; no conjugation.

---

## What the database must provide

Three tables. Anything satisfying this shape works — the exporter never
assumes a particular material set.

| Table | Columns used |
|---|---|
| `materials` | `material_id`, `name` (UNIQUE — the real identity key), `formula` |
| `physical_properties` | `material_id`, `dataset_label`, `density_g_cm3`, `xray_sld`, `neutron_sld`, `source_id` |
| `optical_dispersion` | `material_id`, `dataset_label`, `wavelength_nm`, `n`, `k`, `source_id` |
| `sources` | `source_id`, `doi`, `title`, `authors`, `journal`, `year` |

`dataset_label` carries the polymorph, quantity and provenance in one string
(`"rutile | xray_sld_real | periodictable_CuKalpha"`). Section B of the
pseudocode above is how it is parsed; that convention is the reason no schema
change was needed to add polymorph support.

**Always pass `name`, not `formula`, when you can** — `name` is UNIQUE,
`formula` is not (Diamond and Graphite are both `C`).

### Optional enrichment

If per-batch CSVs with `formula` and `mp_id` columns sit **beside the
database file**, each layer's `materials_db.mp_id` is filled in from them.
This needs `pandas`. Without the CSVs, without pandas, or both, that single
field is `None` and nothing else changes.

---

## Limitations

Real, known, and not worked around. Stated here so nobody rediscovers them.

1. **Sidecar n,k CSVs only resolve in the standalone desktop tool.**
   `physics.py:_resolve_nk_path` falls back to `json_dir + file`, but
   `json_dir` comes from `entry["_json_dir"]`, which *only*
   `model_predictor.py` ever sets. The live web app's upload route
   (`/api/model/upload`) accepts exactly one JSON file, never sets
   `_json_dir`, and has no route for a companion CSV at all. So a stack
   exported here loads correctly in the desktop tool, and its tabulated
   optical data does **not** resolve in the web app unless the path happens
   to be absolute and reachable on the server host. *This is the single
   biggest thing to fix if this gets merged upstream.*

2. **One optical axis per layer.** ModalFit's optical block is isotropic; a
   birefringent material's o/e (or biaxial α/β/γ) axes cannot both live in
   one layer. The exporter picks one, prefers isotropic → o-ray, and prints
   which it chose. It never silently averages them.

3. **Ambient is not database-driven.** The database holds thin-film solids —
   no liquids or gases — so `--ambient air` is an exact-zero-SLD placeholder,
   correct to ~4 decimal places for air/vacuum. For a liquid ambient (D₂O,
   H₂O) pass a pre-built entry dict to `export_stack()`; materials-db's
   `launcher/ambient.py` builds those with cited values.

4. **Missing `k` becomes `0.0`.** Many source datasets are n-only. The count
   is printed per file, never silent, but it *is* an approximation:
   transparent/non-absorbing, reasonable for visible-range dielectrics,
   wrong for an absorbing film.

5. **Two materials cannot be exported** and this is expected, not a bug —
   see `KNOWN_EXCLUSIONS` in `exporter.py`. Both lack any citable density,
   and the exporter refuses to emit a null density rather than letting
   ModalFit guess.

---

## Files

| File | |
|---|---|
| `exporter.py` | The translation. `export_layer()` / `export_stack()` return dicts. |
| `bulk.py` | Writes JSON to disk: `export_stack_json()`, `export_all_layers()`, `list_materials()`. |
| `__main__.py` | The `python -m modalfit_db_export` CLI. |
| `citations.py` | Vendored optical-source phase-resolution table (data). |
| `density.py` | Vendored density-confidence constants and fit bounds. |
| `contract.py` | **The pinned ModalFit commit + every schema finding with file:line citations.** |
| `SCHEMA_NOTES.md` | Full derivation of the schema and units. |
| `XRR_FIT_FINDINGS.md` | The roughness-side and SLD-sign verification. |

### `contract.py` is the important one

ModalFit's own README has already diverged from its actual behavior twice
during this integration — it documents an `examples/` directory that does not
exist, and labels SLD units inconsistently between its own `LayerEditor`
("×1e-6 Å^-2") and `SubstrateEditor` ("Å^-2") for functionally identical
fields. So none of the schema assumptions here rest on documentation; each one
cites the file and line in ModalFit's source it was verified against, at a
pinned commit:

```
MODALFIT_COMMIT_SHA = "4eef754295be929f77b04dcfcd8b6c882ba5f101"   # 2026-08-12
```

If exports start misbehaving, diff a fresh clone against that SHA and re-check
the cited lines. That tells you immediately whether it is a bug here or
upstream drift — instead of re-deriving the whole schema from scratch.

---

## Relationship to materials-db

`exporter.py` is a copy of materials-db's
`src/materials_db/export/modalfit.py`. The translation logic is **unchanged**;
exactly three couplings to that repo's layout were rewired, each marked
`# DROP-IN:` inline and explained in the module docstring:

1. Citations and density helpers, previously imported from `scripts/` via a
   `sys.path.insert` and from the ingestion pipeline package, are now vendored
   siblings.
2. `_ROOT` / `DEFAULT_DB` — a hardcoded path into the checkout — are gone. The
   database is always an explicit argument, so this can never silently read
   the wrong database.
3. `_lookup_mp_id()` globbed that same hardcoded `data/` directory and
   imported pandas unconditionally. It now takes the directory as a parameter
   (defaulting to the database's own directory, which reproduces the original
   behavior exactly) and degrades to `None` without pandas.

`bulk.py` has one deliberate **behavior change** from materials-db's
`scripts/export_all_materials_modalfit.py`: that script discovers which
materials to export by globbing `data/*.csv` for per-batch enrichment files
and asserting the count matches the database's own. Here the **database is the
source of truth** (`SELECT name, formula FROM materials`), because a drop-in
cannot assume those CSVs travelled with it. The material set is identical
whenever both are available — that script asserts as much — and this version
also works on a database standing on its own. Pass `strict=True` (or
`--strict`) to keep the upstream assertion that the skip set matches
`KNOWN_EXCLUSIONS` exactly.

### Verified against the original

Exporting the same stack through both paths produces **byte-identical** JSON
(modulo the intentionally re-labelled `provenance.generated_by`) and
**byte-identical** sidecar CSVs. The full-catalog run exports 133/135
materials with the skip set matching `KNOWN_EXCLUSIONS` exactly under
`--strict`.
